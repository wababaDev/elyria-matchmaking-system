from django import forms

from domain.base.forms.base_forms import BootstrapFormMixin
from domain.base.models import Groups
from domain.matchmaking.models import MembershipTier
from domain.website.models import SiteDocument, SiteSettings
from domain.website.models.site_document import validate_pdf

ROLE_CHOICES = [(Groups.MATCHMAKER, "Matchmaker"), (Groups.ADMIN, "Admin")]


class SiteSettingsForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = SiteSettings
        fields = [
            "consultation_fee", "consultation_fee_currency", "bank_details", "mobile_money_details",
            "default_consultation_location", "contact_phone", "contact_email", "business_address",
        ]
        widgets = {
            "bank_details": forms.Textarea(attrs={"rows": 3}),
            "mobile_money_details": forms.Textarea(attrs={"rows": 3}),
        }


class StaffCreateForm(BootstrapFormMixin, forms.Form):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    job_title = forms.CharField(max_length=100, required=False, help_text="e.g. Senior Matchmaker")
    role = forms.ChoiceField(choices=ROLE_CHOICES, initial=Groups.MATCHMAKER)

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class StaffUpdateForm(BootstrapFormMixin, forms.Form):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    job_title = forms.CharField(max_length=100, required=False)
    role = forms.ChoiceField(choices=ROLE_CHOICES)
    is_active = forms.BooleanField(required=False, label="Active (can sign in)")


class MembershipTierForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = MembershipTier
        fields = ["name", "price", "currency", "duration_months", "display_order", "is_active"]


class PrivacyPolicyUploadForm(BootstrapFormMixin, forms.Form):
    file = forms.FileField(
        label="Privacy Policy (PDF)",
        validators=[validate_pdf],
        widget=forms.ClearableFileInput(attrs={"accept": "application/pdf"}),
    )