from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from domain.base.models import Groups
from domain.base.services.groups import create_groups_and_permissions
from domain.matchmaking.models import (
    Client,
    ClientProfile,
    Consultation,
    ConsultationRequest,
    Membership,
    MembershipTier,
)
from domain.matchmaking.services.compare_service import compare

User = get_user_model()


def make_user(email, *groups):
    user = User.objects.create_user(email=email, password="pass12345", first_name="Test", last_name="User")
    user.groups.add(*Group.objects.filter(name__in=groups))
    return user


class CompareTests(TestCase):
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
        Consultation.objects.create(request=request, a5="About three years ago", notes="Warm.")
        cls.member = Client.objects.create(
            user=make_user("natasha@example.com", Groups.MEMBER), consultation_request=request,
            full_name="Natasha Kabwe", preferred_name="Natasha", matchmaker=cls.matchmaker,
        )
        Membership.objects.create(
            client=cls.member, tier=MembershipTier.objects.get(name="Gold"),
            start_date=date(2026, 1, 1), end_date=date(2027, 1, 1),
        )

    def rows(self, **profile):
        ClientProfile.objects.update_or_create(client=self.member, defaults=profile)
        self.member.refresh_from_db()
        return {r["key"]: r for r in compare(self.member)}

    def test_nothing_without_a_profile(self):
        self.assertEqual(compare(self.member), [])

    def test_facts_that_match(self):
        rows = self.rows(age=34, gender="female", seeking="man", relationship_status="single")
        self.assertFalse(any(rows[k]["differs"] for k in ("age", "gender", "seeking", "status")))

    def test_different_status_is_flagged(self):
        rows = self.rows(relationship_status="divorced")
        self.assertTrue(rows["status"]["differs"])

    def test_a_birthday_is_not_a_discrepancy(self):
        self.assertFalse(self.rows(age=35)["age"]["differs"])
        self.assertTrue(self.rows(age=40)["age"]["differs"])

    def test_open_answers_are_shown_not_judged(self):
        row = self.rows(time_since_last="6_12m")["a5"]
        self.assertFalse(row["differs"])
        self.assertIn("About three years ago", row["consultation_text"])
        self.assertIn("6–12 months", row["profile_text"])

    def test_member_page_shows_comparison_to_matchmaker_only(self):
        self.rows(relationship_status="divorced")
        url = reverse("matchmaking:member-detail", args=[self.member.pk])
        self.client.force_login(self.matchmaker)
        self.assertContains(self.client.get(url), "Consultation vs profile")
        self.client.force_login(self.finance)
        self.assertNotContains(self.client.get(url), "Consultation vs profile")