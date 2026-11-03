from django import forms

from domain.matchmaking.models.date_feedback import DateFeedback

TEXT = {"class": "form-control"}
AREA = {"class": "form-control", "rows": 2}
SELECT = {"class": "form-select"}


class DateFeedbackForm(forms.ModelForm):
    behaviour_flags = forms.MultipleChoiceField(
        label="Behaviour flags", required=False,
        choices=DateFeedback.BEHAVIOUR_FLAGS, widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = DateFeedback
        fields = [
            # 1. Facts
            "date", "setting", "setting_other", "duration_minutes",
            # 2. Did it go ahead
            "went_ahead", "cancelled_by", "cancel_reason",
            # 3. What the client says
            "meet_again", "meet_again_why", "went_well", "concerns",
            "matched_profile", "profile_differed", "deal_breaker",
            "felt_respected", "felt_respected_notes", "wants_next", "change_next_time",
            # 4. Matchmaker's record
            "behaviour_flags", "flag_severity", "flag_notes", "profile_vs_report",
            # 5. Outcome
            "outcome",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", **TEXT}, format="%Y-%m-%d"),
            "duration_minutes": forms.NumberInput(attrs={**TEXT, "placeholder": "e.g. 90"}),
            "setting_other": forms.TextInput(attrs={**TEXT, "placeholder": "e.g. Walk in the park"}),
            "setting": forms.Select(attrs=SELECT),
            "went_ahead": forms.Select(attrs=SELECT),
            "cancelled_by": forms.Select(attrs=SELECT),
            "meet_again": forms.Select(attrs=SELECT),
            "matched_profile": forms.Select(attrs=SELECT),
            "felt_respected": forms.Select(attrs=SELECT),
            "wants_next": forms.Select(attrs=SELECT),
            "flag_severity": forms.Select(attrs=SELECT),
            "outcome": forms.Select(attrs=SELECT),
            "cancel_reason": forms.Textarea(attrs=AREA),
            "meet_again_why": forms.Textarea(attrs={**AREA, "placeholder": "In their words, quotes where possible"}),
            "went_well": forms.Textarea(attrs=AREA),
            "concerns": forms.Textarea(attrs=AREA),
            "profile_differed": forms.Textarea(attrs=AREA),
            "deal_breaker": forms.Textarea(attrs=AREA),
            "felt_respected_notes": forms.Textarea(attrs=AREA),
            "change_next_time": forms.Textarea(attrs=AREA),
            "flag_notes": forms.Textarea(attrs=AREA),
            "profile_vs_report": forms.Textarea(attrs=AREA),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Blank first option on the optional choices
        for name in ["setting", "cancelled_by", "meet_again", "matched_profile", "felt_respected", "wants_next"]:
            self.fields[name].choices = [("", "—")] + list(self.fields[name].choices)[1:]
        self.fields["went_ahead"].choices = [("", "Choose…")] + list(DateFeedback.WentAhead.choices)
        self.fields["outcome"].choices = [("", "Choose…")] + list(DateFeedback.Outcome.choices)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("setting") == "other" and not cleaned.get("setting_other", "").strip():
            self.add_error("setting_other", "Say what the other setting is.")
        elif cleaned.get("setting") != "other":
            cleaned["setting_other"] = ""
        went_ahead = cleaned.get("went_ahead")
        if went_ahead in (DateFeedback.WentAhead.CANCELLED, DateFeedback.WentAhead.NO_SHOW) and not cleaned.get("cancelled_by"):
            self.add_error("cancelled_by", "Say who cancelled or didn't show.")
        if went_ahead == DateFeedback.WentAhead.YES and not cleaned.get("meet_again"):
            self.add_error("meet_again", "Record whether they'd meet again.")
        if cleaned.get("flag_severity") and not cleaned.get("behaviour_flags"):
            self.add_error("behaviour_flags", "Tick at least one flag, or set severity to No concerns.")
        return cleaned