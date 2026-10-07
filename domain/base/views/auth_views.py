from django.conf import settings
from django.contrib.auth.views import LoginView, LogoutView

from domain.base.services.groups import home_url_for


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
    """POST only (Django 5). Use a small form, not a plain link."""
    next_page = "/"