from django.conf import settings
from django.db import models

from domain.base.models import TimeStampedModel
from domain.matchmaking.models.consultation_request import ConsultationRequest


class Consultation(TimeStampedModel):
    """
    What staff found at the consultation.
    The request itself stays exactly as the applicant submitted it.
    """
    request = models.OneToOneField(
        ConsultationRequest, on_delete=models.CASCADE, related_name="consultation"
    )
    scheduled_for = models.DateTimeField(null=True, blank=True)
    location = models.CharField(
        max_length=200, blank=True,
        help_text="Where it will happen, e.g. Elyria office, video call, or an agreed venue.",
    )
    held_at = models.DateTimeField(null=True, blank=True)
    conducted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consultations_conducted",
    )
    # TODO: add structured fields once Elyria shares the Screening Guide
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"Consultation for {self.request.full_name}"