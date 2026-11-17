from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from domain.matchmaking.models import Membership, MembershipTier, Pairing
from domain.matchmaking.services.consultation_request_service import InvalidTransitionError
from domain.matchmaking.services.member_service import end_hold, start_hold
from domain.matchmaking.services.pairing_service import candidates_for, propose, where_it_stands
from domain.matchmaking.tests.test_introductions import IntroductionCase


def day(n):
    return timezone.localdate() + timedelta(days=n)


class HoldTimeTests(IntroductionCase):
    def setUp(self):
        super().setUp()
        # David's tier works like Silver: 6 weeks
        tier = self.david.membership.tier
        tier.allows_hold, tier.hold_weeks = True, 6
        tier.save()

    def membership(self):
        return Membership.objects.get(pk=self.david.membership.pk)  # fresh, no cached hold

    def hold(self, first, last, **kw):
        return start_hold(self.membership(), reason="work", started_on=first, ended_on=last, by=self.annastasia, **kw)

    def test_holds_add_up(self):
        self.hold(day(10), day(23))  # 14 days
        self.assertEqual(self.membership().hold_days_left, 28)  # 4 weeks left

    def test_her_example_two_breaks_of_two_weeks(self):
        Membership.objects.filter(pk=self.david.membership.pk).update(start_date=day(-60))
        self.hold(day(-30), day(-17))  # 2 weeks, already over
        self.assertEqual(self.membership().hold_days_left, 28)  # 4 weeks left
        self.hold(day(5), day(18))  # another 2 weeks
        self.assertEqual(self.membership().hold_days_left, 14)  # 2 weeks left

    def test_too_long_is_refused(self):
        with self.assertRaisesMessage(InvalidTransitionError, "only 6 weeks"):
            self.hold(day(1), day(43))  # 43 days

    def test_end_date_moves_forward_counting_both_days(self):
        old_end = self.membership().end_date
        self.hold(day(1), day(14))
        self.assertEqual(self.membership().end_date, old_end + timedelta(days=14))

    def test_tier_without_hold_is_refused(self):
        bronze = MembershipTier.objects.create(name="Bronze test", price=100, duration_months=12)
        Membership.objects.filter(pk=self.david.membership.pk).update(tier=bronze)
        with self.assertRaisesMessage(InvalidTransitionError, "doesn't include Hold Time"):
            self.hold(day(1), day(5))

    def test_overlap_and_second_open_hold_refused(self):
        self.hold(day(5), day(10))
        with self.assertRaises(InvalidTransitionError):
            self.hold(day(20), day(25))

    def test_current_hold_hides_from_find_a_match(self):
        self.hold(day(0), day(5))
        self.assertNotIn(self.david, candidates_for(self.natasha))

    def test_booked_hold_does_not_hide_yet(self):
        self.hold(day(3), day(5))
        membership = self.membership()
        self.assertFalse(membership.on_hold)
        self.assertIsNotNone(membership.upcoming_hold)
        self.assertIn(self.david, candidates_for(self.natasha))

    def test_end_early_gives_days_back(self):
        old_end = self.membership().end_date
        self.hold(day(0), day(13))  # 14 days
        hold, days_back = end_hold(self.membership(), back_on=day(1), by=self.annastasia)  # last day = today
        self.assertEqual(hold.days_added, 1)
        self.assertEqual(days_back, 13)
        self.assertEqual(self.membership().end_date, old_end + timedelta(days=1))
        self.assertEqual(self.membership().hold_days_left, 41)

    def test_cancel_booked_hold(self):
        old_end = self.membership().end_date
        self.hold(day(5), day(18))
        hold, days_back = end_hold(self.membership(), by=self.annastasia)
        self.assertIsNone(hold.pk)
        self.assertEqual(days_back, 14)
        self.assertEqual(self.membership().end_date, old_end)
        self.assertEqual(self.membership().hold_days_left, 42)

    def test_allowance_starts_again_on_new_term(self):
        self.hold(day(1), day(42))  # all 6 weeks
        self.assertEqual(self.membership().hold_days_left, 0)
        Membership.objects.filter(pk=self.david.membership.pk).update(hold_term_start=day(50))
        self.assertEqual(self.membership().hold_days_left, 42)

    def test_put_on_hold_from_member_page(self):
        self.as_user(self.annastasia)
        self.client.post(reverse("matchmaking:member-hold-start", args=[self.david.pk]), {
            "reason": "grievance", "started_on": day(0).isoformat(), "ended_on": day(13).isoformat(),
        })
        response = self.client.get(reverse("matchmaking:member-detail", args=[self.david.pk]))
        self.assertContains(response, "On hold")
        self.assertContains(response, "2 weeks used · 4 weeks left")

    def test_no_hold_button_for_tier_without_hold(self):
        bronze = MembershipTier.objects.create(name="Bronze test", price=100, duration_months=12)
        Membership.objects.filter(pk=self.david.membership.pk).update(tier=bronze)
        self.as_user(self.annastasia)
        response = self.client.get(reverse("matchmaking:member-detail", args=[self.david.pk]))
        self.assertNotContains(response, "Put on hold")


class HoldAndPairingTests(HoldTimeTests):
    def test_cannot_propose_for_member_on_hold(self):
        self.hold(day(0), day(5))
        david = type(self.david).objects.get(pk=self.david.pk)  # fresh, so the hold is seen
        with self.assertRaisesMessage(InvalidTransitionError, "on hold"):
            propose(david, self.natasha, by=self.annastasia, note_for_a="x", b_profession="", b_location="")

    def test_open_pairing_warns_when_member_goes_on_hold(self):
        pairing = Pairing.objects.create(client_a=self.natasha, client_b=self.david, added_by=self.annastasia)
        self.hold(day(0), day(5))
        pairing = Pairing.objects.get(pk=pairing.pk)
        text, _ = where_it_stands(pairing, self.annastasia)
        self.assertIn("on hold until", text)