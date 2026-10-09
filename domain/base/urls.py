from django.urls import path

from domain.base.views.auth_views import SignInView, SignOutView, StaffSignInView, SetPasswordView

app_name = "base"

urlpatterns = [
    path("sign-in/", SignInView.as_view(), name="sign-in"),
    path("management/sign-in/", StaffSignInView.as_view(), name="staff-sign-in"),
    path("sign-out/", SignOutView.as_view(), name="sign-out"),
    path("account/set-password/<uidb64>/<token>/", SetPasswordView.as_view(), name="set-password"),
]