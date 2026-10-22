from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.db import transaction
from django.shortcuts import redirect
from django.views.generic import TemplateView

from domain.portal.forms.portal_forms import ContactDetailsForm, MemberPasswordChangeForm
from domain.portal.views.base import PortalMixin
from domain.website.models import SiteSettings


class AccountView(PortalMixin, TemplateView):
    """Membership summary, contact details and change password: two forms on one page."""
    template_name = "domain/portal/account/account.html"
    portal_nav = "account"

    def get_context_data(self, contact_form=None, password_form=None, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context.update(
            membership=getattr(self.client, "membership", None),
            profile=self.profile,
            site=SiteSettings.load(),
            contact_form=contact_form or ContactDetailsForm(
                user=user, initial={"email": user.email, "phone": self.profile.phone}
            ),
            password_form=password_form or MemberPasswordChangeForm(user=user),
        )
        return context

    def post(self, request, *args, **kwargs):
        if request.POST.get("form") == "password":
            return self._change_password(request)
        return self._save_contact(request)

    def _save_contact(self, request):
        form = ContactDetailsForm(request.POST, user=request.user)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(contact_form=form))

        with transaction.atomic():
            if form.email_changed:
                request.user.email = form.cleaned_data["email"]
                request.user.save(update_fields=["email"])
            self.profile.phone = form.cleaned_data["phone"].strip()
            self.profile.save(update_fields=["phone", "updated_at"])

        messages.success(request, "Contact details updated.")
        return redirect("portal:account")

    def _change_password(self, request):
        form = MemberPasswordChangeForm(user=request.user, data=request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(password_form=form))

        form.save()
        update_session_auth_hash(request, form.user)  # stay signed in
        messages.success(request, "Password changed.")
        return redirect("portal:account")