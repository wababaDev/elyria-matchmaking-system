"""
Self-Service Profile rules: create (pre-filled), save and return, mark complete.
"""
from io import BytesIO

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageOps

from domain.matchmaking.models import ClientProfile, ConsultationRequest, ProfilePhoto
from domain.matchmaking.profile_sections import HIGH_IMPACT, SECTIONS, display_value, section_status

MAX_NON_NEGOTIABLES = 5
PHOTO_MAX_EDGE = 1600  # pixels, longest side (matches the browser)
PHOTO_QUALITY = 80


def _shrink_photo(upload):
    """
    Resize to at most PHOTO_MAX_EDGE on the long side, turn it the right way up, and save as JPEG.
    Saving without EXIF also removes hidden data such as the GPS location the photo was taken at.
    """
    upload.seek(0)
    with Image.open(upload) as original:
        image = ImageOps.exif_transpose(original)  # phones store rotation in EXIF
        image = image.convert("RGB")               # JPEG needs RGB (also flattens PNG transparency)
        image.thumbnail((PHOTO_MAX_EDGE, PHOTO_MAX_EDGE))  # keeps proportions, never enlarges
        out = BytesIO()
        image.save(out, "JPEG", quality=PHOTO_QUALITY, optimize=True)
    return ContentFile(out.getvalue(), name="photo.jpg")

# What the person is seeking → the partner's gender
_SEEKING_TO_GENDER = {
    ConsultationRequest.Seeking.MAN: ConsultationRequest.Gender.MALE,
    ConsultationRequest.Seeking.WOMAN: ConsultationRequest.Gender.FEMALE,
}


class ProfileLockedError(Exception):
    """A completed profile can be edited, but required answers can't be emptied again."""

    def __init__(self, missing):
        self.missing = missing  # [(section, [labels]), ...] for incomplete sections only
        super().__init__("Required answers can't be removed from a completed profile.")


def _prefill(client):
    """'Confirm your details' starts from what they sent with the consultation request."""
    cr = client.consultation_request
    statuses = ClientProfile.RelationshipStatus.values
    return {
        "full_name": client.full_name or cr.full_name,
        "preferred_name": client.preferred_name or cr.preferred_name,
        "age": cr.age,
        "gender": cr.gender,
        "seeking": cr.seeking,
        "relationship_status": cr.relationship_status if cr.relationship_status in statuses else "",
        "location": cr.location,
        "nationality": cr.nationality,
        "occupation": cr.occupation,
        "phone": cr.phone,
        "partner_gender": _SEEKING_TO_GENDER.get(cr.seeking, ""),
    }


def get_profile(client):
    """The member's profile, created and pre-filled the first time it's needed."""
    try:
        return client.profile
    except ClientProfile.DoesNotExist:
        profile, _ = ClientProfile.objects.get_or_create(client=client, defaults=_prefill(client))
        return profile


def incomplete_sections(profile, *, has_photos=None):
    """[(section, [missing labels]), ...] for sections that still need answers."""
    if has_photos is None:
        has_photos = profile.pk is not None and profile.photos.exists()
    return [(s, missing) for s, missing in section_status(profile, has_photos=has_photos) if missing]


def progress(profile):
    """(sections complete, total sections) for the progress bar."""
    incomplete = len(incomplete_sections(profile))
    return len(SECTIONS) - incomplete, len(SECTIONS)


def _save_photo(profile, kind, upload):
    """One photo per kind: a new upload replaces the old one (and its file)."""
    old = profile.photos.filter(kind=kind).first()
    if old:
        old.image.delete(save=False)
        old.delete()
    ProfilePhoto.objects.create(profile=profile, kind=kind, image=_shrink_photo(upload))


@transaction.atomic
def save_profile(profile, *, photos=None, complete=False):
    """
    Save the member's answers. `profile` already holds the new values (from the form).

    - Not complete yet: always saves, so nothing they typed is lost.
      With complete=True it then checks the required answers and, if all are there,
      marks the profile complete and alerts the matchmaker.
    - Already complete: required answers can't be emptied again (ProfileLockedError, nothing saved).

    Returns the incomplete sections (empty list = everything required is answered).
    """
    photos = {kind: f for kind, f in (photos or {}).items() if f}
    has_photos = bool(photos) or profile.photos.exists()

    changes = []
    if profile.is_complete:
        missing = incomplete_sections(profile, has_photos=has_photos)
        if missing:
            raise ProfileLockedError(missing)
        changes = changed_fields(profile, new_photos=photos)

    profile.save()
    for kind, upload in photos.items():
        _save_photo(profile, kind, upload)

    missing = incomplete_sections(profile, has_photos=has_photos)
    if complete and not missing and not profile.is_complete:
        profile.completed_at = timezone.now()
        profile.save(update_fields=["completed_at", "updated_at"])

        from notification.services.profile_emails import notify_profile_completed

        transaction.on_commit(lambda: notify_profile_completed(profile.client))
    elif changes:
        # A completed profile was changed: log each change in the member's notes, and tell the matchmaker
        from domain.matchmaking.services.member_note_service import log_profile_changes
        from notification.services.profile_emails import notify_profile_updated

        log_profile_changes(profile.client, changes)
        sections = list(dict.fromkeys(c["section"] for c in changes))  # unique, in page order
        important = [f'{c["label"]}: {c["old"] or "(blank)"} → {c["new"] or "(blank)"}' for c in changes if c["high_impact"]]
        transaction.on_commit(lambda: notify_profile_updated(profile.client, sections, important))
    return missing


def changed_fields(profile, *, new_photos=None):
    """
    Every answer that differs from what is saved (call before saving).
    [{"section", "label", "old", "new", "high_impact"}, ...] with readable values.
    """
    saved = ClientProfile.objects.get(pk=profile.pk)
    changes = []
    for section in SECTIONS:
        for spec in section.fields:
            if getattr(saved, spec.name) != getattr(profile, spec.name):
                changes.append({
                    "section": section.title,
                    "label": str(ClientProfile._meta.get_field(spec.name).verbose_name),
                    "old": display_value(saved, spec),
                    "new": display_value(profile, spec),
                    "high_impact": spec.name in HIGH_IMPACT,
                })
        if section.has_non_negotiables and saved.non_negotiables != profile.non_negotiables:
            changes.append({
                "section": section.title, "label": "Non-negotiables",
                "old": "; ".join(saved.non_negotiables), "new": "; ".join(profile.non_negotiables),
                "high_impact": False,
            })
        if section.has_photos and new_photos:
            kinds = ", ".join(str(ProfilePhoto.Kind(k).label) for k in new_photos)
            changes.append({
                "section": section.title, "label": "Profile photos",
                "old": "", "new": f"New photo: {kinds}", "high_impact": False,
            })
    return changes