from django import forms
from django.utils import timezone

from domain.matchmaking.models.membership import MembershipHold


class StartHoldForm(forms.Form):
    reason = forms.ChoiceField(choices=MembershipHold.Reason.choices, widget=forms.Select(attrs={"class": "form-select"}))
    note = forms.CharField(
        label="Note (staff only)", required=False, max_length=300,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Asked by email on 2 Nov"}),
    )
    started_on = forms.DateField(
        label="Hold starts", initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )


class EndHoldForm(forms.Form):
    ended_on = forms.DateField(
        label="Back from hold on", initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )