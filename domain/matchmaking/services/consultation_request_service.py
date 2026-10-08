from dataclasses import dataclass

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from domain.matchmaking.models import ConsultationRequest
from domain.matchmaking.models.consultation_request import NOT_ELIGIBLE_MESSAGE
from notification.services.consultation_emails import notify_new_consultation_request

RATE_LIMIT_ATTEMPTS = 5          # per address...
RATE_LIMIT_WINDOW = 60 * 60      # ...per hour


class NotEligibleError(Exception):
    pass


@dataclass(frozen=True)
class SubmissionResult:
    consultation_request: ConsultationRequest
    created: bool


@transaction.atomic
def submit_consultation_request(candidate: ConsultationRequest) -> SubmissionResult:
    """
    Save a new request, or note a resubmission if this email already has an open one.
    Emails are sent only after the save has committed.
    """
    if candidate.relationship_status in ConsultationRequest.BLOCKED_STATUSES:
        raise NotEligibleError(NOT_ELIGIBLE_MESSAGE)

    candidate.email = candidate.email.strip().lower()

    existing = (
        ConsultationRequest.objects.open()
        .select_for_update()
        .filter(email__iexact=candidate.email)
        .first()
    )
    if existing:
        existing.resubmission_count += 1
        existing.last_resubmitted_at = timezone.now()
        existing.save(update_fields=["resubmission_count", "last_resubmitted_at", "updated_at"])
        return SubmissionResult(existing, created=False)

    candidate.status = ConsultationRequest.Status.AWAITING_PAYMENT
    candidate.save()
    transaction.on_commit(lambda: notify_new_consultation_request(candidate))
    return SubmissionResult(candidate, created=True)


def is_rate_limited(ip: str | None) -> bool:
    """Counts this attempt. True once an address goes over the hourly limit."""
    if not ip:
        return False
    key = f"consultation-request:{ip}"
    if cache.add(key, 1, RATE_LIMIT_WINDOW):
        return False
    try:
        return cache.incr(key) > RATE_LIMIT_ATTEMPTS
    except ValueError:  # key expired between add and incr
        cache.set(key, 1, RATE_LIMIT_WINDOW)
        return False