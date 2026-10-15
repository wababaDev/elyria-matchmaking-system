from django.db import models

from domain.base.models import TimeStampedModel
from domain.matchmaking.models.consultation_request import ConsultationRequest


class MembershipTier(TimeStampedModel):
    """Managed by Admin. Changes apply to new memberships only."""
    name = models.CharField(max_length=60, unique=True)
    price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Standard price. Leave blank if it's agreed case by case.",
    )
    currency = models.CharField(
        max_length=3, choices=ConsultationRequest.Currency.choices,
        default=ConsultationRequest.Currency.ZMW,
    )
    duration_months = models.PositiveSmallIntegerField(default=12)
    display_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True, help_text="Untick to retire a tier without affecting existing members.")

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name