from dataclasses import dataclass

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from domain.matchmaking.models import ConsultationRequest
from domain.matchmaking.models.consultation_request import NOT_ELIGIBLE_MESSAGE
from notification.services.consultation_emails import notify_new_consultation_request
from django.db.models import Q

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


# ---------- Staff side ----------

class InvalidTransitionError(Exception):
    pass


LIST_FILTERS = [
    ("open", "Open"),
    ("awaiting_payment", "Awaiting payment"),
    ("fee_paid", "Fee paid"),
    ("consulted", "Consulted"),
    ("closed", "Closed"),
    ("all", "All"),
]

CLOSED_STATUSES = [
    ConsultationRequest.Status.BECAME_MEMBER,
    ConsultationRequest.Status.DECLINED,
    ConsultationRequest.Status.CLOSED,
]


def filter_consultation_requests(status: str = "open", query: str = "", assigned: str = ""):
    qs = ConsultationRequest.objects.select_related("assigned_to")
    if status == "open":
        qs = qs.open()
    elif status == "closed":
        qs = qs.filter(status__in=CLOSED_STATUSES)
    elif status in ConsultationRequest.Status.values:
        qs = qs.filter(status=status)

    if assigned == "none":
        qs = qs.filter(assigned_to__isnull=True)
    elif assigned.isdigit():
        qs = qs.filter(assigned_to_id=int(assigned))

    query = query.strip()
    if query:
        qs = qs.filter(
            Q(full_name__icontains=query)
            | Q(preferred_name__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
        )
    return qs


def _lock(consultation):
    return ConsultationRequest.objects.select_for_update().get(pk=consultation.pk)


@transaction.atomic
def mark_fee_paid(consultation, *, by, amount, currency, method, reference=""):
    consultation = _lock(consultation)
    if consultation.status != ConsultationRequest.Status.AWAITING_PAYMENT:
        raise InvalidTransitionError("Only requests awaiting payment can be marked as paid.")
    consultation.status = ConsultationRequest.Status.FEE_PAID
    consultation.fee_paid_at = timezone.now()
    consultation.fee_marked_paid_by = by
    consultation.fee_amount = amount
    consultation.fee_currency = currency
    consultation.fee_payment_method = method
    consultation.fee_reference = reference
    consultation.save(update_fields=[
        "status", "fee_paid_at", "fee_marked_paid_by", "fee_amount",
        "fee_currency", "fee_payment_method", "fee_reference", "updated_at",
    ])
    return consultation


@transaction.atomic
def decline_request(consultation, *, by):
    consultation = _lock(consultation)
    if not consultation.is_open:
        raise InvalidTransitionError("This request is already closed.")
    consultation.status = ConsultationRequest.Status.DECLINED
    consultation.save(update_fields=["status", "updated_at"])
    return consultation


@transaction.atomic
def assign_request(consultation, *, to):
    consultation = _lock(consultation)
    if not consultation.is_open:
        raise InvalidTransitionError("Closed requests can't be reassigned.")
    consultation.assigned_to = to
    consultation.save(update_fields=["assigned_to", "updated_at"])
    return consultation


def requests_visible_to(user):
    """Admin sees everything; matchmakers only what's assigned to them."""
    qs = ConsultationRequest.objects.all()
    if user.has_perm("base.view_all_consultation_requests"):
        return qs
    return qs.filter(assigned_to=user)