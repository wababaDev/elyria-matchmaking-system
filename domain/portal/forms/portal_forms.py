from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordChangeForm

from domain.matchmaking.models import ClientProfile, ProfilePhoto
from domain.matchmaking.profile_sections import (
    CHECKS,
    CHIPS,
    FIELD_NAMES,
    FIELDS_BY_NAME,
    SCALE,
    SELECT,
    SELECT_PLACEHOLDER,
    SLIDER,
    TEXTAREA,
)
from domain.matchmaking.services.profile_service import MAX_NON_NEGOTIABLES

MAX_PHOTO_MB = 10
NON_NEGOTIABLE_MAX_LENGTH = 200


def _photo_field():
    return forms.ImageField(required=False, widget=forms.FileInput(attrs={"accept": "image/*", "hidden": True}))


class ProfileForm(forms.ModelForm):
    """
    The whole Self-Service Profile. Nothing is required here, so the member can save
    and return; the "Mark profile complete" check is in profile_service.
    """
    core_values = forms.MultipleChoiceField(
        choices=ClientProfile.CoreValue.choices, required=False, widget=forms.CheckboxSelectMultiple
    )
    partner_values = forms.MultipleChoiceField(
        choices=ClientProfile.CoreValue.choices, required=False, widget=forms.CheckboxSelectMultiple
    )

    # One upload slot per kind of photo (a new upload replaces the old one)
    photo_full_length = _photo_field()
    photo_close_up = _photo_field()
    photo_other = _photo_field()

    PHOTO_FIELDS = {
        "photo_full_length": ProfilePhoto.Kind.FULL_LENGTH,
        "photo_close_up": ProfilePhoto.Kind.CLOSE_UP,
        "photo_other": ProfilePhoto.Kind.OTHER,
    }

    class Meta:
        model = ClientProfile
        fields = FIELD_NAMES

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in FIELD_NAMES:
            self._style(name, FIELDS_BY_NAME[name])

        # Non-negotiables are free-text rows added in the browser (up to 5)
        if self.is_bound:
            self.non_negotiables = [v.strip() for v in self.data.getlist("non_negotiables") if v.strip()]
        else:
            self.non_negotiables = list(self.instance.non_negotiables or [])

    def _style(self, name, spec):
        field = self.fields[name]
        field.required = False
        if spec.placeholder:
            field.widget.attrs["placeholder"] = spec.placeholder

        if spec.kind in (CHIPS, SCALE):
            field.widget = forms.RadioSelect()
            field.choices = [c for c in field.choices if c[0] != ""]
        elif spec.kind == SELECT:
            field.choices = [("", SELECT_PLACEHOLDER.get(name, "Select"))] + [c for c in field.choices if c[0] != ""]
        elif spec.kind == SLIDER:
            field.widget = forms.NumberInput(attrs={"type": "range", "min": 1, "max": 5, "step": 1})
        elif spec.kind == TEXTAREA:
            field.widget = forms.Textarea(attrs={"rows": 4})
        elif spec.kind == CHECKS:
            pass  # declared above

    def clean(self):
        cleaned = super().clean()

        low, high = cleaned.get("partner_age_min"), cleaned.get("partner_age_max")
        if low and high and low > high:
            self.add_error("partner_age_max", "Must be the same as or higher than 'Age from'.")

        if len(self.non_negotiables) > MAX_NON_NEGOTIABLES:
            raise forms.ValidationError(f"Please keep to {MAX_NON_NEGOTIABLES} non-negotiables or fewer.")
        if any(len(v) > NON_NEGOTIABLE_MAX_LENGTH for v in self.non_negotiables):
            raise forms.ValidationError(
                f"Each non-negotiable can be up to {NON_NEGOTIABLE_MAX_LENGTH} characters."
            )

        for name in self.PHOTO_FIELDS:
            upload = cleaned.get(name)
            if upload and upload.size > MAX_PHOTO_MB * 1024 * 1024:
                self.add_error(name, f"Photos can be up to {MAX_PHOTO_MB} MB.")
        return cleaned

    def _post_clean(self):
        super()._post_clean()
        self.instance.non_negotiables = self.non_negotiables

    @property
    def photo_uploads(self):
        """{kind: uploaded file} for the photos chosen in this submission."""
        return {
            kind: self.cleaned_data.get(name)
            for name, kind in self.PHOTO_FIELDS.items()
            if self.cleaned_data.get(name)
        }


class ContactDetailsForm(forms.Form):
    """Email (their sign-in) and phone. Changing the email needs the current password."""
    email = forms.EmailField(label="Email address")
    phone = forms.CharField(label="Phone number", max_length=30)
    current_password = forms.CharField(
        label="Current password",
        required=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
        help_text="Only needed if you change your email address.",
    )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if email != self.user.email.lower():
            if get_user_model().objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists():
                raise forms.ValidationError("This email address can't be used. Please choose another.")
        return email

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("email")
        if email and email != self.user.email.lower():
            if not self.user.check_password(cleaned.get("current_password") or ""):
                self.add_error("current_password", "Enter your current password to change your email address.")
        return cleaned

    @property
    def email_changed(self):
        return self.cleaned_data["email"] != self.user.email.lower()


class MemberPasswordChangeForm(PasswordChangeForm):
    """Django's own form (checks the current password and the password rules)."""