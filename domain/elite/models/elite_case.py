"""
Elite Grade: a client asks Elyria to discreetly approach one named person.
Visible to Admin (and, from Part 2, the case's handler) only. Not registered in Django admin,
and there is no export, by design.
"""
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from domain.base.models import TimeStampedModel

VERIFY_LINK_HOURS = 48
ABANDONED_AFTER_DAYS = 30
MAX_DOCUMENT_SIZE = 15 * 1024 * 1024  # 15 MB
DOCUMENT_TYPES = (".pdf", ".jpg", ".jpeg", ".png", ".docx")


def _private_storage():
    from domain.base.storage import PrivateMediaStorage

    return PrivateMediaStorage()


def _document_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "pdf"
    return f"elite/{instance.case.reference}/{instance.kind}-{secrets.token_hex(3)}.{ext}"


def validate_document(file):
    if not file.name.lower().endswith(DOCUMENT_TYPES):
        raise ValidationError("Upload a PDF, Word document or photo (JPG/PNG).")
    if file.size > MAX_DOCUMENT_SIZE:
        raise ValidationError("The file must be 15 MB or smaller.")


def new_token():
    return secrets.token_urlsafe(32)


class EliteCase(TimeStampedModel):
    class Status(models.TextChoices):
        AWAITING_EMAIL = "awaiting_email", "Awaiting email confirmation"
        AWAITING_DOCUMENTS = "awaiting_documents", "Awaiting documents"
        UNDER_REVIEW = "under_review", "Under review"
        DECLINED = "declined", "Declined"
        APPROVED = "approved", "Approved: awaiting payment"

    OPEN_STATUSES = [Status.AWAITING_EMAIL, Status.AWAITING_DOCUMENTS, Status.UNDER_REVIEW, Status.APPROVED]

    # The client (applicant)
    full_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.AWAITING_EMAIL)

    # E1: email confirmation
    verify_token = models.CharField(max_length=64, unique=True, default=new_token)
    verify_sent_at = models.DateTimeField(default=timezone.now)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    documents_sent_at = models.DateTimeField(null=True, blank=True)

    # E2/E3: signed documents arrive by email; Admin records them
    nda_received = models.BooleanField(default=False)
    declaration_received = models.BooleanField(default=False)
    request_form_received = models.BooleanField(default=False)
    documents_confirmed_at = models.DateTimeField(null=True, blank=True)
    documents_confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="elite_documents_confirmed"
    )

    # E4: Admin's review
    check_known_to_client = models.BooleanField("Known to the client", default=False)
    check_no_prior_rejection = models.BooleanField("No prior rejection", default=False)
    check_no_power_imbalance = models.BooleanField("No power imbalance", default=False)
    check_identity_verified = models.BooleanField("Identity verified", default=False)
    check_suitability = models.BooleanField("Suitability assessment complete", default=False)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="elite_cases_decided"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} {self.full_name}"

    @property
    def reference(self):
        return f"ELT-{self.pk:04d}" if self.pk else "ELT-new"

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES

    @property
    def verify_link_expired(self):
        return timezone.now() > self.verify_sent_at + timedelta(hours=VERIFY_LINK_HOURS)

    @property
    def all_documents_received(self):
        return self.nda_received and self.declaration_received and self.request_form_received

    @property
    def all_checks_done(self):
        return all([
            self.check_known_to_client, self.check_no_prior_rejection, self.check_no_power_imbalance,
            self.check_identity_verified, self.check_suitability,
        ])


class EliteDocument(TimeStampedModel):
    """A signed document or form the client emailed back, uploaded by Admin. Stored privately."""

    class Kind(models.TextChoices):
        NDA = "nda", "NDA"
        DECLARATION = "declaration", "Declaration of Respectful Intent"
        REQUEST_FORM = "request_form", "Confidential Introduction Request Form"
        OTHER = "other", "Other"

    case = models.ForeignKey(EliteCase, on_delete=models.CASCADE, related_name="documents")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    file = models.FileField(upload_to=_document_path, storage=_private_storage, validators=[validate_document])
    original_name = models.CharField(max_length=200, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} for {self.case.reference}"


class EliteCaseEvent(models.Model):
    """The case timeline. Append-only: entries can be added, never changed or deleted."""

    case = models.ForeignKey(EliteCase, on_delete=models.CASCADE, related_name="events")
    at = models.DateTimeField(default=timezone.now)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    text = models.TextField()

    class Meta:
        ordering = ["at", "pk"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Timeline entries can't be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Timeline entries can't be deleted.")


class EliteAccessLog(models.Model):
    """Every time staff open a case or one of its documents."""

    class Action(models.TextChoices):
        VIEW_CASE = "view_case", "Opened case"
        VIEW_DOCUMENT = "view_document", "Opened document"

    case = models.ForeignKey(EliteCase, on_delete=models.CASCADE, related_name="access_log")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    action = models.CharField(max_length=20, choices=Action.choices)
    detail = models.CharField(max_length=200, blank=True)
    at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-at"]