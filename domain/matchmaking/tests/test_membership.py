import re
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from domain.base.models import Groups
from domain.base.services.groups import create_groups_and_permissions
from domain.matchmaking.models import Client, ConsultationRequest, Membership, MembershipPayment

User = get_user_model()
S = ConsultationRequest.Status

MEMBERSHIP = {
    "tier": "gold", "start_date": "2026-10-09", "end_date": "2027-10-08",
    "amount": "15000.00", "currency": "ZMW", "method": "bank_transfer", "reference": "BT-77",
}


def make_user(email, *groups):
    user = User.objects.create_user(email=email, password="pass12345", first_name="Anisha", last_name="N")
    user.groups.add(*Group.objects.filter(name__in=groups))
    return user


def make_request(**overrides):
    data = {
        "full_name": "Natasha Kabwe", "preferred_name": "Natasha", "gender": "female", "age": 34,
        "seeking": "man", "relationship_status": "single", "location": "Lusaka, Zambia",
        "nationality": "Zambian", "occupation": "Accountant", "email": "natasha@example.com",
        "phone": "+260977000000",
    }
    data.update(overrides)
    return ConsultationRequest.objects.create(**data)


class ConfirmMembershipTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        create_groups_and_permissions()
        cls.matchmaker = make_user("mm@x.com", Groups.MATCHMAKER)

    def setUp(self):
        self.client.force_login(self.matchmaker)

    def confirm(self, c, data=MEMBERSHIP, follow=False):
        url = reverse("matchmaking:consultation-request-confirm-membership", args=[c.pk])
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(url, data, follow=follow)

    def test_requires_consultation_first(self):
        c = make_request(status=S.FEE_PAID)
        response = self.confirm(c, follow=True)
        self.assertContains(response, "only be confirmed after the consultation")
        self.assertFalse(Client.objects.exists())

    def test_confirm_creates_everything(self):
        c = make_request(status=S.CONSULTED, assigned_to=self.matchmaker)
        self.confirm(c)

        c.refresh_from_db()
        self.assertEqual(c.status, S.BECAME_MEMBER)

        client = Client.objects.get(consultation_request=c)
        self.assertEqual(client.matchmaker, self.matchmaker)
        self.assertTrue(client.user.groups.filter(name=Groups.MEMBER).exists())
        self.assertFalse(client.user.has_usable_password())

        self.assertEqual(client.membership.tier, Membership.Tier.GOLD)
        payment = MembershipPayment.objects.get(membership=client.membership)
        self.assertEqual(str(payment.amount), "15000.00")
        self.assertEqual(payment.kind, MembershipPayment.Kind.NEW)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/account/set-password/", mail.outbox[0].body)

    def test_end_date_must_be_after_start(self):
        c = make_request(status=S.CONSULTED)
        response = self.confirm(c, {**MEMBERSHIP, "end_date": "2026-10-01"}, follow=True)
        self.assertContains(response, "end date must be after")
        self.assertFalse(Client.objects.exists())

    def test_staff_email_is_refused(self):
        make_user("natasha@example.com", Groups.MATCHMAKER)
        c = make_request(status=S.CONSULTED)
        response = self.confirm(c, follow=True)
        self.assertContains(response, "already belongs to a staff account")

    def test_set_password_link_signs_member_in(self):
        c = make_request(status=S.CONSULTED)
        self.confirm(c)
        self.client.logout()

        link = re.search(r"http\S+/account/set-password/\S+/", mail.outbox[0].body).group(0)
        response = self.client.get(urlparse(link).path)  # Django swaps the token for a session
        form_url = response.url

        response = self.client.post(form_url, {"new_password1": "Str0ng-pass-123", "new_password2": "Str0ng-pass-123"})
        self.assertRedirects(response, "/portal/", fetch_redirect_response=False)

        user = User.objects.get(email="natasha@example.com")
        self.assertTrue(user.check_password("Str0ng-pass-123"))