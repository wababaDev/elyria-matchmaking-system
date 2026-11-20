from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.functional import cached_property

from domain.base.models import TimeStampedModel
from domain.matchmaking.models.client import Client
from domain.matchmaking.models.consultation_request import ConsultationRequest
from domain.matchmaking.models.membership_tier import MembershipTier

EXPIRING_SOON_DAYS = 30


def weeks_text(days):
    """42 -> '6 weeks', 10 -> '1 week 3 days', 0 -> '0 days'."""
    weeks, rest = divmod(max(days, 0), 7)
    parts = []
    if weeks:
        parts.append(f"{weeks} week{'s' if weeks != 1 else ''}")
    if rest or not weeks:
        parts.append(f"{rest} day{'s' if rest != 1 else ''}")
    return " ".join(parts)


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
    # Hold Time is counted from here. Set on renewal or upgrade, so the allowance starts again.
    # Empty = count from start_date.
    hold_term_start = models.DateField(null=True, blank=True)
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

    # ------------------------------------------------------------ Hold Time

    @cached_property
    def current_hold(self):
        """The hold that covers today, if any."""
        return self.holds.active_on(timezone.localdate()).first()

    @property
    def on_hold(self):
        return self.current_hold is not None

    @cached_property
    def upcoming_hold(self):
        """A hold that's been booked but hasn't started yet."""
        return self.holds.filter(started_on__gt=timezone.localdate()).order_by("started_on").first()

    @property
    def hold_allowance_days(self):
        return self.tier.hold_days

    @property
    def can_hold(self):
        return self.status == self.Status.ACTIVE and self.hold_allowance_days > 0

    def term_holds(self):
        return self.holds.filter(started_on__gte=self.hold_term_start or self.start_date)

    @property
    def hold_days_used(self):
        return sum(hold.length_days for hold in self.term_holds())

    @property
    def hold_days_left(self):
        return max(self.hold_allowance_days - self.hold_days_used, 0)

    @property
    def hold_summary(self):
        """'6 weeks per term · 2 weeks used · 4 weeks left'"""
        return (
            f"{weeks_text(self.hold_allowance_days)} per term · "
            f"{weeks_text(self.hold_days_used)} used · {weeks_text(self.hold_days_left)} left"
        )


class MembershipHoldQuerySet(models.QuerySet):
    def active_on(self, day):
        """Holds that cover `day`. An empty end date is an old open-ended hold."""
        return self.filter(started_on__lte=day).filter(Q(ended_on__isnull=True) | Q(ended_on__gte=day))


class MembershipHold(TimeStampedModel):
    """
    Hold Time: the member has officially asked not to be set on any dates for a while.
    Saved with a first and last day; the membership end date moves forward by those days straight away.
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
    started_on = models.DateField()  # first day on hold
    ended_on = models.DateField(null=True, blank=True)  # last day on hold (empty only on old holds)
    days_added = models.PositiveIntegerField(default=0)
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="holds_started"
    )
    ended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="holds_ended"
    )

    objects = MembershipHoldQuerySet.as_manager()

    class Meta:
        ordering = ["-started_on", "-created_at"]

    def __str__(self):
        return f"Hold for {self.membership.client} from {self.started_on}"

    @property
    def length_days(self):
        """Days on hold, counting the first and the last day: 1–14 Dec is 14 days."""
        last = self.ended_on or timezone.localdate()
        return max((last - self.started_on).days + 1, 0)

    @property
    def length_text(self):
        return weeks_text(self.length_days)

    @property
    def days_so_far(self):
        """Days on hold up to today (for the 'On hold' notice)."""
        last = min(self.ended_on or timezone.localdate(), timezone.localdate())
        return max((last - self.started_on).days + 1, 0)


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