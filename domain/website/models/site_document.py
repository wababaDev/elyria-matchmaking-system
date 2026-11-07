from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify
from domain.base.models import TimeStampedModel

MAX_PDF_SIZE = 10 * 1024 * 1024  # 10 MB


def validate_pdf(file):
    if not file.name.lower().endswith(".pdf"):
        raise ValidationError("Please upload a PDF file.")
    if file.size > MAX_PDF_SIZE:
        raise ValidationError("The file must be 10 MB or smaller.")
    header = file.read(5)
    file.seek(0)
    if header != b"%PDF-":
        raise ValidationError("This file doesn't look like a valid PDF.")



def document_path(instance, filename):
    """documents/<kind>/<original-name>.pdf, e.g. documents/elite_nda/elyria-nda-v3.pdf"""
    name = filename.rsplit(".", 1)[0]
    return f"documents/{instance.kind}/{slugify(name) or instance.kind}.pdf"

class SiteDocument(TimeStampedModel):
    """Documents Admin uploads; one current file per kind. Replacing a file takes effect straight away."""

    class Kind(models.TextChoices):
        PRIVACY_POLICY = "privacy_policy", "Privacy Policy"
        # Elite Grade: emailed to applicants, never linked publicly
        ELITE_TIER = "elite_tier", "Elite Grade document"
        ELITE_NDA = "elite_nda", "Client Confidentiality & Non-Disclosure Agreement"
        ELITE_DECLARATION = "elite_declaration", "Declaration of Respectful Intent"
        ELITE_REQUEST_FORM = "elite_request_form", "Confidential Introduction Request Form"
        ELITE_INDEMNITY = "elite_indemnity", "Indemnity Notice"
        ELITE_ACKNOWLEDGEMENT = "elite_acknowledgement", "Introduction Acknowledgement"

    # Attached to the email sent once an applicant confirms their email (E1/E2)
    ELITE_EMAIL_KINDS = [Kind.ELITE_TIER, Kind.ELITE_NDA, Kind.ELITE_DECLARATION, Kind.ELITE_REQUEST_FORM]
    # All Elite documents, in the order shown in Settings → Documents
    ELITE_KINDS = ELITE_EMAIL_KINDS + [Kind.ELITE_INDEMNITY, Kind.ELITE_ACKNOWLEDGEMENT]

    kind = models.CharField(max_length=40, choices=Kind.choices, unique=True)
    file = models.FileField(upload_to=document_path, validators=[validate_pdf])
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    def __str__(self):
        return self.get_kind_display()

    @classmethod
    def current(cls, kind):
        return cls.objects.filter(kind=kind).first()