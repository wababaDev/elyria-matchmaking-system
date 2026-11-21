"""
The Official Consultation Record: filled in during the call, then locked for good.

Once locked it is the baseline that later profile answers are compared against,
so it can never be edited again. Anything learned later becomes a note.
"""
from django.db import transaction
from django.utils import timezone

from domain.matchmaking.consultation_questions import BEFORE_YOU_BEGIN, REQUIRED_TO_LOCK, TEXT_FIELDS
from domain.matchmaking.models import Consultation, ConsultationRequest
from domain.matchmaking.services.consultation_request_service import InvalidTransitionError

Status = ConsultationRequest.Status

# The record can be written once the fee is paid, and finished after the call
OPEN_STATUSES = (Status.FEE_PAID, Status.CONSULTED)
EDITABLE_FIELDS = BEFORE_YOU_BEGIN + TEXT_FIELDS + ["readiness"]


def _lock_request(consultation_request):
    return ConsultationRequest.objects.select_for_update().get(pk=consultation_request.pk)


def _record_for(consultation_request):
    if consultation_request.status not in OPEN_STATUSES:
        raise InvalidTransitionError("The consultation record can be filled in once the fee has been paid.")
    consultation, _ = Consultation.objects.get_or_create(request=consultation_request)
    if consultation.is_locked:
        raise InvalidTransitionError("This consultation record is locked and can't be changed.")
    return consultation


@transaction.atomic
def save_consultation_record(consultation_request, *, data, by):
    """Save the draft. Nothing is required yet."""
    consultation = _record_for(_lock_request(consultation_request))
    for field in EDITABLE_FIELDS:
        if field in data:
            value = data[field]
            setattr(consultation, field, value.strip() if isinstance(value, str) else value)
    if consultation.readiness and not consultation.readiness_set_at:
        consultation.readiness_set_at = timezone.now()
        consultation.readiness_set_by = by
    consultation.save()
    return consultation


def missing_to_lock(consultation):
    """Labels of what still has to be filled in before locking."""
    return [
        str(Consultation._meta.get_field(f).verbose_name)
        for f in REQUIRED_TO_LOCK
        if not (getattr(consultation, f) or "").strip()
    ]


@transaction.atomic
def lock_consultation_record(consultation_request, *, by):
    """
    Lock the record for good. If the consultation wasn't marked as held yet,
    this also marks it as held (the call has clearly happened).
    """
    consultation_request = _lock_request(consultation_request)
    consultation = _record_for(consultation_request)

    missing = missing_to_lock(consultation)
    if missing:
        raise InvalidTransitionError("Before locking, fill in: " + ", ".join(missing) + ".")

    now = timezone.now()
    consultation.record_locked_at = now
    consultation.record_locked_by = by
    fields = ["record_locked_at", "record_locked_by", "updated_at"]

    if consultation_request.status == Status.FEE_PAID:
        consultation.held_at = consultation.held_at or now
        consultation.conducted_by = consultation.conducted_by or by
        fields += ["held_at", "conducted_by"]
        consultation_request.status = Status.CONSULTED
        consultation_request.save(update_fields=["status", "updated_at"])

    consultation.save(update_fields=fields)
    return consultation


@transaction.atomic
def set_readiness(consultation_request, *, readiness, by):
    """
    The readiness score is due within 24 hours of the call, so it may come after locking.
    It can be set once; after that it is part of the locked baseline.
    """
    consultation = Consultation.objects.select_for_update().filter(request=consultation_request).first()
    if not consultation:
        raise InvalidTransitionError("There is no consultation record yet.")
    if consultation.readiness:
        raise InvalidTransitionError("The readiness score has already been recorded.")
    if readiness not in Consultation.Readiness.values:
        raise InvalidTransitionError("Choose Low, Medium or High.")
    consultation.readiness = readiness
    consultation.readiness_set_at = timezone.now()
    consultation.readiness_set_by = by
    consultation.save(update_fields=["readiness", "readiness_set_at", "readiness_set_by", "updated_at"])
    return consultation