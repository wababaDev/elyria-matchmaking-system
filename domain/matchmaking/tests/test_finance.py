from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from domain.base.models import Groups
from domain.base.services.groups import create_groups_and_permissions
from domain.matchmaking.models import (
    Client,
    Consultation,
    ConsultationRequest,
    Membership,
    MembershipPayment,
    MembershipTier,
)

User = get_user_model()
S = ConsultationRequest.Status


def make_user(email, *groups, first="Test"):
    user = User.objects.create_user(email=email, password="pass12345", first_name=first, last_name="User")
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


class FinanceCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        create_groups_and_permissions()
        cls.admin = make_user("admin@x.com", Groups.ADMIN, first="Ada")
        cls.matchmaker = make_user("mm@x.com", Groups.MATCHMAKER, first="Anisha")
        cls.finance = make_user("fin@x.com", Groups.FINANCE, first="Fiona")

        # One person who paid the fee and then became a member and renewed
        cls.request = make_request(
            status=S.BECAME_MEMBER, assigned_to=cls.matchmaker,
            fee_paid_at=timezone.now(), fee_marked_paid_by=cls.matchmaker,
            fee_amount=1000, fee_currency="ZMW", fee_payment_method="mobile_money", fee_reference="MM-1",
        )
        member_user = make_user("natasha@example.com", Groups.MEMBER)
        client = Client.objects.create(
            user=member_user, consultation_request=cls.request,
            full_name="Natasha Kabwe", preferred_name="Natasha", matchmaker=cls.matchmaker,
        )
        tier = MembershipTier.objects.get(name="Gold")
        cls.membership = Membership.objects.create(
            client=client, tier=tier, start_date=date(2026, 1, 1), end_date=date(2027, 1, 1),
        )
        for kind, ref in ((MembershipPayment.Kind.NEW, "BT-1"), (MembershipPayment.Kind.RENEWAL, "BT-2")):
            MembershipPayment.objects.create(
                membership=cls.membership, kind=kind, amount=15000, currency="ZMW",
                method="bank_transfer", reference=ref, recorded_by=cls.matchmaker,
            )

        # Someone else, fee only
        make_request(
            full_name="Grace Lungu", email="grace@x.com", status=S.FEE_PAID,
            fee_paid_at=timezone.now(), fee_marked_paid_by=cls.admin,
            fee_amount=1000, fee_currency="ZMW", fee_payment_method="bank_transfer",
        )

    def setUp(self):
        self.client.force_login(self.finance)


class FinanceAccessTests(FinanceCase):
    def test_can_open_read_only_pages(self):
        for name in ("dashboard", "payments", "consultation-requests", "members"):
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(f"matchmaking:{name}")).status_code, 200)

    def test_can_open_request_and_member_detail(self):
        self.assertEqual(
            self.client.get(reverse("matchmaking:consultation-request-detail", args=[self.request.pk])).status_code, 200
        )
        self.assertEqual(
            self.client.get(reverse("matchmaking:member-detail", args=[self.membership.client.pk])).status_code, 200
        )

    def test_cannot_open_queue_settings_or_enquiries(self):
        for name in ("my-queue", "enquiries", "settings-staff"):
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(f"matchmaking:{name}")).status_code, 403)

    def test_cannot_change_anything(self):
        c = make_request(email="new@x.com")
        response = self.client.post(
            reverse("matchmaking:consultation-request-mark-paid", args=[c.pk]),
            {"method": "mobile_money", "reference": ""},
        )
        self.assertEqual(response.status_code, 403)

        response = self.client.post(
            reverse("matchmaking:member-renew", args=[self.membership.client.pk]),
            {"tier": self.membership.tier_id, "method": "bank_transfer"},
        )
        self.assertEqual(response.status_code, 403)

    def test_cannot_undo_payment(self):
        c = make_request(email="paid@x.com", status=S.FEE_PAID, fee_paid_at=timezone.now(), fee_amount=1000)
        response = self.client.post(
            reverse("matchmaking:consultation-request-undo-paid", args=[c.pk]), {"reason": "x"}
        )
        self.assertEqual(response.status_code, 403)

    def test_notes_hidden_from_finance(self):
        Consultation.objects.create(request=self.request, notes="Private consultation notes")
        url = reverse("matchmaking:consultation-request-detail", args=[self.request.pk])
        record_url = reverse("matchmaking:consultation-record", args=[self.request.pk])

        # Finance: no record card on the request page, and the record itself is forbidden
        self.assertNotContains(self.client.get(url), record_url)
        self.assertEqual(self.client.get(record_url).status_code, 403)

        # Admin: sees the card, and the notes on the record page
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(url), record_url)
        self.assertContains(self.client.get(record_url), "Private consultation notes")

    def test_matchmaker_cannot_see_payments(self):
        self.client.force_login(self.matchmaker)
        self.assertEqual(self.client.get(reverse("matchmaking:payments")).status_code, 403)

    def test_admin_can_see_payments(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("matchmaking:payments")).status_code, 200)

    def test_finance_not_offered_for_assignment(self):
        from domain.matchmaking.forms import staff_members
        self.assertNotIn(self.finance, staff_members())


class PaymentsPageTests(FinanceCase):
    def get(self, **params):
        return self.client.get(reverse("matchmaking:payments"), params)

    def test_lists_every_payment(self):
        response = self.get()
        self.assertEqual(response.context["summary"]["count"], 4)  # 2 fees + new + renewal
        self.assertEqual(dict(response.context["summary"]["all"])["ZMW"], 32000)

    def test_search_by_reference_shows_whole_history(self):
        response = self.get(q=self.request.payment_reference)
        kinds = sorted(p.kind for p in response.context["payments"])
        self.assertEqual(kinds, ["fee", "new", "renewal"])

    def test_filter_by_type(self):
        response = self.get(kind="renewal")
        self.assertEqual([p.transaction_ref for p in response.context["payments"]], ["BT-2"])

    def test_filter_by_staff_member(self):
        response = self.get(staff=self.admin.pk)
        self.assertEqual([p.person for p in response.context["payments"]], ["Grace Lungu"])

    def test_staff_summary(self):
        rows = {r["user"]: r for r in self.get().context["staff_rows"]}
        self.assertEqual(rows[self.matchmaker]["fees"], 1)
        self.assertEqual(rows[self.matchmaker]["new"], 1)
        self.assertEqual(rows[self.matchmaker]["renewals"], 1)
        self.assertEqual(rows[self.admin]["fees"], 1)

    def test_member_counts(self):
        self.assertEqual(self.get().context["members"]["total"], 1)


class CancelledByTests(FinanceCase):
    def test_cancellation_records_who(self):
        self.client.force_login(self.matchmaker)
        self.client.post(
            reverse("matchmaking:member-cancel", args=[self.membership.client.pk]), {"reason": "Moved abroad"}
        )
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.cancelled_by, self.matchmaker)

        self.client.force_login(self.finance)
        rows = {r["user"]: r for r in self.client.get(reverse("matchmaking:payments")).context["staff_rows"]}
        self.assertEqual(rows[self.matchmaker]["cancelled"], 1)