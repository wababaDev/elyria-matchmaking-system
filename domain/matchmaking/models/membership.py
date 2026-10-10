from django.conf import settings
from django.db import models
from django.utils import timezone

from domain.base.models import TimeStampedModel
from domain.matchmaking.models.client import Client
from domain.matchmaking.models.consultation_request import ConsultationRequest
from domain.matchmaking.models.membership_tier import MembershipTier

class Membership(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CANCELLED = "cancelled", "Cancelled"

    client = models.OneToOneField(Client, on_delete=models.CASCADE, related_name="membership")
    tier = models.ForeignKey(MembershipTier, on_delete=models.PROTECT, related_name="memberships")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    start_date = models.DateField()
    end_date = models.DateField()
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)

    def __str__(self):
        return f"{self.client} ({self.tier})"

    @property
    def is_current(self):
        return self.status == self.Status.ACTIVE and self.end_date >= timezone.localdate()


class MembershipPayment(TimeStampedModel):
    """One row per payment, so renewals build a history instead of overwriting."""

    class Kind(models.TextChoices):
        NEW = "new", "New membership"
        RENEWAL = "renewal", "Renewal"

    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="payments")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, choices=ConsultationRequest.Currency.choices)
    method = models.CharField(max_length=20, choices=ConsultationRequest.PaymentMethod.choices)
    reference = models.CharField(max_length=100, blank=True)
    paid_on = models.DateField(default=timezone.localdate)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-paid_on", "-created_at"]