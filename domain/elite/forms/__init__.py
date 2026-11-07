from django import forms

from domain.elite.models import EliteDocument
from domain.elite.models.elite_case import validate_document
from domain.elite.services.elite_service import CHECKS


class ApplyForm(forms.Form):
    """E1 on the website: name and email only."""
    full_name = forms.CharField(label="Full name", max_length=150)
    email = forms.EmailField(label="Email address")
    phone = forms.CharField(label="Phone number (optional)", max_length=40, required=False)
    understood = forms.BooleanField(
        label="I understand that Elite Grade is by approval only, and that Elyria may decline any request without giving reasons.",
    )
    # Honeypot: hidden from people, bots fill it in
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))


class DocumentUploadForm(forms.Form):
    kind = forms.ChoiceField(choices=EliteDocument.Kind.choices, widget=forms.Select(attrs={"class": "form-select"}))
    file = forms.FileField(validators=[validate_document], widget=forms.ClearableFileInput(attrs={"class": "form-control"}))


CHECKBOX = forms.CheckboxInput(attrs={"class": "form-check-input"})


class DocumentsReceivedForm(forms.Form):
    nda = forms.BooleanField(label="NDA signed", required=False, widget=CHECKBOX)
    declaration = forms.BooleanField(label="Declaration of Respectful Intent signed", required=False, widget=CHECKBOX)
    request_form = forms.BooleanField(
        label="Confidential Introduction Request Form completed and signed", required=False, widget=CHECKBOX,
    )


class ChecksForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field, label in CHECKS:
            self.fields[field] = forms.BooleanField(label=label, required=False)


class DecisionForm(forms.Form):
    decision = forms.ChoiceField(choices=[("approve", "Approve"), ("decline", "Decline"), ("more_info", "More information needed")])
    note = forms.CharField(required=False, max_length=2000)