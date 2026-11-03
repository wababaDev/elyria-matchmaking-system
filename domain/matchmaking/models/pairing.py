"""
Matching: one Pairing record shared by both members.

Order:
1. A's matchmaker proposes A + B. Nobody sees anything yet.
2. If B belongs to another matchmaker, B's matchmaker reviews A's full profile and approves (or declines).
3. A's matchmaker now sees B's full profile, talks it through with B's matchmaker, and either
   presents B to A or closes the pairing. (Same matchmaker: steps 2 and 3 are skipped.)
4. A sees B's card and decides. "Not interested" ends it; B is never shown or told.
5. If A is interested, B's matchmaker presents A's card to B. B decides.
6. Both interested = mutual interest; the matchmakers arrange the introduction.
Declines are never deleted. Members are only ever told "This introduction will not go ahead."
"""
from django.conf import settings
from django.db import models

from domain.base.models import TimeStampedModel
from domain.matchmaking.models.client import Client

OPEN_PAIRING_LIMIT = 3  # a warning only, never a block


class Pairing(TimeStampedModel):
    class Approval(models.TextChoices):
        NOT_NEEDED = "not_needed", "Not needed (same matchmaker)"
        PENDING = "pending", "Waiting for approval"
        APPROVED = "approved", "Approved"
        DECLINED = "declined", "Declined"

    class DecisionA(models.TextChoices):
        PENDING = "pending", "Pending"
        INTERESTED = "interested", "Interested"
        NOT_INTERESTED = "not_interested", "Not interested"

    class DecisionB(models.TextChoices):
        NOT_PRESENTED = "not_presented", "Not yet presented"
        PENDING = "pending", "Pending"
        INTERESTED = "interested", "Interested"
        NOT_INTERESTED = "not_interested", "Not interested"

    class Setting(models.TextChoices):
        COFFEE = "coffee", "Coffee"
        MEAL = "meal", "Meal"
        VIDEO = "video", "Video call"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        PRESENTED_TO_B = "presented_to_b", "Presented to client B"
        MUTUAL = "mutual", "Mutual interest"
        CLOSED = "closed", "Closed"

    client_a = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="pairings_as_a")
    client_b = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="pairings_as_b")
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pairings_added")

    # B's matchmaker approves before A sees anything (skipped when it's the same matchmaker)
    approval = models.CharField(max_length=20, choices=Approval.choices, default=Approval.NOT_NEEDED)
    approval_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="pairings_approved"
    )
    approval_at = models.DateTimeField(null=True, blank=True)

    # A's matchmaker presents B to A (second approval). Set at once when it's the same matchmaker.
    a_presented_at = models.DateTimeField(null=True, blank=True)
    a_presented_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="pairings_presented_to_a"
    )

    a_decision = models.CharField(max_length=20, choices=DecisionA.choices, default=DecisionA.PENDING)
    a_decided_at = models.DateTimeField(null=True, blank=True)
    b_decision = models.CharField(max_length=20, choices=DecisionB.choices, default=DecisionB.NOT_PRESENTED)
    b_presented_at = models.DateTimeField(null=True, blank=True)
    b_presented_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="pairings_presented"
    )
    b_decided_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROPOSED)

    # What each member reads: written per pairing by that member's matchmaker
    note_for_a = models.TextField("Note for client A", blank=True)        # why B suits A
    b_profession = models.CharField("B's profession, as shown to A", max_length=120, blank=True)
    b_location = models.CharField("B's location, as shown to A", max_length=120, blank=True)
    note_for_b = models.TextField("Note for client B", blank=True)        # why A suits B
    a_profession = models.CharField("A's profession, as shown to B", max_length=120, blank=True)
    a_location = models.CharField("A's location, as shown to B", max_length=120, blank=True)

    # The first date: set by the matchmaker once both said yes. Later dates live on DateFeedback.
    introduced_on = models.DateField(null=True, blank=True)
    introduction_setting = models.CharField(max_length=20, choices=Setting.choices, blank=True)
    introduction_minutes = models.PositiveSmallIntegerField("Planned length (minutes)", null=True, blank=True)
    introduction_setting_other = models.CharField("Setting (other)", max_length=120, blank=True)

    @property
    def introduction_setting_label(self):
        if self.introduction_setting == self.Setting.OTHER and self.introduction_setting_other:
            return self.introduction_setting_other
        return self.get_introduction_setting_display()
    closed_at = models.DateTimeField(null=True, blank=True)
    # Staff who closed or declined it. Empty when a member said "not interested".
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="pairings_closed"
    )
    closed_reason = models.CharField(max_length=300, blank=True)  # staff only

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.client_a} + {self.client_b}"

    @property
    def is_open(self):
        return self.status != self.Status.CLOSED

    @property
    def visible_to_a(self):
        return self.a_presented_at is not None

    @property
    def waiting_to_present_to_a(self):
        """Approved by B's matchmaker; A's matchmaker hasn't presented it to A yet."""
        return self.is_open and self.approval == self.Approval.APPROVED and self.a_presented_at is None

    def other(self, client):
        return self.client_b if client.pk == self.client_a_id else self.client_a

    def side(self, client):
        return "a" if client.pk == self.client_a_id else "b"


class MatchAccessLog(models.Model):
    """Who searched for or opened which member while matching. Kept for Admin to review."""

    class Action(models.TextChoices):
        SEARCH = "search", "Searched for candidates"
        PROPOSE = "propose", "Proposed a pairing"
        VIEW_PAIRING = "view_pairing", "Opened a pairing"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="match_access_logs")
    action = models.CharField(max_length=20, choices=Action.choices)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, null=True, blank=True, related_name="match_access_entries")
    detail = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]