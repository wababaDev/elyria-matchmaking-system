from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from domain.base.models import Groups
from domain.base.services.groups import create_groups_and_permissions
from domain.matchmaking.models import (
    Client, ConsultationRequest, Membership, MembershipPayment, MembershipTier,
)

User = get_user_model()
TODAY = timezone.localdate()


def make_user(email, *groups):
    user = User.objects.create_user(email=email, password="pass12345", first_name="Test", last_name="User")
    user.groups.add(*Group.objects.filter(name__in=groups))
    return user


def make_member(name, *, matchmaker=None, end_in_days=200, tier="Gold"):
    email = f"{name.lower()}@example.com"
    request = ConsultationRequest.objects.create(
        full_name=f"{name} Banda", preferred_name=name, gender="female", age=34, seeking="man",
        relationship_status="single", location="Lusaka", nationality="Zambian", occupation="Accountant",
        email=email, phone="+260977000000", status=ConsultationRequest.Status.BECAME_MEMBER,
    )
    user = make_user(email, Groups.MEMBER)
    client = Client.objects.create(
        user=user, consultation_request=request, full_name=f"{name} Banda",
        preferred_name=name, matchmaker=matchmaker,
    )
    membership = Membership.objects.create(
        client=client, tier=MembershipTier.objects.get(name=tier),
        start_date=TODAY - timedelta(days=100), end_date=TODAY + timedelta(days=end_in_days),
    )
    MembershipPayment.objects.create(
        membership=membership, kind="new", amount=15000, currency="ZMW", method="bank_transfer",
    )
    return client


class MemberTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        create_groups_and_permissions()
        cls.admin = make_user("admin@x.com", Groups.ADMIN)
        cls.anisha = make_user("anisha@x.com", Groups.MATCHMAKER)
        cls.tonde = make_user("tonde@x.com", Groups.MATCHMAKER)

    def url(self, name, member=None):
        return reverse(f"matchmaking:{name}", args=[member.pk] if member else [])

    def test_matchmaker_sees_only_own_members(self):
        make_member("Grace", matchmaker=self.anisha)
        make_member("Ruth", matchmaker=self.tonde)
        self.client.force_login(self.anisha)
        response = self.client.get(self.url("members"))
        self.assertContains(response, "Grace Banda")
        self.assertNotContains(response, "Ruth Banda")

    def test_admin_sees_everyone(self):
        make_member("Grace", matchmaker=self.anisha)
        make_member("Ruth", matchmaker=self.tonde)
        self.client.force_login(self.admin)
        response = self.client.get(self.url("members"))
        self.assertContains(response, "Grace Banda")
        self.assertContains(response, "Ruth Banda")

    def test_matchmaker_cannot_open_other_member(self):
        ruth = make_member("Ruth", matchmaker=self.tonde)
        self.client.force_login(self.anisha)
        self.assertEqual(self.client.get(self.url("member-detail", ruth)).status_code, 404)

    def test_member_account_gets_403(self):
        grace = make_member("Grace", matchmaker=self.anisha)
        self.client.force_login(grace.user)
        self.assertEqual(self.client.get(self.url("member-detail", grace)).status_code, 403)

    def test_expiring_filter(self):
        make_member("Soon", matchmaker=self.anisha, end_in_days=10)
        make_member("Later", matchmaker=self.anisha, end_in_days=200)
        self.client.force_login(self.anisha)
        response = self.client.get(self.url("members"), {"status": "expiring"})
        self.assertContains(response, "Soon Banda")
        self.assertNotContains(response, "Later Banda")

    def test_renew_early_extends_from_end_date(self):
        grace = make_member("Grace", matchmaker=self.anisha, end_in_days=10)
        old_end = grace.membership.end_date
        self.client.force_login(self.anisha)
        self.client.post(self.url("member-renew", grace), {
            "tier": grace.membership.tier_id, "amount": "15000", "currency": "ZMW",
            "method": "mobile_money", "reference": "R1",
        })
        grace.membership.refresh_from_db()
        self.assertGreater(grace.membership.end_date, old_end)
        self.assertEqual(grace.membership.payments.filter(kind="renewal").count(), 1)

    def test_renew_without_amount_uses_tier_price(self):
        MembershipTier.objects.filter(name="Gold").update(price=18000, duration_months=12)
        grace = make_member("Grace", matchmaker=self.anisha)
        self.client.force_login(self.anisha)
        self.client.post(self.url("member-renew", grace), {
            "tier": grace.membership.tier_id, "amount": "", "currency": "ZMW", "method": "cash",
        })
        payment = grace.membership.payments.get(kind="renewal")
        self.assertEqual(str(payment.amount), "18000.00")

    def test_cancel_disables_sign_in(self):
        grace = make_member("Grace", matchmaker=self.anisha)
        self.client.force_login(self.anisha)
        self.client.post(self.url("member-cancel", grace), {"reason": "Found a partner"})
        grace.membership.refresh_from_db()
        grace.user.refresh_from_db()
        self.assertEqual(grace.membership.status, Membership.Status.CANCELLED)
        self.assertFalse(grace.user.is_active)

    def test_resend_sign_in_link(self):
        grace = make_member("Grace", matchmaker=self.anisha)
        self.client.force_login(self.anisha)
        self.client.post(self.url("member-resend-link", grace))
        self.assertEqual(mail.outbox[0].to, ["grace@example.com"])
        self.assertIn("/account/set-password/", mail.outbox[0].body)

    def test_only_admin_can_reassign(self):
        grace = make_member("Grace", matchmaker=self.anisha)
        self.client.force_login(self.anisha)
        response = self.client.post(self.url("member-reassign", grace), {"assigned_to": self.tonde.pk})
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.admin)
        self.client.post(self.url("member-reassign", grace), {"assigned_to": self.tonde.pk})
        grace.refresh_from_db()
        self.assertEqual(grace.matchmaker, self.tonde)