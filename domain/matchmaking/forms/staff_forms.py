from django import forms
from django.contrib.auth import get_user_model

from domain.base.models import STAFF_GROUPS
from domain.base.models import Groups
from domain.matchmaking.models import ConsultationRequest
from domain.matchmaking.models import ConsultationRequest, Membership
from domain.matchmaking.models import ConsultationRequest, MembershipTier
from domain.matchmaking.utils import add_months
from domain.base.forms.base_forms import BootstrapFormMixin
from domain.matchmaking.forms.consultation_request_form import ConsultationRequestForm

def staff_members():
    """People who can be assigned requests and members: Matchmakers and Admin, never Finance."""
    return (
        get_user_model().objects
        .filter(is_active=True, groups__name__in=[Groups.MATCHMAKER, Groups.ADMIN])
        .distinct()
        .order_by("first_name", "last_name")
    )


class FeePaymentForm(forms.Form):
    """How it was paid. The amount comes from Settings (consultation) or the tier (membership)."""
    method = forms.ChoiceField(
        choices=ConsultationRequest.PaymentMethod.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    reference = forms.CharField(
        label="Transaction ID",
        max_length=100, required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional"}),
    )

class BookConsultationForm(forms.Form):
    scheduled_for = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local", "class": "form-control"},
            format="%Y-%m-%dT%H:%M",
        ),
    )
    location = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "e.g. Video call, or venue agreed on the call"}
        ),
    )

class AssignForm(forms.Form):
    assigned_to = forms.ModelChoiceField(
        queryset=None, required=False, empty_label="Unassigned"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["assigned_to"]
        field.queryset = staff_members()
        field.label_from_instance = lambda user: user.full_name
        field.widget.attrs["class"] = "form-select form-select-sm"

class PricedTierMixin:
    """Only active tiers, and only ones with a price set."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tier"].queryset = MembershipTier.objects.filter(is_active=True)

    def clean_tier(self):
        tier = self.cleaned_data["tier"]
        if tier.price is None:
            raise forms.ValidationError(
                f"{tier.name} has no price yet. Set it in Settings → Membership tiers first."
            )
        return tier
class ConfirmMembershipForm(PricedTierMixin, FeePaymentForm):
    tier = forms.ModelChoiceField(queryset=MembershipTier.objects.none())
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))

    field_order = ["tier", "start_date", "method", "reference"]


class ChangeSignInEmailForm(forms.Form):
    email = forms.EmailField(
        label="New sign-in email",
        widget=forms.EmailInput(attrs={"class": "form-control", "autocomplete": "off"}),
    )

    
def one_year_from(day):
    try:
        return day.replace(year=day.year + 1)
    except ValueError:  # 29 Feb
        return day.replace(year=day.year + 1, day=28)


class RenewMembershipForm(BootstrapFormMixin, PricedTierMixin, FeePaymentForm):
    tier = forms.ModelChoiceField(queryset=MembershipTier.objects.none())

    field_order = ["tier", "method", "reference"]

class CancelMembershipForm(BootstrapFormMixin, forms.Form):
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), label="Reason for cancelling")


class ConsultationRequestDetailsForm(BootstrapFormMixin, ConsultationRequestForm):
    """Staff correcting what the applicant submitted: same rules as the public form."""
    website = None  # drop the public form's honeypot field

    class Meta(ConsultationRequestForm.Meta):
        fields = [
            "full_name", "preferred_name", "email", "phone", "gender", "seeking", "age",
            "relationship_status", "relationship_status_other",
            "location", "nationality", "occupation",
        ]


class UndoFeePaidForm(forms.Form):
    reason = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Marked paid by mistake"}),
    )