from django import forms

from domain.matchmaking.models import ConsultationRequest
from domain.matchmaking.models.consultation_request import NOT_ELIGIBLE_MESSAGE


class ConsultationRequestForm(forms.ModelForm):
    # Honeypot: hidden from people, bots tend to fill it in
    website = forms.CharField(required=False)

    class Meta:
        model = ConsultationRequest
        fields = [
            "full_name", "preferred_name", "gender", "age", "seeking",
            "relationship_status", "relationship_status_other", "location", "nationality", "occupation",
            "email", "phone",
        ]

        def clean(self):
            cleaned = super().clean()
            if (cleaned.get("relationship_status") == ConsultationRequest.RelationshipStatus.OTHER
                    and not cleaned.get("relationship_status_other", "").strip()):
                self.add_error("relationship_status_other", "Please tell us a little more.")
            return cleaned

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean_relationship_status(self):
        value = self.cleaned_data["relationship_status"]
        if value in ConsultationRequest.BLOCKED_STATUSES:
            raise forms.ValidationError(NOT_ELIGIBLE_MESSAGE, code="not_eligible")
        return value