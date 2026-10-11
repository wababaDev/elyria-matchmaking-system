from django.conf import settings
from django.db import models

from domain.base.models import TimeStampedModel
from domain.matchmaking.models.membership_tier import MembershipTier


class Enquiry(TimeStampedModel):
    """'Learn More' question from a Membership tier card."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ANSWERED = "answered", "Answered"

    tier = models.ForeignKey(
        MembershipTier, on_delete=models.SET_NULL, null=True, blank=True, related_name="enquiries"
    )
    question = models.TextField()
    first_name = models.CharField(max_length=80)
    contact = models.CharField("Phone number or email", max_length=150)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    answered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    response_note = models.TextField(blank=True, help_text="How it was answered, for the team's reference.")

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "enquiries"

    def __str__(self):
        return f"{self.first_name}: {self.tier or 'General'}"

    @property
    def contact_is_email(self):
        return "@" in self.contact