from django.contrib.auth.views import LoginView, LogoutView, PasswordResetConfirmView

from domain.base.models.permissions import STAFF_GROUPS
from domain.base.services.groups import home_url_for
from django.shortcuts import resolve_url

class SignInView(LoginView):
    """Member sign-in (public, linked from the site)."""
    template_name = "domain/portal/auth/sign_in.html"
    redirect_authenticated_user = True

    def get_default_redirect_url(self):
        # Used when there's no safe ?next= in the URL
        return home_url_for(self.request.user)


class StaffSignInView(SignInView):
    """Staff sign-in (separate, not linked from the public site)."""
    template_name = "domain/management/auth/sign_in.html"


class SignOutView(LogoutView):
    """POST only (Django 5). Staff go back to the staff sign-in, members to the member sign-in."""

    def post(self, request, *args, **kwargs):
        user = request.user
        self.was_staff = user.is_superuser or user.groups.filter(name__in=STAFF_GROUPS).exists()
        return super().post(request, *args, **kwargs)

    def get_default_redirect_url(self):
        return resolve_url("base:staff-sign-in" if self.was_staff else "base:sign-in")


class SetPasswordView(PasswordResetConfirmView):
    """From the welcome email: choose a password, get signed in, land on your home page."""
    template_name = "domain/portal/auth/set_password.html"
    post_reset_login = True
    post_reset_login_backend = "django.contrib.auth.backends.ModelBackend"

    def get_success_url(self):
        return home_url_for(self.request.user)