from django.conf import settings
from django.db import models

from domain.base.models import TimeStampedModel
from domain.matchmaking.models.consultation_request import ConsultationRequest


class Client(TimeStampedModel):
    """A confirmed member. The profile fields arrive in week 6."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="client")
    consultation_request = models.OneToOneField(
        ConsultationRequest, on_delete=models.PROTECT, related_name="client"
    )
    full_name = models.CharField(max_length=150)
    preferred_name = models.CharField(max_length=80)
    matchmaker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clients",
    )

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name

    @property
    def consultation(self):
        """The consultation notes travel with the client via the original request."""
        return getattr(self.consultation_request, "consultation", None)