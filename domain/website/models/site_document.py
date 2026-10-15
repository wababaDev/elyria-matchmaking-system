from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

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


class SiteDocument(TimeStampedModel):
    """Public documents Admin uploads; one current file per kind."""

    class Kind(models.TextChoices):
        PRIVACY_POLICY = "privacy_policy", "Privacy Policy"

    kind = models.CharField(max_length=40, choices=Kind.choices, unique=True)
    file = models.FileField(upload_to="documents/", validators=[validate_pdf])
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    def __str__(self):
        return self.get_kind_display()

    @classmethod
    def current(cls, kind):
        return cls.objects.filter(kind=kind).first()