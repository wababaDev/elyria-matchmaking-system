from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property

from domain.base.models import TimeStampedModel
from domain.matchmaking.models.client import Client
from domain.matchmaking.models.consultation_request import ConsultationRequest
from domain.matchmaking.models.membership_tier import MembershipTier

EXPIRING_SOON_DAYS = 30


class Membership(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CANCELLED = "cancelled", "Cancelled"

    client = models.OneToOneField(
        Client, on_delete=models.CASCADE, related_name="membership"
    )
    tier = models.ForeignKey(
        MembershipTier, on_delete=models.PROTECT, related_name="memberships"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    start_date = models.DateField()
    end_date = models.DateField()
    # Total introductions this membership has paid for, across renewals and upgrades.
    # Empty = use the tier's number (so new memberships need nothing set). Unlimited if the tier has none.
    introductions_allowed = models.PositiveSmallIntegerField(null=True, blank=True)
    # Last renewal reminder sent for the current end date (60 / 30 / 14). Cleared when renewed.
    renewal_reminder_days = models.PositiveSmallIntegerField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    cancellation_reason = models.TextField(blank=True)

    def __str__(self):
        return f"{self.client} ({self.tier})"

    @property
    def is_current(self):
        return (
            self.status == self.Status.ACTIVE and self.end_date >= timezone.localdate()
        )

    @property
    def display_status(self):
        """active / expiring / expired / cancelled, for badges and filters."""
        if self.status == self.Status.CANCELLED:
            return "cancelled"
        today = timezone.localdate()
        if self.end_date < today:
            return "expired"
        if self.end_date <= today + timedelta(days=EXPIRING_SOON_DAYS):
            return "expiring"
        return "active"

    @property
    def days_left(self):
        return (self.end_date - timezone.localdate()).days

    @property
    def introductions_allowance(self):
        """None means unlimited."""
        if self.introductions_allowed is not None:
            return self.introductions_allowed
        return self.tier.max_introductions

    @cached_property
    def current_hold(self):
        return self.holds.filter(ended_on__isnull=True).first()

    @property
    def on_hold(self):
        return self.current_hold is not None


class MembershipHold(TimeStampedModel):
    """
    Hold Time: the member has officially asked not to be set on any dates for a while.
    When the hold ends, the membership end date moves forward by the days it lasted.
    """

    class Reason(models.TextChoices):
        GRIEVANCE = "grievance", "Grievance / bereavement"
        WORK = "work", "Work commitment"
        TRAVEL = "travel", "Travel"
        PERSONAL = "personal", "Personal reasons"
        OTHER = "other", "Other"

    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="holds")
    reason = models.CharField(max_length=20, choices=Reason.choices)
    note = models.CharField(max_length=300, blank=True)
    started_on = models.DateField()
    ended_on = models.DateField(null=True, blank=True)
    days_added = models.PositiveIntegerField(default=0)
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="holds_started"
    )
    ended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="holds_ended"
    )

    class Meta:
        ordering = ["-started_on", "-created_at"]

    def __str__(self):
        return f"Hold for {self.membership.client} from {self.started_on}"

    @property
    def days_so_far(self):
        return ((self.ended_on or timezone.localdate()) - self.started_on).days


class MembershipPayment(TimeStampedModel):
    """One row per payment, so renewals build a history instead of overwriting."""

    class Kind(models.TextChoices):
        NEW = "new", "New membership"
        RENEWAL = "renewal", "Renewal"
        UPGRADE = "upgrade", "Upgrade"

    membership = models.ForeignKey(
        Membership, on_delete=models.CASCADE, related_name="payments"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(
        max_length=3, choices=ConsultationRequest.Currency.choices
    )
    method = models.CharField(
        max_length=20, choices=ConsultationRequest.PaymentMethod.choices
    )
    reference = models.CharField(max_length=100, blank=True)
    paid_on = models.DateField(default=timezone.localdate)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["-paid_on", "-created_at"]