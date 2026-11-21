from django.db import models

from domain.base.models import TimeStampedModel
from domain.matchmaking.models.consultation_request import ConsultationRequest


class MembershipTierQuerySet(models.QuerySet):
    def for_members(self):
        """Tiers a member can be given, renewed or upgraded onto. Elite Grade has its own path (Elite cases)."""
        return self.filter(is_active=True).exclude(name__icontains="elite")

class MembershipTier(TimeStampedModel):
    """Managed by Admin. Changes apply to new memberships and renewals only."""
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
    # Introductions = different people a member actually meets. Matches (cards to choose from) are unlimited.
    max_introductions = models.PositiveSmallIntegerField(
        "Introductions included", null=True, blank=True,
        help_text="How many different people a member on this tier can be introduced to. Leave blank for unlimited.",
    )
    # Hold Time: how long a member can pause, in total, per membership term (resets on renewal or upgrade)
    allows_hold = models.BooleanField(
        "Allows Hold Time", default=False,
        help_text="Tick if members on this tier can put their membership on hold.",
    )
    hold_weeks = models.PositiveSmallIntegerField(
        "Hold Time (weeks)", null=True, blank=True,
        help_text="Total weeks on hold per membership term, across all holds. Starts again on renewal or upgrade.",
    )
    display_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True, help_text="Untick to retire a tier without affecting existing members.")
    objects = MembershipTierQuerySet.as_manager()
    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name

    @property
    def hold_days(self):
        """Days of Hold Time per term. 0 = no Hold Time on this tier."""
        if not self.allows_hold:
            return 0
        return (self.hold_weeks or 0) * 7

    @property
    def is_elite(self):
       """Same rule as elite_service.elite_tier(): the name contains 'Elite'."""
       return "elite" in self.name.lower()