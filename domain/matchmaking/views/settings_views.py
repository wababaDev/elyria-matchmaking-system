from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, FormView, ListView, TemplateView, UpdateView

from domain.base.mixins import AdminRequiredMixin
from domain.base.services.staff_service import (
    StaffError,
    create_staff_member,
    role_of,
    staff_users,
    update_staff_member,
)
from domain.matchmaking.forms import (
    MembershipTierForm,
    PrivacyPolicyUploadForm,
    SiteSettingsForm,
    StaffCreateForm,
    StaffUpdateForm,
)
from domain.matchmaking.models import MembershipTier
from domain.website.models import SiteDocument, SiteSettings
from domain.website.services.document_service import replace_document
from notification.services.staff_emails import send_staff_invite

User = get_user_model()


class SettingsMixin(AdminRequiredMixin):
    settings_tab = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["settings_tab"] = self.settings_tab
        return context


# ---------- General ----------

class GeneralSettingsView(SettingsMixin, SuccessMessageMixin, UpdateView):
    settings_tab = "general"
    form_class = SiteSettingsForm
    template_name = "domain/management/settings/general.html"
    success_url = reverse_lazy("matchmaking:settings-general")
    success_message = "Settings saved."

    def get_object(self, queryset=None):
        return SiteSettings.load()


# ---------- Staff ----------

class StaffListView(SettingsMixin, TemplateView):
    settings_tab = "staff"
    template_name = "domain/management/settings/staff_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["staff"] = [(user, role_of(user)) for user in staff_users()]
        return context


class StaffCreateView(SettingsMixin, FormView):
    settings_tab = "staff"
    form_class = StaffCreateForm
    template_name = "domain/management/settings/staff_form.html"
    success_url = reverse_lazy("matchmaking:settings-staff")

    def form_valid(self, form):
        try:
            user = create_staff_member(by=self.request.user, **form.cleaned_data)
        except StaffError as error:
            form.add_error("email", str(error))
            return self.form_invalid(form)
        messages.success(self.request, f"{user.full_name} added. An email to set their password is on its way.")
        return super().form_valid(form)


class StaffUpdateView(SettingsMixin, FormView):
    settings_tab = "staff"
    form_class = StaffUpdateForm
    template_name = "domain/management/settings/staff_form.html"
    success_url = reverse_lazy("matchmaking:settings-staff")

    def dispatch(self, request, *args, **kwargs):
        self.member = get_object_or_404(staff_users(), pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        profile = getattr(self.member, "profile", None)
        return {
            "first_name": self.member.first_name,
            "last_name": self.member.last_name,
            "job_title": profile.job_title if profile else "",
            "role": role_of(self.member),
            "is_active": self.member.is_active,
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["member"] = self.member
        return context

    def form_valid(self, form):
        try:
            update_staff_member(self.member, by=self.request.user, **form.cleaned_data)
        except StaffError as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)
        messages.success(self.request, f"{self.member.full_name} updated.")
        return super().form_valid(form)


class StaffResendInviteView(SettingsMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        member = get_object_or_404(staff_users(), pk=pk)
        send_staff_invite(member)
        messages.success(request, f"A new password link was sent to {member.email}.")
        return redirect("matchmaking:settings-staff")


# ---------- Membership tiers ----------

class TierListView(SettingsMixin, ListView):
    settings_tab = "tiers"
    model = MembershipTier
    template_name = "domain/management/settings/tier_list.html"
    context_object_name = "tiers"


class TierCreateView(SettingsMixin, SuccessMessageMixin, CreateView):
    settings_tab = "tiers"
    model = MembershipTier
    form_class = MembershipTierForm
    template_name = "domain/management/settings/tier_form.html"
    success_url = reverse_lazy("matchmaking:settings-tiers")
    success_message = "Tier \"%(name)s\" added."


class TierUpdateView(SettingsMixin, SuccessMessageMixin, UpdateView):
    settings_tab = "tiers"
    model = MembershipTier
    form_class = MembershipTierForm
    template_name = "domain/management/settings/tier_form.html"
    success_url = reverse_lazy("matchmaking:settings-tiers")
    success_message = "Tier \"%(name)s\" saved. New memberships will use these values."


# ---------- Documents ----------

class DocumentsView(SettingsMixin, FormView):
    settings_tab = "documents"
    form_class = PrivacyPolicyUploadForm
    template_name = "domain/management/settings/documents.html"
    success_url = reverse_lazy("matchmaking:settings-documents")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["privacy_document"] = SiteDocument.current(SiteDocument.Kind.PRIVACY_POLICY)
        return context

    def form_valid(self, form):
        replace_document(kind=SiteDocument.Kind.PRIVACY_POLICY, file=form.cleaned_data["file"], by=self.request.user)
        messages.success(self.request, "Privacy Policy uploaded. The public page now links to it.")
        return super().form_valid(form)