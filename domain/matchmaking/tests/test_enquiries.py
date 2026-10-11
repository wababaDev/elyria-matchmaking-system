from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from domain.base.models import Groups
from domain.base.services.groups import create_groups_and_permissions
from domain.matchmaking.forms import EnquiryForm
from domain.matchmaking.models import Enquiry, MembershipTier

User = get_user_model()
VALID = {"tier": "Gold", "question": "What's included in Gold?", "first_name": "Grace", "contact": "+260 977 123 456"}


def make_user(email, *groups):
    user = User.objects.create_user(email=email, password="pass12345", first_name="Test", last_name="User")
    user.groups.add(*Group.objects.filter(name__in=groups))
    return user


class EnquiryFormTests(TestCase):
    def test_phone_or_email_accepted(self):
        self.assertTrue(EnquiryForm(data=VALID).is_valid())
        self.assertTrue(EnquiryForm(data={**VALID, "contact": "Grace@Example.com"}).is_valid())

    def test_rubbish_contact_rejected(self):
        self.assertFalse(EnquiryForm(data={**VALID, "contact": "call me"}).is_valid())

    def test_unknown_tier_still_saves(self):
        form = EnquiryForm(data={**VALID, "tier": ""})
        self.assertTrue(form.is_valid())


class PublicEnquiryTests(TestCase):
    url = reverse("website:enquiry")

    def setUp(self):
        cache.clear()

    def test_submit_saves_and_alerts_team(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url, VALID)
        enquiry = Enquiry.objects.get()
        self.assertEqual(enquiry.tier.name, "Gold")
        self.assertEqual(enquiry.status, Enquiry.Status.OPEN)
        self.assertRedirects(response, f"{reverse('website:enquiry-thanks')}?tier={enquiry.tier.pk}", fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("New enquiry (Gold)", mail.outbox[0].subject)

    def test_thanks_page_names_tier(self):
        gold = MembershipTier.objects.get(name="Gold")
        response = self.client.get(reverse("website:enquiry-thanks"), {"tier": gold.pk})
        self.assertContains(response, "about Gold Membership")

    def test_honeypot_saves_nothing(self):
        self.client.post(self.url, {**VALID, "website": "spam"})
        self.assertFalse(Enquiry.objects.exists())


class StaffEnquiryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        create_groups_and_permissions()
        cls.matchmaker = make_user("mm@x.com", Groups.MATCHMAKER)
        cls.member = make_user("m@x.com", Groups.MEMBER)

    def test_matchmaker_sees_open_enquiries(self):
        Enquiry.objects.create(question="Q", first_name="Grace", contact="+260977123456")
        self.client.force_login(self.matchmaker)
        response = self.client.get(reverse("matchmaking:enquiries"))
        self.assertContains(response, "Grace")
        self.assertEqual(response.context["open_enquiries_count"], 1)

    def test_mark_answered(self):
        e = Enquiry.objects.create(question="Q", first_name="Grace", contact="+260977123456")
        self.client.force_login(self.matchmaker)
        self.client.post(reverse("matchmaking:enquiry-answered", args=[e.pk]), {"response_note": "Called her"})
        e.refresh_from_db()
        self.assertEqual(e.status, Enquiry.Status.ANSWERED)
        self.assertEqual(e.answered_by, self.matchmaker)
        self.assertEqual(e.response_note, "Called her")

    def test_member_cannot_see_enquiries(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse("matchmaking:enquiries")).status_code, 403)