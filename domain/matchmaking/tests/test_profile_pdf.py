from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from domain.base.models import Groups
from domain.base.services.groups import create_groups_and_permissions
from domain.matchmaking.models import Client, ClientProfile, ConsultationRequest, Membership, MembershipTier

User = get_user_model()


def make_user(email, *groups):
    user = User.objects.create_user(email=email, password="pass12345", first_name="Test", last_name="User")
    user.groups.add(*Group.objects.filter(name__in=groups))
    return user


class ProfilePdfTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        create_groups_and_permissions()
        cls.matchmaker = make_user("mm@x.com", Groups.MATCHMAKER)
        cls.finance = make_user("fin@x.com", Groups.FINANCE)
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
        cls.profile = ClientProfile.objects.create(
            client=cls.member, full_name="Natasha Kabwe", hobbies="Reading", core_values=["honesty"],
        )
        cls.url = reverse("matchmaking:member-profile-pdf", args=[cls.member.pk])

    def setUp(self):
        self.client.force_login(self.matchmaker)

    def test_complete_profile_downloads_as_pdf(self):
        ClientProfile.objects.filter(pk=self.profile.pk).update(completed_at=timezone.now())
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(self.member.consultation_request.payment_reference, response["Content-Disposition"])
        self.assertIn("Natasha-", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_incomplete_profile_is_refused(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("matchmaking:member-detail", args=[self.member.pk]))

    def test_finance_cannot_download(self):
        ClientProfile.objects.filter(pk=self.profile.pk).update(completed_at=timezone.now())
        self.client.force_login(self.finance)
        self.assertEqual(self.client.get(self.url).status_code, 403)