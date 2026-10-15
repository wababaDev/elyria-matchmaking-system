import re

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from domain.base.forms.base_forms import BootstrapFormMixin
from domain.matchmaking.models import Enquiry, MembershipTier

PHONE_RE = re.compile(r"^\+?[\d\s\-()]{7,20}$")


class EnquiryForm(forms.ModelForm):
    website = forms.CharField(required=False)  # honeypot
    # The card sends the tier's name (e.g. "Gold"), matched against Settings → Membership tiers
    tier = forms.ModelChoiceField(
        queryset=MembershipTier.objects.all(), to_field_name="name", required=False
    )

    class Meta:
        model = Enquiry
        fields = ["tier", "question", "first_name", "contact"]

    def clean_contact(self):
        value = self.cleaned_data["contact"].strip()
        if "@" in value:
            try:
                validate_email(value)
            except ValidationError:
                raise ValidationError("Please enter a valid email address.")
            return value.lower()
        if not PHONE_RE.match(value) or sum(c.isdigit() for c in value) < 7:
            raise ValidationError("Please enter a valid phone number or email address.")
        return value


class AnswerEnquiryForm(BootstrapFormMixin, forms.Form):
    response_note = forms.CharField(
        required=False,
        label="How was it answered? (optional)",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "e.g. Called her, sent the Gold brochure"}),
    )