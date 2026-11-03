from datetime import timedelta

from django.core import mail
from django.urls import reverse
from django.utils import timezone

from domain.matchmaking.models import MembershipPayment, MembershipTier, Pairing
from domain.matchmaking.services.member_service import (
    end_hold,
    introduction_status,
    renew_membership,
    start_hold,
)
from domain.matchmaking.services.pairing_service import candidates_for, record_introduction
from domain.matchmaking.tests.test_pairings import PairingCase, make_member


class IntroductionCase(PairingCase):
    def setUp(self):
        MembershipTier.objects.filter(name="Gold").update(max_introductions=3, price=1000)

    def introduce(self, a, b, by):
        """A mutual pairing with an introduction date recorded."""
        pairing = Pairing.objects.create(
            client_a=a, client_b=b, added_by=by, status=Pairing.Status.MUTUAL,
            a_presented_at=timezone.now(), a_decision="interested", b_decision="interested",
        )
        with self.captureOnCommitCallbacks(execute=True):
            record_introduction(pairing, by=by, introduced_on=timezone.localdate())
        return pairing

    def status(self, client):
        client.membership.refresh_from_db()
        return introduction_status(client.membership)


class CountingTests(IntroductionCase):
    def test_counts_different_people_not_matches(self):
        Pairing.objects.create(client_a=self.natasha, client_b=self.david, added_by=self.anisha)  # a match only
        self.introduce(self.natasha, self.joseph, self.anisha)
        self.assertEqual(self.status(self.natasha)["used"], 1)
        self.assertEqual(self.status(self.natasha)["left"], 2)

    def test_same_person_again_is_still_one_introduction(self):
        first = self.introduce(self.natasha, self.joseph, self.anisha)
        Pairing.objects.filter(pk=first.pk).update(status=Pairing.Status.CLOSED)
        self.introduce(self.natasha, self.joseph, self.anisha)
        self.assertEqual(self.status(self.natasha)["used"], 1)

    def test_unlimited_tier(self):
        MembershipTier.objects.filter(name="Gold").update(max_introductions=None)
        self.introduce(self.natasha, self.joseph, self.anisha)
        self.assertEqual(self.status(self.natasha), {"allowed": None, "used": 1, "left": None, "state": "ok"})


class ReminderTests(IntroductionCase):
    def test_one_left_then_none_left_emails_member_and_matchmaker(self):
        extra = make_member("Kelvin Tembo", gender="male", seeking="woman", matchmaker=self.anisha)
        third = make_member("Mike Zulu", gender="male", seeking="woman", matchmaker=self.anisha)

        self.introduce(self.natasha, self.joseph, self.anisha)
        mail.outbox.clear()
        self.introduce(self.natasha, extra, self.anisha)              # 2 of 3: one left
        subjects = [m.subject for m in mail.outbox if self.natasha.user.email in m.to or "anisha@x.com" in m.to]
        self.assertTrue(any("one introduction left" in s for s in subjects))
        self.assertTrue(any("Natasha has one introduction left" in s for s in subjects))

        mail.outbox.clear()
        self.introduce(self.natasha, third, self.anisha)              # 3 of 3: none left
        self.assertTrue(any("used all your introductions" in m.subject for m in mail.outbox))

    def test_nothing_sent_with_plenty_left(self):
        mail.outbox.clear()
        self.introduce(self.natasha, self.joseph, self.anisha)        # 1 of 3
        self.assertFalse(any("introduction" in m.subject.lower() and "left" in m.subject for m in mail.outbox))


class RenewUpgradeTests(IntroductionCase):
    def test_renewal_adds_to_what_is_left_and_extends(self):
        self.introduce(self.natasha, self.joseph, self.anisha)        # 1 of 3 used
        membership = self.natasha.membership
        old_end = membership.end_date
        renew_membership(membership, tier=MembershipTier.objects.get(name="Gold"), method="bank_transfer", by=self.anisha)
        status = self.status(self.natasha)
        self.assertEqual((status["allowed"], status["left"]), (6, 5))
        self.assertGreater(self.natasha.membership.end_date, old_end)

    def test_upgrade_is_recorded_as_upgrade(self):
        silver = MembershipTier.objects.create(name="Test Silver", price=500, max_introductions=5, duration_months=6)
        renew_membership(self.natasha.membership, tier=silver, method="bank_transfer", by=self.anisha)
        self.assertEqual(self.status(self.natasha)["allowed"], 8)     # 3 from Gold + 5
        self.assertEqual(self.natasha.membership.payments.first().kind, MembershipPayment.Kind.UPGRADE)


class HoldTests(IntroductionCase):
    def test_hold_hides_member_and_extends_end_date(self):
        membership = self.david.membership
        old_end = membership.end_date
        start_hold(membership, reason="work", started_on=timezone.localdate() - timedelta(days=10), by=self.annastasia)
        self.assertNotIn(self.david, candidates_for(self.natasha))

        hold = end_hold(membership, by=self.annastasia)
        membership.refresh_from_db()
        self.assertEqual(hold.days_added, 10)
        self.assertEqual(membership.end_date, old_end + timedelta(days=10))
        self.assertIn(self.david, candidates_for(self.natasha))

    def test_hold_from_member_page(self):
        self.as_user(self.annastasia)
        self.client.post(reverse("matchmaking:member-hold-start", args=[self.david.pk]),
                         {"reason": "grievance", "started_on": timezone.localdate().isoformat()})
        self.assertTrue(self.david.membership.holds.filter(ended_on__isnull=True).exists())
        response = self.client.get(reverse("matchmaking:member-detail", args=[self.david.pk]))
        self.assertContains(response, "On hold")