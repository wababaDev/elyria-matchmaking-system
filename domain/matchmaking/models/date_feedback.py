"""
Date feedback: one record per member per date, written by that member's own matchmaker.
Never shown to the other member's matchmaker; anything about the other member is passed on
verbally, and their matchmaker writes their own notes after looking into it.
"""
from django.conf import settings
from django.db import models

from domain.base.models import TimeStampedModel
from domain.matchmaking.models.client import Client
from domain.matchmaking.models.pairing import Pairing


class DateFeedback(TimeStampedModel):
    # ---------- Choices

    class WentAhead(models.TextChoices):
        YES = "yes", "Yes, it went ahead"
        RESCHEDULED = "rescheduled", "Rescheduled"
        CANCELLED = "cancelled", "Cancelled"
        NO_SHOW = "no_show", "No-show"

    class CancelledBy(models.TextChoices):
        CLIENT = "client", "The client"
        MATCH = "match", "The match"
        MATCHMAKER = "matchmaker", "A matchmaker"
        OTHER = "other", "Other"

    class YesNoUnsure(models.TextChoices):
        YES = "yes", "Yes"
        NO = "no", "No"
        UNSURE = "unsure", "Unsure"

    class MatchedProfile(models.TextChoices):
        YES = "yes", "Yes"
        MOSTLY = "mostly", "Mostly"
        NO = "no", "No"

    class Respected(models.TextChoices):
        YES = "yes", "Yes"
        PARTLY = "partly", "Partly"
        NO = "no", "No"

    class WantsNext(models.TextChoices):
        SECOND_DATE = "another_date", "Another date"
        PAUSE = "pause", "A pause"
        END = "end", "To end it"

    class Severity(models.TextChoices):
        NONE = "", "No concerns"
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        SERIOUS = "serious", "Serious (Admin is emailed)"

    class Outcome(models.TextChoices):
        ANOTHER_DATE = "another_date", "Another date"
        ENDED_BY_CLIENT = "ended_by_client", "Ended by client"
        ENDED_BY_MATCH = "ended_by_match", "Ended by match"
        ONGOING = "ongoing", "Ongoing"
        PAUSE = "pause", "Pause"

    BEHAVIOUR_FLAGS = [
        ("late", "Late or kept them waiting"),
        ("disrespectful", "Disrespectful"),
        ("pressure", "Pressured them"),
        ("inappropriate", "Inappropriate comments or behaviour"),
        ("misrepresented", "Misrepresented themselves"),
        ("alcohol", "Too much alcohol"),
        ("safety", "Safety concern"),
        ("other", "Other"),
    ]

    # ---------- Which date, whose feedback
    pairing = models.ForeignKey(Pairing, on_delete=models.PROTECT, related_name="feedback")
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="date_feedback")
    date_number = models.PositiveSmallIntegerField(default=1)

    # ---------- 1. Facts of the introduction
    date = models.DateField("Date")
    setting = models.CharField("Setting", max_length=20, choices=Pairing.Setting.choices, blank=True)
    setting_other = models.CharField("Other setting", max_length=120, blank=True)
    duration_minutes = models.PositiveSmallIntegerField("Length (minutes)", null=True, blank=True)

    # ---------- 2. Did it go ahead
    went_ahead = models.CharField("Did it go ahead?", max_length=20, choices=WentAhead.choices)
    cancelled_by = models.CharField("Who cancelled or didn't show?", max_length=20, choices=CancelledBy.choices, blank=True)
    cancel_reason = models.TextField("Why", blank=True)

    # ---------- 3. What the client says (their words)
    meet_again = models.CharField("Would meet again?", max_length=10, choices=YesNoUnsure.choices, blank=True)
    meet_again_why = models.TextField("Why", blank=True)
    went_well = models.TextField("What went well", blank=True)
    concerns = models.TextField("What concerned them", blank=True)
    matched_profile = models.CharField("Did the person match their profile?", max_length=10, choices=MatchedProfile.choices, blank=True)
    profile_differed = models.TextField("What differed", blank=True)
    deal_breaker = models.TextField("Anything they see as a deal-breaker?", blank=True)
    felt_respected = models.CharField("Did they feel respected and comfortable?", max_length=10, choices=Respected.choices, blank=True)
    felt_respected_notes = models.TextField("In their words", blank=True)
    wants_next = models.CharField("What they want next", max_length=20, choices=WantsNext.choices, blank=True)
    change_next_time = models.TextField("What they'd change in the next introduction", blank=True)

    # ---------- 4. Matchmaker's own record (separate from what the client said)
    behaviour_flags = models.JSONField("Behaviour flags", default=list, blank=True)
    flag_severity = models.CharField("Severity", max_length=10, choices=Severity.choices, blank=True)
    flag_notes = models.TextField("Details", blank=True)
    profile_vs_report = models.TextField(
        "Differences between the match's profile and what the client reported", blank=True
    )

    # ---------- 5. Outcome
    outcome = models.CharField("Outcome", max_length=20, choices=Outcome.choices)

    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="date_feedback_recorded")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="date_feedback_updated"
    )

    class Meta:
        ordering = ["pairing", "date_number"]
        constraints = [
            models.UniqueConstraint(fields=["pairing", "client", "date_number"], name="one_feedback_per_member_per_date"),
        ]

    def __str__(self):
        return f"{self.introduction_id} feedback for {self.client}"

    @property
    def introduction_id(self):
        return f"INT-{self.pairing_id:04d}-{self.date_number}"

    @property
    def setting_label(self):
        if self.setting == Pairing.Setting.OTHER and self.setting_other:
            return self.setting_other
        return self.get_setting_display()

    @property
    def flag_labels(self):
        labels = dict(self.BEHAVIOUR_FLAGS)
        return [labels.get(f, f) for f in self.behaviour_flags]