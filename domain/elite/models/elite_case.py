"""
Elite Grade: a client asks Elyria to discreetly approach one named person.
Visible to Admin and the case's Case Handler only. Not registered in Django admin,
and there is no export, by design. The named person's details are stored encrypted and wiped
30 days after the case closes; only a fingerprint stays in the "do not approach" register.
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
        PAID = "paid", "Paid: ready for outreach"
        OUTREACH_SENT = "outreach_sent", "Outreach sent: waiting for reply"
        AGREED = "agreed", "Agreed to hear more: awaiting acknowledgement"
        INTRODUCTION = "introduction", "Identity shared: introduction next"
        INTRODUCED = "introduced", "Introduced: feedback"
        BRONZE_OFFERED = "bronze_offered", "Not proceeding: Bronze offered"
        CLOSED = "closed", "Closed"

    OPEN_STATUSES = [
        Status.AWAITING_EMAIL, Status.AWAITING_DOCUMENTS, Status.UNDER_REVIEW, Status.APPROVED,
        Status.PAID, Status.OUTREACH_SENT, Status.AGREED, Status.INTRODUCTION, Status.INTRODUCED,
        Status.BRONZE_OFFERED,
    ]
    # Cases where the Case Handler has the next step
    HANDLER_STATUSES = [
        Status.APPROVED, Status.PAID, Status.OUTREACH_SENT, Status.AGREED, Status.INTRODUCTION, Status.INTRODUCED,
        Status.BRONZE_OFFERED,
    ]

    class ContactType(models.TextChoices):
        PHONE = "phone", "Phone / WhatsApp"
        EMAIL = "email", "Email"
        MUTUAL = "mutual", "Through a mutual contact"
        OTHER = "other", "Other"

    class Outcome(models.TextChoices):
        DECLINED = "declined", "The person declined"
        NO_RESPONSE = "no_response", "No response within 14 days"
        NOT_SIGNED = "not_signed", "Agreed, but didn't sign the acknowledgement"

    class IntroResult(models.TextChoices):
        TOOK_PLACE = "took_place", "Took place"
        CANCELLED = "cancelled", "Cancelled"
        NO_SHOW = "no_show", "No-show"

    class ClosingOutcome(models.TextChoices):
        CONTINUING = "continuing", "Connection continuing"
        NOT_CONTINUING = "not_continuing", "Not continuing"
        DID_NOT_HAPPEN = "did_not_happen", "Introduction didn't happen"

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

    # E6: Case Handler, fee and Indemnity Notice
    handler = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="elite_cases_handled"
    )
    handler_assigned_at = models.DateTimeField(null=True, blank=True)
    fee_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    fee_currency = models.CharField(max_length=3, blank=True)
    fee_method = models.CharField(max_length=20, blank=True)
    fee_reference = models.CharField(max_length=100, blank=True)
    fee_paid_on = models.DateField(null=True, blank=True)
    fee_recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="elite_fees_recorded"
    )
    indemnity_received = models.BooleanField(default=False)

    # E7: the named person (encrypted; wiped 30 days after closing)
    person_name_enc = models.TextField(blank=True)
    person_contact_type = models.CharField(max_length=20, choices=ContactType.choices, blank=True)
    person_contact_enc = models.TextField(blank=True)
    person_email_enc = models.TextField(blank=True)  # given with consent once they agree (for introduction alerts)
    person_details_wiped_at = models.DateTimeField(null=True, blank=True)

    # E7/E8: outreach
    outreach_bounces = models.PositiveSmallIntegerField(default=0)
    outreach_delivered_on = models.DateField(null=True, blank=True)
    reply_due_on = models.DateField(null=True, blank=True)
    reply_reminder_sent = models.BooleanField(default=False)
    reply_ended_notice_sent = models.BooleanField(default=False)
    acknowledgement_received = models.BooleanField(default=False)
    outcome = models.CharField(max_length=20, choices=Outcome.choices, blank=True)

    # E10: the introduction (stays in the case: neither person becomes a member)
    intro_at = models.DateTimeField("Date and time", null=True, blank=True)
    intro_venue = models.CharField("Venue", max_length=200, blank=True)
    intro_video_link = models.URLField("Video link", blank=True)
    intro_alerts_sent_at = models.DateTimeField(null=True, blank=True)
    coached_client = models.BooleanField("Client coached on dating etiquette", default=False)
    guidelines_client = models.BooleanField("Guidelines read to the client", default=False)
    coached_person = models.BooleanField("Named person coached on dating etiquette", default=False)
    guidelines_person = models.BooleanField("Guidelines read to the named person", default=False)
    intro_result = models.CharField(max_length=20, choices=IntroResult.choices, blank=True)
    intro_took_place_on = models.DateField(null=True, blank=True)
    closing_outcome = models.CharField(max_length=20, choices=ClosingOutcome.choices, blank=True)

    # E11: Bronze offer and closing
    bronze_offered_at = models.DateTimeField(null=True, blank=True)
    bronze_accepted = models.BooleanField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

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
    def person_name(self):
        from domain.elite.crypto import decrypt
        return decrypt(self.person_name_enc)

    @property
    def person_contact(self):
        from domain.elite.crypto import decrypt
        return decrypt(self.person_contact_enc)

    @property
    def person_email(self):
        from domain.elite.crypto import decrypt
        return decrypt(self.person_email_enc)

    @property
    def has_person(self):
        return bool(self.person_name_enc)

    @property
    def fee_recorded(self):
        return self.fee_paid_on is not None

    @property
    def reply_overdue(self):
        return (
            self.status == self.Status.OUTREACH_SENT and self.reply_due_on is not None
            and timezone.localdate() > self.reply_due_on
        )

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
        INDEMNITY = "indemnity", "Indemnity Notice"
        ACKNOWLEDGEMENT = "acknowledgement", "Introduction Acknowledgement"
        OTHER = "other", "Other"

    # Contain the named person's details: deleted with them, 30 days after the case closes
    NAMED_PERSON_KINDS = [Kind.REQUEST_FORM, Kind.ACKNOWLEDGEMENT, Kind.OTHER]

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


class SuppressionEntry(models.Model):
    """
    "Do not approach again": a person who declined, didn't respond, or didn't sign.
    Only keyed fingerprints of their name and contact are kept, never the details themselves.
    """
    name_fingerprint = models.CharField(max_length=64, db_index=True)
    contact_fingerprint = models.CharField(max_length=64, blank=True, db_index=True)
    reason = models.CharField(max_length=20, choices=EliteCase.Outcome.choices)
    case_reference = models.CharField(max_length=20)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "suppression entries"


class EliteFeedback(models.Model):
    """
    One feedback form for one person: A (client after the introduction), B (named person after the
    introduction), C (client, case closed without an introduction). Sent by a private one-time link.
    Answers are staff-only (Admin and the Case Handler) and are never edited.
    """

    class Form(models.TextChoices):
        A = "A", "Form A: client, after the introduction"
        B = "B", "Form B: named person, after the introduction"
        C = "C", "Form C: client, closed without an introduction"

    case = models.ForeignKey(EliteCase, on_delete=models.CASCADE, related_name="feedback")
    form = models.CharField(max_length=1, choices=Form.choices)
    token = models.CharField(max_length=64, unique=True, default=new_token)
    send_on = models.DateField()
    remind_on = models.DateField()
    closes_on = models.DateField()
    sent_at = models.DateTimeField(null=True, blank=True)
    reminded_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.CharField(max_length=20, blank=True)  # "client" / "named person"
    answers = models.JSONField(default=dict, blank=True)
    red_flag = models.BooleanField(default=False)
    red_flag_reasons = models.JSONField(default=list, blank=True)
    referral_lead = models.BooleanField(default=False)

    class Meta:
        ordering = ["case", "form"]
        constraints = [models.UniqueConstraint(fields=["case", "form"], name="one_elite_form_per_case")]

    def __str__(self):
        return f"{self.case.reference} Form {self.form}"

    @property
    def is_open(self):
        return self.completed_at is None and timezone.localdate() <= self.closes_on

    @property
    def state(self):
        if self.completed_at:
            return "completed"
        if timezone.localdate() > self.closes_on:
            return "closed"
        if self.sent_at:
            return "sent"
        return "scheduled"


class EliteFeedbackNote(models.Model):
    """Admin's dated note on a feedback form. Append-only, like the timeline."""
    feedback = models.ForeignKey(EliteFeedback, on_delete=models.CASCADE, related_name="notes")
    by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    at = models.DateTimeField(default=timezone.now)
    text = models.TextField()

    class Meta:
        ordering = ["at"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Notes can't be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Notes can't be deleted.")