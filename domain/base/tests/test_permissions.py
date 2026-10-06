from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.views import View

from domain.base.mixins import AdminRequiredMixin, MemberRequiredMixin, StaffRequiredMixin
from domain.base.models import Groups, Profile
from domain.base.services.groups import create_groups_and_permissions
from domain.base.templatetags.group_tags import has_any_group

User = get_user_model()


def make_user(email, *groups, **extra):
    user = User.objects.create_user(email=email, password="pass12345", **extra)
    user.groups.add(*Group.objects.filter(name__in=groups))
    return user


class OkView(View):
    def get(self, request):
        return HttpResponse("ok")


class StaffView(StaffRequiredMixin, OkView):
    pass


class MatchingView(StaffRequiredMixin, OkView):
    permission_required = "base.manage_matching"


class AdminView(AdminRequiredMixin, OkView):
    pass


class MemberView(MemberRequiredMixin, OkView):
    pass


class BaseTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        create_groups_and_permissions()


class GroupSetupTests(BaseTestCase):
    def perms(self, name):
        return set(Group.objects.get(name=name).permissions.values_list("codename", flat=True))

    def test_member_only_gets_portal(self):
        self.assertEqual(self.perms(Groups.MEMBER), {"access_member_portal"})

    def test_matchmaker_cannot_manage_staff(self):
        self.assertIn("manage_matching", self.perms(Groups.MATCHMAKER))
        self.assertNotIn("manage_staff", self.perms(Groups.MATCHMAKER))

    def test_admin_can_manage_staff(self):
        self.assertIn("manage_staff", self.perms(Groups.ADMIN))

    def test_setup_is_repeatable(self):
        create_groups_and_permissions()
        self.assertEqual(Group.objects.count(), 3)


class ProfileTests(BaseTestCase):
    def test_profile_created_with_user(self):
        user = make_user("p@x.com")
        self.assertTrue(Profile.objects.filter(user=user).exists())

    def test_profile_group_flags(self):
        user = make_user("mm@x.com", Groups.MATCHMAKER)
        self.assertTrue(user.profile.is_matchmaker)
        self.assertTrue(user.profile.is_staff_member)
        self.assertFalse(user.profile.is_admin)

    def test_has_any_group_tag(self):
        user = make_user("a@x.com", Groups.ADMIN)
        self.assertTrue(has_any_group(user, "Matchmaker, Admin"))
        self.assertFalse(has_any_group(user, "Member"))


class MixinTests(BaseTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def call(self, view, user):
        request = self.rf.get("/")
        request.user = user
        return view.as_view()(request)

    def test_anonymous_redirected_to_staff_sign_in(self):
        response = self.call(StaffView, AnonymousUser())
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("base:staff-sign-in"), response.url)

    def test_member_blocked_from_staff_view(self):
        with self.assertRaises(PermissionDenied):
            self.call(StaffView, make_user("m@x.com", Groups.MEMBER))

    def test_staff_blocked_from_member_view(self):
        with self.assertRaises(PermissionDenied):
            self.call(MemberView, make_user("s@x.com", Groups.MATCHMAKER))

    def test_member_can_open_portal(self):
        self.assertEqual(self.call(MemberView, make_user("m2@x.com", Groups.MEMBER)).status_code, 200)

    def test_matchmaker_can_match(self):
        self.assertEqual(self.call(MatchingView, make_user("mm@x.com", Groups.MATCHMAKER)).status_code, 200)

    def test_matchmaker_blocked_from_admin_view(self):
        with self.assertRaises(PermissionDenied):
            self.call(AdminView, make_user("mm2@x.com", Groups.MATCHMAKER))

    def test_superuser_passes_admin_view(self):
        su = User.objects.create_superuser(email="su@x.com", password="pass12345")
        self.assertEqual(self.call(AdminView, su).status_code, 200)


class SignInRedirectTests(BaseTestCase):
    def sign_in(self, email):
        return self.client.post(reverse("base:sign-in"), {"username": email, "password": "pass12345"})

    def test_staff_lands_on_dashboard(self):
        make_user("s@x.com", Groups.MATCHMAKER)
        self.assertRedirects(self.sign_in("s@x.com"), "/management/", fetch_redirect_response=False)

    def test_member_lands_on_portal(self):
        make_user("m@x.com", Groups.MEMBER)
        self.assertRedirects(self.sign_in("m@x.com"), "/portal/", fetch_redirect_response=False)