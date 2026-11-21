"""
A completed Self-Service Profile as a branded PDF, for staff.

Rendered from an HTML template with WeasyPrint. Images (logo and member photos)
are embedded as data URIs, so nothing is fetched over the network and the private
photos never need a URL.
"""
import base64
import logging

from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import slugify

from domain.matchmaking.profile_sections import answers_by_group

logger = logging.getLogger(__name__)

LOGO = "front/assets/logo-hz.png"


class ProfileNotCompleteError(Exception):
    pass


def _data_uri(data, mime):
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def _static_uri(path, mime="image/png"):
    found = finders.find(path)
    if not found:
        return ""
    with open(found, "rb") as f:
        return _data_uri(f.read(), mime)


def _photo_uri(photo):
    try:
        with photo.image.open("rb") as f:
            return _data_uri(f.read(), "image/jpeg")
    except FileNotFoundError:
        return ""


def profile_filename(client):
    """e.g. Natasha-EL-7K3M9Q-profile-20261024.pdf: the name to recognise it, the reference to tell two Natashas apart."""
    profile = getattr(client, "profile", None)
    name = slugify((profile.preferred_name if profile else "") or client.preferred_name).title() or "Member"
    reference = client.consultation_request.payment_reference or f"member-{client.pk}"
    return f"{name}-{reference}-profile-{timezone.localdate():%Y%m%d}.pdf"


def profile_pdf(client, *, by):
    """PDF bytes for a member's completed profile."""
    from weasyprint import HTML  # imported here so the rest of the site doesn't need it loaded

    profile = getattr(client, "profile", None)
    if not profile or not profile.is_complete:
        raise ProfileNotCompleteError("The profile isn't complete yet.")

    photos = [
        {"label": p.get_kind_display(), "src": src}
        for p in profile.photos.all()
        if (src := _photo_uri(p))
    ]
    html = render_to_string("domain/management/members/profile_pdf.html", {
        "client": client,
        "profile": profile,
        "membership": getattr(client, "membership", None),
        "groups": answers_by_group(profile, has_photos=bool(photos)),
        "photos": photos,
        "logo": _static_uri(LOGO),
        "generated_at": timezone.localtime(),
        "generated_by": by,
    })
    logger.info("Profile PDF for client %s downloaded by user %s", client.pk, by.pk)
    return HTML(string=html).write_pdf()