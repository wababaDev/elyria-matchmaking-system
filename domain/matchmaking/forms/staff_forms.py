from django import forms
from django.contrib.auth import get_user_model

from domain.base.models import STAFF_GROUPS
from domain.matchmaking.models import ConsultationRequest


def staff_members():
    return (
        get_user_model()
        .objects.filter(is_active=True, groups__name__in=STAFF_GROUPS)
        .distinct()
        .order_by("first_name", "last_name")
    )


class FeePaymentForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    currency = forms.ChoiceField(
        choices=ConsultationRequest.Currency.choices,
        initial=ConsultationRequest.Currency.ZMW,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    method = forms.ChoiceField(
        choices=ConsultationRequest.PaymentMethod.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    reference = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Optional"}
        ),
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

class ConsultationNotesForm(forms.Form):
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 8, "class": "form-control"}),
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
