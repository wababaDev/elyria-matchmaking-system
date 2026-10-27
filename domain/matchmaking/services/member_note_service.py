"""
Matchmaker Notes: add, edit (keeping history), close. Never delete.
"""
from django.db import transaction
from django.utils import timezone

from domain.matchmaking.models import MemberNote, MemberNoteRevision
from domain.matchmaking.services.consultation_request_service import InvalidTransitionError

Kind = MemberNote.Kind
Status = MemberNote.Status


def notes_for(client, *, show=""):
    """The member's notes, newest first. show: '' (all), 'open', or a kind."""
    qs = client.notes.select_related("author", "closed_by").prefetch_related("revisions__edited_by")
    if show == "open":
        qs = qs.filter(status=Status.OPEN)
    elif show in Kind.values:
        qs = qs.filter(kind=show)
    return qs


def note_summary(client):
    """Counts for the summary strip."""
    notes = client.notes.all()
    last = notes.order_by("-created_at").values_list("created_at", flat=True).first()
    return {
        "open_discrepancies": notes.filter(kind=Kind.DISCREPANCY, status=Status.OPEN).count(),
        "changes_to_review": notes.filter(kind=Kind.PROFILE_CHANGE, status=Status.OPEN).count(),
        "high_impact_open": notes.filter(status=Status.OPEN, affects_matching=True).count(),
        "total": notes.count(),
        "last": last,
    }


def add_observation(client, *, category, body, by):
    if not body.strip():
        raise InvalidTransitionError("Write the observation.")
    return MemberNote.objects.create(
        client=client, kind=Kind.OBSERVATION, author=by, category=category, body=body.strip()
    )


def add_discrepancy(client, *, subject, consultation_answer, profile_answer, difference, body,
                    follow_up, follow_up_due, by):
    if not subject.strip() or not body.strip():
        raise InvalidTransitionError("Say what was compared and what you noticed.")
    return MemberNote.objects.create(
        client=client, kind=Kind.DISCREPANCY, author=by, status=Status.OPEN,
        subject=subject.strip(), first_value=consultation_answer.strip(), second_value=profile_answer.strip(),
        difference=difference, body=body.strip(), follow_up=follow_up, follow_up_due=follow_up_due,
        affects_matching=difference != MemberNote.Difference.WORDING,
    )


@transaction.atomic
def edit_note(note, *, body, by):
    """Only the author can edit, and the earlier text is kept."""
    note = MemberNote.objects.select_for_update().get(pk=note.pk)
    if note.by_system or note.author_id != by.pk:
        raise InvalidTransitionError("You can only edit notes you wrote.")
    body = body.strip()
    if not body:
        raise InvalidTransitionError("A note can't be emptied. Add a new note to correct it instead.")
    if body == note.body:
        return note
    MemberNoteRevision.objects.create(note=note, previous_body=note.body, edited_by=by)
    note.body = body
    note.save(update_fields=["body", "updated_at"])
    return note


@transaction.atomic
def close_note(note, *, outcome, resolution, by):
    """Close an open discrepancy or mark a profile change as reviewed. A note on what was done is required."""
    note = MemberNote.objects.select_for_update().get(pk=note.pk)
    if not note.is_open:
        raise InvalidTransitionError("This item is already closed.")
    if not resolution.strip():
        raise InvalidTransitionError("Say what was done before closing.")
    note.status = Status.CLOSED
    note.outcome = outcome
    note.resolution = resolution.strip()
    note.closed_at = timezone.now()
    note.closed_by = by
    note.save(update_fields=["status", "outcome", "resolution", "closed_at", "closed_by", "updated_at"])
    return note


def log_profile_changes(client, changes):
    """
    Called when a member edits a completed profile. One note per changed field,
    written by the system, open until a matchmaker reviews it.
    changes: [{"label", "old", "new", "high_impact"}, ...]
    """
    MemberNote.objects.bulk_create([
        MemberNote(
            client=client, kind=Kind.PROFILE_CHANGE, author=None, status=Status.OPEN,
            subject=c["label"], first_value=c["old"], second_value=c["new"],
            body="Changed by the member in their profile.",
            affects_matching=c["high_impact"],
        )
        for c in changes
    ])