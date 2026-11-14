"""
Renewal reminders (Service Journey 11.4 and section 5): the member and their matchmaker are emailed
60, 30 and 14 days before the membership ends.

Run once a day by Celery Beat (domain/matchmaking/tasks.py). Each reminder goes once: the last one
sent is stored on the membership. If the job missed a few days, only the latest due reminder is sent
(never three at once). When the membership is renewed, the end date moves out and the reminders
start again. Members on hold are skipped: their end date will still move.
"""
import logging
from datetime import timedelta

from django.utils import timezone

from domain.matchmaking.models import Membership

logger = logging.getLogger(__name__)

REMINDER_DAYS = (60, 30, 14)


def due_reminder(days_left, last_sent):
    """
    Which reminder (60 / 30 / 14) is due today, or None.
    last_sent: the last one already sent for this end date (None = none yet).
    """
    if days_left < 0 or days_left > max(REMINDER_DAYS):
        return None
    due = min(mark for mark in REMINDER_DAYS if days_left <= mark)
    if last_sent is not None and last_sent <= due:
        return None
    return due


def send_renewal_reminders(today=None):
    """Returns {"sent": n, "reset": n, "failed": n}. Never raises: one bad record doesn't stop the rest."""
    from notification.services import membership_emails

    today = today or timezone.localdate()
    summary = {"sent": 0, "reset": 0, "failed": 0}
    window_end = today + timedelta(days=max(REMINDER_DAYS))

    # Renewed (end date moved past the window): start the reminders again next time round
    summary["reset"] = Membership.objects.filter(
        renewal_reminder_days__isnull=False, end_date__gt=window_end,
    ).update(renewal_reminder_days=None)

    candidates = (
        Membership.objects
        .filter(status=Membership.Status.ACTIVE, end_date__gte=today, end_date__lte=window_end)
        .select_related("client", "client__user", "client__matchmaker", "tier")
    )
    for membership in candidates:
        if membership.on_hold:
            continue
        days_left = (membership.end_date - today).days
        due = due_reminder(days_left, membership.renewal_reminder_days)
        if due is None:
            continue
        try:
            membership_emails.deliver_renewal_reminder(membership, days=days_left)
        except Exception:  # noqa: BLE001 - keep going; it's tried again tomorrow
            logger.exception("Renewal reminder failed for membership %s", membership.pk)
            summary["failed"] += 1
            continue
        Membership.objects.filter(pk=membership.pk).update(renewal_reminder_days=due)
        summary["sent"] += 1
    return summary