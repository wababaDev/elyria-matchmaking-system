from django import forms

from domain.matchmaking.consultation_questions import BEFORE_YOU_BEGIN, TEXT_FIELDS
from domain.matchmaking.models import Consultation


class ConsultationRecordForm(forms.ModelForm):
    """Every box on the Official Consultation Record. Nothing is required for a draft."""

    class Meta:
        model = Consultation
        fields = BEFORE_YOU_BEGIN + TEXT_FIELDS + ["readiness"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.required = False
            if name in BEFORE_YOU_BEGIN:
                field.widget = forms.RadioSelect(attrs={"class": "form-check-input"})
                field.choices = [c for c in field.choices if c[0] != ""]
            elif name == "readiness":
                field.widget.attrs["class"] = "form-select"
                field.choices = [("", "Not scored yet")] + [c for c in field.choices if c[0] != ""]
            else:
                rows = 6 if name in ("notes", "follow_up_questions") else 3
                field.widget = forms.Textarea(attrs={"rows": rows, "class": "form-control"})


class ReadinessForm(forms.Form):
    readiness = forms.ChoiceField(
        choices=Consultation.Readiness.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )