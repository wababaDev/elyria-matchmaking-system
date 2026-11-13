from django import forms
from django.utils import timezone

from domain.elite.models import EliteCase, EliteDocument
from domain.elite.models.elite_case import validate_document
from domain.elite.services.elite_service import CHECKS


class ApplyForm(forms.Form):
    """E1 on the website: name and email only."""

    full_name = forms.CharField(label="Full name", max_length=150)
    email = forms.EmailField(label="Email address")
    phone = forms.CharField(
        label="Phone number (optional)", max_length=40, required=False
    )
    understood = forms.BooleanField(
        label="I understand that Elite Grade is by approval only, and that Elyria may decline any request without giving reasons.",
    )
    # Honeypot: hidden from people, bots fill it in
    website = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}),
    )


class DocumentUploadForm(forms.Form):
    kind = forms.ChoiceField(
        choices=EliteDocument.Kind.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    file = forms.FileField(
        validators=[validate_document],
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
    )


CHECKBOX = forms.CheckboxInput(attrs={"class": "form-check-input"})


class DocumentsReceivedForm(forms.Form):
    nda = forms.BooleanField(label="NDA signed", required=False, widget=CHECKBOX)
    declaration = forms.BooleanField(
        label="Declaration of Respectful Intent signed", required=False, widget=CHECKBOX
    )
    request_form = forms.BooleanField(
        label="Confidential Introduction Request Form completed and signed",
        required=False,
        widget=CHECKBOX,
    )


class ChecksForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field, label in CHECKS:
            self.fields[field] = forms.BooleanField(label=label, required=False)


class DecisionForm(forms.Form):
    decision = forms.ChoiceField(
        choices=[
            ("approve", "Approve"),
            ("decline", "Decline"),
            ("more_info", "More information needed"),
        ]
    )
    note = forms.CharField(required=False, max_length=2000)


# ---------------------------------------------------------------- Part 2a


def handler_choices():
    from django.contrib.auth import get_user_model

    from domain.base.models import Groups

    return (
        get_user_model()
        .objects.filter(
            is_active=True, groups__name__in=[Groups.MATCHMAKER, Groups.ADMIN]
        )
        .distinct()
        .order_by("first_name", "last_name")
    )


class HandlerChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, user):
        return user.full_name or user.email


class AssignHandlerForm(forms.Form):
    handler = HandlerChoiceField(
        queryset=None,
        label="Case Handler",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["handler"].queryset = handler_choices()


DATE_INPUT = {"type": "date", "class": "form-control"}


class FeeForm(forms.Form):
    """The amount isn't a field: it's the Elite Grade price from Settings → Membership tiers."""

    def __init__(self, *args, **kwargs):
        from domain.matchmaking.models import ConsultationRequest

        super().__init__(*args, **kwargs)
        self.fields["method"] = forms.ChoiceField(
            label="Paid by",
            choices=ConsultationRequest.PaymentMethod.choices,
            widget=forms.Select(attrs={"class": "form-select"}),
        )
        self.fields["reference"] = forms.CharField(
            label="Transaction reference",
            required=False,
            max_length=100,
            widget=forms.TextInput(attrs={"class": "form-control"}),
        )
        self.fields["paid_on"] = forms.DateField(
            label="Paid on",
            initial=timezone.localdate,
            widget=forms.DateInput(attrs=DATE_INPUT, format="%Y-%m-%d"),
        )


class PersonForm(forms.Form):
    name = forms.CharField(
        label="Their full name, as on the request form",
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    contact_type = forms.ChoiceField(
        label="Contact route",
        choices=EliteCase.ContactType.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    contact_other = forms.CharField(
        label="What kind of contact?",
        required=False,
        max_length=60,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "e.g. Workplace address"}
        ),
    )
    contact = forms.CharField(
        label="Contact details the client gave",
        max_length=200,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "e.g. +260 97…, name@…, or the mutual contact",
            }
        ),
    )
    met_where = forms.CharField(
        label="Where they say they first met",
        max_length=200,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "From the request form, e.g. a friend's wedding in Lusaka",
            }
        ),
    )
    occupation = forms.CharField(
        label="Occupation or workplace (if known)",
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    def clean(self):
        data = super().clean()
        if data.get("contact_type") == EliteCase.ContactType.OTHER:
            if not (data.get("contact_other") or "").strip():
                self.add_error(
                    "contact_other",
                    "Say what kind of contact it is, e.g. Workplace address.",
                )
        else:
            data["contact_other"] = ""
        return data


class OutreachForm(forms.Form):
    delivered = forms.ChoiceField(
        choices=[("yes", "Delivered"), ("no", "Bounced / didn't reach them")]
    )
    sent_on = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs=DATE_INPUT, format="%Y-%m-%d"),
    )


class AnswerForm(forms.Form):
    answer = forms.ChoiceField(
        choices=[
            ("agreed", "Agreed to hear more"),
            ("declined", "Declined"),
            ("no_response", "No response"),
        ]
    )
    person_email = forms.EmailField(
        required=False, widget=forms.EmailInput(attrs={"class": "form-control"})
    )


class SendAcknowledgementForm(forms.Form):
    person_email = forms.EmailField(
        label="Their email", widget=forms.EmailInput(attrs={"class": "form-control"})
    )


class AcknowledgementForm(forms.Form):
    signed = forms.ChoiceField(choices=[("yes", "Signed"), ("no", "Not signed")])
    person_email = forms.EmailField(
        required=False,
        label="Their email, if you don't have it yet (for introduction alerts)",
        widget=forms.EmailInput(attrs={"class": "form-control"}),
    )


class ConfirmForm(forms.Form):
    """For buttons that only confirm a step."""


class BronzeAnswerForm(forms.Form):
    accepted = forms.ChoiceField(choices=[("yes", "Accepted"), ("no", "Declined")])


# ---------------------------------------------------------------- Part 2b


class IntroductionForm(forms.Form):
    intro_at = forms.DateTimeField(
        label="Date and time",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local", "class": "form-control"},
            format="%Y-%m-%dT%H:%M",
        ),
    )
    venue = forms.CharField(
        label="Venue",
        required=False,
        max_length=200,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "e.g. The Deli, Levy Mall, Lusaka",
            }
        ),
    )
    video_link = forms.URLField(
        label="Or a video link",
        required=False,
        widget=forms.URLInput(
            attrs={"class": "form-control", "placeholder": "https://…"}
        ),
    )


class PreparationForm(forms.Form):
    def __init__(self, *args, **kwargs):
        from domain.elite.services.introduction_service import PREP_FIELDS

        super().__init__(*args, **kwargs)
        for field, label in PREP_FIELDS:
            self.fields[field] = forms.BooleanField(
                label=label, required=False, widget=CHECKBOX
            )


class IntroResultForm(forms.Form):
    result = forms.ChoiceField(choices=EliteCase.IntroResult.choices)
    on = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs=DATE_INPUT, format="%Y-%m-%d"),
    )
    who = forms.CharField(
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    why = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )


class CloseCaseForm(forms.Form):
    outcome = forms.ChoiceField(
        choices=EliteCase.ClosingOutcome.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    note = forms.CharField(
        required=False,
        max_length=1000,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )


class ExtendWindowForm(forms.Form):
    days = forms.TypedChoiceField(
        coerce=int,
        choices=[(7, "7 days"), (14, "14 days")],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    reason = forms.CharField(
        max_length=300,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "e.g. travelling until the 20th",
                "required": True,
            }
        ),
    )


class FeedbackSaveForm(forms.Form):
    """Which form is being saved; the answers themselves are checked by feedback_forms.clean_answers."""

    form = forms.ChoiceField(choices=[("A", "A"), ("B", "B"), ("C", "C")])


class CaseNoteForm(forms.Form):
    """Feedback gathered offline (or any other note). Goes on the timeline."""

    about = forms.ChoiceField(
        choices=[
            ("feedback_client", "Feedback from the client"),
            ("feedback_person", "Feedback from the named person"),
            ("note", "Note"),
        ],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    text = forms.CharField(
        max_length=2000,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 4,
                "required": True,
                "placeholder": "Only what matters, e.g. 'Both happy, want to meet again. Client felt well prepared.'",
            }
        ),
    )
    concern = forms.BooleanField(
        required=False, widget=forms.CheckboxInput(attrs={"class": "form-check-input"})
    )


class InfoAnswerForm(forms.Form):
    """The client's reply to 'More information needed'. 'outcome' is the button pressed."""

    outcome = forms.ChoiceField(
        choices=[("answered", "Answer received"), ("no_answer", "No answer")]
    )
    answer = forms.CharField(
        required=False,
        max_length=2000,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "e.g. Confirmed they met at a friend's wedding in 2024 and have known each other two years.",
            }
        ),
    )
    file = forms.FileField(
        required=False,
        validators=[validate_document],
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
    )
