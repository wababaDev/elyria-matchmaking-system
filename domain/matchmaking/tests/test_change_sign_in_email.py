from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from domain.base.models import Groups
from domain.base.services.groups import create_groups_and_permissions
from domain.matchmaking.models import Client, ConsultationRequest, Membership, MembershipTier

User = get_user_model()


def make_user(email, *groups, password="pass12345"):
    user = User.objects.create_user(email=email, password=password, first_name="Test", last_name="User")
    user.groups.add(*Group.objects.filter(name__in=groups))
    return user


class ChangeSignInEmailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        create_groups_and_permissions()
        cls.matchmaker = make_user("mm@x.com", Groups.MATCHMAKER)
        cls.other_matchmaker = make_user("mm2@x.com", Groups.MATCHMAKER)
        cls.finance = make_user("fin@x.com", Groups.FINANCE)
        make_user("taken@example.com", Groups.MEMBER)

        request = ConsultationRequest.objects.create(
            full_name="Natasha Kabwe", preferred_name="Natasha", gender="female", age=34, seeking="man",
            relationship_status="single", location="Lusaka, Zambia", nationality="Zambian",
            occupation="Accountant", email="natasha@example.com", phone="+260977000000",
            status=ConsultationRequest.Status.BECAME_MEMBER,
        )
        cls.member = Client.objects.create(
            user=make_user("natasha@example.com", Groups.MEMBER), consultation_request=request,
            full_name="Natasha Kabwe", preferred_name="Natasha", matchmaker=cls.matchmaker,
        )
        Membership.objects.create(
            client=cls.member, tier=MembershipTier.objects.get(name="Gold"),
            start_date=date(2026, 1, 1), end_date=date(2027, 1, 1),
        )
        cls.url = reverse("matchmaking:member-change-email", args=[cls.member.pk])

    def setUp(self):
        self.client.force_login(self.matchmaker)

    def change(self, email):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.url, {"email": email})

    def email(self):
        self.member.user.refresh_from_db()
        return self.member.user.email

    def test_matchmaker_changes_email_and_both_addresses_are_told(self):
        response = self.change("  Natasha.New@Example.com ")
        self.assertRedirects(response, reverse("matchmaking:member-detail", args=[self.member.pk]))
        self.assertEqual(self.email(), "natasha.new@example.com")
        self.assertEqual(len(mail.outbox), 1)
        self.assertCountEqual(mail.outbox[0].to, ["natasha.new@example.com", "natasha@example.com"])

    def test_password_still_works_after_change(self):
        self.change("natasha.new@example.com")
        self.assertTrue(self.member.user.check_password("pass12345"))

    def test_email_used_by_someone_else_is_refused(self):
        self.change("taken@example.com")
        self.assertEqual(self.email(), "natasha@example.com")
        self.assertEqual(len(mail.outbox), 0)

    def test_member_without_password_gets_a_fresh_link(self):
        self.member.user.set_unusable_password()
        self.member.user.save()
        self.change("natasha.new@example.com")
        subjects = [m.subject for m in mail.outbox]
        self.assertTrue(any("sign-in link" in s.lower() for s in subjects), subjects)

    def test_other_matchmaker_and_finance_cannot(self):
        self.client.force_login(self.other_matchmaker)
        self.assertEqual(self.change("x@example.com").status_code, 404)
        self.client.force_login(self.finance)
        self.assertEqual(self.change("x@example.com").status_code, 403)
        self.assertEqual(self.email(), "natasha@example.com")