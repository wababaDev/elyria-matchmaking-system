"""
Matchmaker Notes: a staff-only, dated log for each member.

- Never deleted (there is no delete anywhere, and the admin refuses deletes).
- Editing keeps the earlier text in MemberNoteRevision, with who changed it and when.
- Author and time are stamped automatically. author=None means the system wrote it.
"""
from django.conf import settings
from django.db import models

from domain.base.models import TimeStampedModel
from domain.matchmaking.models.client import Client


class MemberNote(TimeStampedModel):
    class Kind(models.TextChoices):
        OBSERVATION = "observation", "Observation"
        DISCREPANCY = "discrepancy", "Discrepancy"
        PROFILE_CHANGE = "profile_change", "Profile change"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    class Category(models.TextChoices):  # observations
        COMMUNICATION = "communication", "Communication"
        READINESS = "readiness", "Readiness"
        EXPECTATIONS = "expectations", "Expectations"
        PRESENTATION = "presentation", "Presentation"
        OTHER = "other", "Other"

    class Difference(models.TextChoices):  # discrepancies
        WORDING = "wording", "Wording only"
        MATERIAL = "material", "Material"
        DEALBREAKER = "dealbreaker", "Contradicts a deal-breaker or blocked status"

    class FollowUp(models.TextChoices):  # discrepancies
        CALL = "call", "Ask on next call"
        MESSAGE = "message", "Ask by message"
        UPDATE_FORM = "update_form", "Ask client to update the form"
        DOCUMENTS = "documents", "Verify with documents"
        FOUNDER = "founder", "Escalate to the Founder"
        NONE = "none", "No action"

    class Outcome(models.TextChoices):  # closing a discrepancy or reviewing a change
        NO_CONCERN = "no_concern", "Clarified, no concern"
        PROFILE_UPDATED = "profile_updated", "Clarified, profile updated"
        REVIEWED = "reviewed", "Reviewed"
        UNRESOLVED = "unresolved", "Closed, unresolved"

    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="notes")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="member_notes"
    )

    # What it's about: observation category, the compared item, or the profile field that changed
    category = models.CharField(max_length=20, choices=Category.choices, blank=True)
    subject = models.CharField("Compared item / field", max_length=200, blank=True)
    body = models.TextField("Note", blank=True)

    # Discrepancy: the two answers. Profile change: before and after.
    first_value = models.TextField(blank=True)
    second_value = models.TextField(blank=True)
    difference = models.CharField(max_length=20, choices=Difference.choices, blank=True)
    follow_up = models.CharField(max_length=20, choices=FollowUp.choices, blank=True)
    follow_up_due = models.DateField(null=True, blank=True)
    affects_matching = models.BooleanField(default=False)

    # Open items (discrepancies, profile changes) get closed with an outcome and a note
    status = models.CharField(max_length=10, choices=Status.choices, blank=True)
    outcome = models.CharField(max_length=20, choices=Outcome.choices, blank=True)
    resolution = models.TextField(blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="member_notes_closed"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} on {self.client}"

    @property
    def is_open(self):
        return self.status == self.Status.OPEN

    @property
    def by_system(self):
        return self.author_id is None


class MemberNoteRevision(models.Model):
    """The text a note had before an edit."""
    note = models.ForeignKey(MemberNote, on_delete=models.PROTECT, related_name="revisions")
    previous_body = models.TextField()
    edited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="member_note_edits")
    edited_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-edited_at"]