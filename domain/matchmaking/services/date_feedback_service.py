"""
Date feedback: what a member said after each date with the person they were introduced to,
plus their matchmaker's own record and the outcome that decides what happens next.
"""
from django.db import transaction
from django.db.models import Max

from domain.matchmaking.models.date_feedback import DateFeedback
from domain.matchmaking.services.consultation_request_service import InvalidTransitionError
from domain.matchmaking.services.pairing_service import _close, _lock, can_manage

ENDING_OUTCOMES = {DateFeedback.Outcome.ENDED_BY_CLIENT, DateFeedback.Outcome.ENDED_BY_MATCH}


def can_record_feedback(user, pairing, client):
    """Only the member's own matchmaker (or Admin), and only once the introduction is set."""
    return (
        client.pk in (pairing.client_a_id, pairing.client_b_id)
        and pairing.introduced_on is not None
        and can_manage(user, client)
    )


def feedback_for(pairing, client):
    return DateFeedback.objects.filter(pairing=pairing, client=client).select_related("recorded_by", "updated_by")


def next_date_number(pairing, client):
    return (DateFeedback.objects.filter(pairing=pairing, client=client).aggregate(n=Max("date_number"))["n"] or 0) + 1


def new_feedback(pairing, client):
    """An unsaved record with the facts filled in: date 1 from the introduction, later dates blank."""
    number = next_date_number(pairing, client)
    first = number == 1
    return DateFeedback(
        pairing=pairing, client=client, date_number=number,
        date=pairing.introduced_on if first else None,
        setting=pairing.introduction_setting if first else "",
        setting_other=pairing.introduction_setting_other if first else "",
        duration_minutes=pairing.introduction_minutes if first else None,
    )


@transaction.atomic
def save_feedback(feedback, *, by):
    """
    Save new or edited feedback. Ending outcomes close the pairing; a Serious flag emails Admin.
    `feedback` is the instance from the form (not yet saved).
    """
    if not can_record_feedback(by, feedback.pairing, feedback.client):
        raise InvalidTransitionError("Only this member's matchmaker can record their feedback.")

    was_serious = False
    if feedback.pk:
        was_serious = DateFeedback.objects.get(pk=feedback.pk).flag_severity == DateFeedback.Severity.SERIOUS
        feedback.updated_by = by
    else:
        feedback.recorded_by = by
    feedback.save()

    if feedback.outcome in ENDING_OUTCOMES:
        pairing = _lock(feedback.pairing)
        if pairing.is_open:
            by_client = feedback.outcome == DateFeedback.Outcome.ENDED_BY_CLIENT
            who = feedback.client.preferred_name if by_client else pairing.other(feedback.client).preferred_name
            _close(pairing, f"Ended after date {feedback.date_number} by {who}.", by=by)
            pairing.save()

    if feedback.flag_severity == DateFeedback.Severity.SERIOUS and not was_serious:
        from notification.services import feedback_emails

        transaction.on_commit(lambda: feedback_emails.notify_admin_serious_flag(feedback))
    return feedback


def feedback_by_pairing(member):
    """{pairing_id: [feedback, ...]} for the member page's Pairings tab (this member's feedback only)."""
    grouped = {}
    for fb in DateFeedback.objects.filter(client=member).select_related("recorded_by").order_by("date_number"):
        grouped.setdefault(fb.pairing_id, []).append(fb)
    return grouped