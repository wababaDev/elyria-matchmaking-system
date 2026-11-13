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
    person_contact_other_enc = models.TextField(blank=True)
    person_email_enc = models.TextField(blank=True)  # given with consent once they agree (for introduction alerts)
    person_met_where_enc = models.TextField(blank=True)  # where the client says they first met (from the request form)
    person_occupation_enc = models.TextField(blank=True)  # occupation or workplace, if known
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
    def person_contact_label(self):
        """'Phone / WhatsApp', 'Email', ... or, for Other, what the handler typed (e.g. 'Workplace address')."""
        from domain.elite.crypto import decrypt
        if self.person_contact_type == self.ContactType.OTHER and self.person_contact_other_enc:
            return decrypt(self.person_contact_other_enc)
        return self.get_person_contact_type_display()
    
    @property
    def person_met_where(self):
        from domain.elite.crypto import decrypt
        return decrypt(self.person_met_where_enc)
 
    @property
    def person_occupation(self):
        from domain.elite.crypto import decrypt
        return decrypt(self.person_occupation_enc)
 
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
        CLIENT_REPLY = "client_reply", "Client's reply (more information)"
        OTHER = "other", "Other"

    # Contain the named person's details: deleted with them, 30 days after the case closes
    NAMED_PERSON_KINDS = [Kind.REQUEST_FORM, Kind.ACKNOWLEDGEMENT, Kind.CLIENT_REPLY, Kind.OTHER]

    case = models.ForeignKey(EliteCase, on_delete=models.CASCADE, related_name="documents")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    file = models.FileField(upload_to=_document_path, storage=_private_storage, validators=[validate_document])
    original_name = models.CharField(max_length=200, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} for {self.case.reference}"


class EliteInfoRequest(models.Model):
    """
    "More information needed" during review: the question emailed to the client, and what came back.
    The reply arrives at info@; Admin records a short summary here (and can upload the reply itself as a
    case document). While a question is open, the case can't be approved.
    """
 
    case = models.ForeignKey(EliteCase, on_delete=models.CASCADE, related_name="info_requests")
    question = models.TextField()
    asked_at = models.DateTimeField(default=timezone.now)
    asked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    answer = models.TextField(blank=True)  # a short summary; the named person's details go in the uploaded reply
    no_answer = models.BooleanField(default=False)
    answered_at = models.DateTimeField(null=True, blank=True)
    answered_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
 
    class Meta:
        ordering = ["asked_at"]
 
    def __str__(self):
        return f"{self.case.reference}: question of {self.asked_at:%d %b %Y}"
 
    @property
    def is_open(self):
        return self.answered_at is None
    
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
    "Do not approach again": a person who declined, didn't respond, or didn't sign (E8, E9, E11).
    Kept after the named person's other details are deleted. As decided by the Client (D16): only the
    client's full name, the named person's full name, where they say they first met, and occupation or
    workplace. No phone or email. Stored encrypted; staff read them normally.
    The name fingerprint lets a new case with the same name be flagged; it warns, it doesn't block.
    """
    name_fingerprint = models.CharField(max_length=64, db_index=True)
    client_name_enc = models.TextField(blank=True)
    person_name_enc = models.TextField(blank=True)
    met_where_enc = models.TextField(blank=True)
    occupation_enc = models.TextField(blank=True)
    reason = models.CharField(max_length=20, choices=EliteCase.Outcome.choices)
    case_reference = models.CharField(max_length=20)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "suppression entries"

    def _read(self, value):
        from domain.elite.crypto import decrypt
        return decrypt(value) if value else ""
 
    @property
    def client_name(self):
        return self._read(self.client_name_enc)
 
    @property
    def person_name(self):
        return self._read(self.person_name_enc)
 
    @property
    def met_where(self):
        return self._read(self.met_where_enc)
 
    @property
    def occupation(self):
        return self._read(self.occupation_enc)


class EliteFeedback(models.Model):
    """
    Answers to one of the client's feedback forms, asked by the Case Handler on a call and typed in here.
    A: the client after the introduction. B: the named person after the introduction.
    C: the client when the case closed without an introduction. Staff only; every save goes on the timeline.
    """
 
    class Form(models.TextChoices):
        A = "A", "Form A: client, after the introduction"
        B = "B", "Form B: named person, after the introduction"
        C = "C", "Form C: client, closed without an introduction"
 
    case = models.ForeignKey(EliteCase, on_delete=models.CASCADE, related_name="feedback")
    form = models.CharField(max_length=1, choices=Form.choices)
    answers = models.JSONField(default=dict, blank=True)
    red_flag = models.BooleanField(default=False)
    red_flag_reasons = models.JSONField(default=list, blank=True)
    referral_lead = models.BooleanField(default=False)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")  # last saved by
    recorded_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
 
    class Meta:
        ordering = ["case", "form"]
        constraints = [models.UniqueConstraint(fields=["case", "form"], name="one_elite_form_per_case")]
 
    def __str__(self):
        return f"{self.case.reference} Form {self.form}"