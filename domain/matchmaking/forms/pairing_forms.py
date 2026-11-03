from django import forms

from domain.matchmaking.models import ClientProfile, Pairing

TEXT = {"class": "form-control"}
SELECT = {"class": "form-select"}


class FindMatchForm(forms.Form):
    age_min = forms.IntegerField(label="Age from", required=False, min_value=20, max_value=90,
                                 widget=forms.NumberInput(attrs=TEXT))
    age_max = forms.IntegerField(label="Age to", required=False, min_value=20, max_value=90,
                                 widget=forms.NumberInput(attrs=TEXT))
    city = forms.CharField(label="City", required=False, max_length=100,
                           widget=forms.TextInput(attrs={**TEXT, "placeholder": "e.g. Lusaka"}))
    children = forms.ChoiceField(label="Has children", required=False,
                                 choices=[("", "Any"), ("yes", "Yes"), ("no", "No")],
                                 widget=forms.Select(attrs=SELECT))
    religion = forms.ChoiceField(label="Faith", required=False,
                                 choices=[("", "Any")] + list(ClientProfile.Religion.choices),
                                 widget=forms.Select(attrs=SELECT))


class ProposePairingForm(forms.Form):
    candidate = forms.IntegerField(widget=forms.HiddenInput)
    note = forms.CharField(
        label="Note for your member",
        widget=forms.Textarea(attrs={**TEXT, "rows": 3,
                                     "placeholder": "Why this person could suit your member. They will read this."}),
    )
    profession = forms.CharField(label="Profession, as your member will see it", required=False, max_length=120,
                                 widget=forms.TextInput(attrs={**TEXT, "placeholder": "e.g. Works in engineering"}))
    location = forms.CharField(label="Location, as your member will see it", required=False, max_length=120,
                               widget=forms.TextInput(attrs={**TEXT, "placeholder": "e.g. Lusaka"}))


class ApprovalForm(forms.Form):
    approve = forms.ChoiceField(choices=[("yes", "Approve"), ("no", "Decline")])
    reason = forms.CharField(required=False, max_length=300)


class PresentForm(forms.Form):
    note = forms.CharField()
    profession = forms.CharField(required=False, max_length=120)
    location = forms.CharField(required=False, max_length=120)


class IntroductionForm(forms.Form):
    introduced_on = forms.DateField()
    setting = forms.ChoiceField(choices=[("", "Setting")] + list(Pairing.Setting.choices), required=False)
    minutes = forms.IntegerField(min_value=10, max_value=600, required=False)
    setting_other = forms.CharField(max_length=120, required=False)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("setting") == Pairing.Setting.OTHER and not cleaned.get("setting_other", "").strip():
            self.add_error("setting_other", "Say what the other setting is.")
        return cleaned


class ClosePairingForm(forms.Form):
    reason = forms.CharField(max_length=300)