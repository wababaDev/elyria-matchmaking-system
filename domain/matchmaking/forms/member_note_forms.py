from django import forms

from domain.matchmaking.models import MemberNote

TEXT = {"class": "form-control"}
SELECT = {"class": "form-select"}


class ObservationForm(forms.Form):
    category = forms.ChoiceField(choices=MemberNote.Category.choices, widget=forms.Select(attrs=SELECT))
    body = forms.CharField(
        label="Observation",
        widget=forms.Textarea(attrs={**TEXT, "rows": 4, "placeholder": "What was seen or heard, and when."}),
    )


class DiscrepancyForm(forms.Form):
    subject = forms.CharField(
        label="Compared item", max_length=200,
        widget=forms.TextInput(attrs={**TEXT, "placeholder": "e.g. Time since last relationship ended"}),
    )
    consultation_answer = forms.CharField(
        label="Said in consultation", required=False, widget=forms.Textarea(attrs={**TEXT, "rows": 2})
    )
    profile_answer = forms.CharField(
        label="Entered in the profile", required=False, widget=forms.Textarea(attrs={**TEXT, "rows": 2})
    )
    difference = forms.ChoiceField(
        label="Type of difference", choices=MemberNote.Difference.choices, widget=forms.Select(attrs=SELECT)
    )
    body = forms.CharField(
        label="What I noticed",
        widget=forms.Textarea(attrs={**TEXT, "rows": 3, "placeholder": "Facts only, e.g. “Consultation says three years. Form says eight months.”"}),
    )
    follow_up = forms.ChoiceField(choices=MemberNote.FollowUp.choices, widget=forms.Select(attrs=SELECT))
    follow_up_due = forms.DateField(
        label="Follow up by", required=False, widget=forms.DateInput(attrs={**TEXT, "type": "date"})
    )


class NoteEditForm(forms.Form):
    body = forms.CharField(widget=forms.Textarea(attrs={**TEXT, "rows": 3}))


class CloseNoteForm(forms.Form):
    outcome = forms.ChoiceField(choices=MemberNote.Outcome.choices, widget=forms.Select(attrs=SELECT))
    resolution = forms.CharField(
        label="What was done",
        widget=forms.Textarea(attrs={**TEXT, "rows": 2, "placeholder": "e.g. Asked on call 3 Nov. She meant 8 months; updated."}),
    )