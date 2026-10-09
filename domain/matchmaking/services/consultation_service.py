from django.db import transaction
from django.utils import timezone

from domain.matchmaking.models import Consultation, ConsultationRequest
from domain.matchmaking.services.consultation_request_service import InvalidTransitionError
from notification.services.consultation_emails import notify_consultation_booked

Status = ConsultationRequest.Status


def _lock(consultation_request):
    return ConsultationRequest.objects.select_for_update().get(pk=consultation_request.pk)


@transaction.atomic
def book_consultation(consultation_request, *, scheduled_for, location="", by):
    consultation_request = _lock(consultation_request)
    if consultation_request.status != Status.FEE_PAID:
        raise InvalidTransitionError("A consultation can only be booked once the fee has been paid.")
    consultation, _ = Consultation.objects.get_or_create(request=consultation_request)
    
    location = location.strip()
    if consultation.scheduled_for == scheduled_for and consultation.location == location:
       return consultation  # nothing changed: no email

    rebooked = consultation.scheduled_for is not None
    consultation.scheduled_for = scheduled_for
    consultation.location = location
    consultation.save(update_fields=["scheduled_for", "location", "updated_at"])
    transaction.on_commit(lambda: notify_consultation_booked(consultation, rebooked=rebooked))
    return consultation


@transaction.atomic
def save_consultation_notes(consultation_request, *, notes, by):
    consultation_request = _lock(consultation_request)
    if consultation_request.status not in (Status.FEE_PAID, Status.CONSULTED):
        raise InvalidTransitionError("Notes can only be added once the fee has been paid.")
    consultation, _ = Consultation.objects.get_or_create(request=consultation_request)
    consultation.notes = notes.strip()
    consultation.save(update_fields=["notes", "updated_at"])
    return consultation


@transaction.atomic
def mark_consulted(consultation_request, *, by):
    consultation_request = _lock(consultation_request)
    if consultation_request.status != Status.FEE_PAID:
        raise InvalidTransitionError("Only requests with a paid fee can be marked as consulted.")
    consultation = Consultation.objects.filter(request=consultation_request).first()
    if not consultation or not consultation.notes.strip():
        raise InvalidTransitionError("Add the consultation notes before marking it as consulted.")

    consultation.held_at = timezone.now()
    consultation.conducted_by = by
    consultation.save(update_fields=["held_at", "conducted_by", "updated_at"])

    consultation_request.status = Status.CONSULTED
    consultation_request.save(update_fields=["status", "updated_at"])
    return consultation