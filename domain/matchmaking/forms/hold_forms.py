from django import forms
from django.utils import timezone

from domain.matchmaking.models.membership import MembershipHold

DATE = {"type": "date", "class": "form-control"}


class StartHoldForm(forms.Form):
    reason = forms.ChoiceField(choices=MembershipHold.Reason.choices, widget=forms.Select(attrs={"class": "form-select"}))
    note = forms.CharField(
        label="Note (staff only)", required=False, max_length=300,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Asked by email on 2 Nov"}),
    )
    started_on = forms.DateField(label="First day on hold", initial=timezone.localdate, widget=forms.DateInput(attrs=DATE))
    ended_on = forms.DateField(label="Last day on hold", widget=forms.DateInput(attrs=DATE))

    def clean(self):
        data = super().clean()
        start, end = data.get("started_on"), data.get("ended_on")
        if start and end and end < start:
            self.add_error("ended_on", "The last day can't be before the first day.")
        return data


class EndHoldForm(forms.Form):
    # Empty when cancelling a hold that hasn't started yet
    back_on = forms.DateField(
        label="Back from hold on", required=False, initial=timezone.localdate,
        widget=forms.DateInput(attrs=DATE),
    )