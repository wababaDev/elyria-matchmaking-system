from django.core import mail
from django.urls import reverse
from django.utils import timezone

from domain.base.models import Groups
from domain.matchmaking.models import Pairing
from domain.matchmaking.models.date_feedback import DateFeedback
from domain.matchmaking.tests.test_pairings import PairingCase, make_user

WENT_WELL = {
    "date": "2026-11-01", "setting": "coffee", "duration_minutes": "90",
    "went_ahead": "yes", "meet_again": "yes", "meet_again_why": "\"She made me laugh.\"",
    "went_well": "Easy conversation", "matched_profile": "yes", "felt_respected": "yes",
    "wants_next": "another_date", "flag_severity": "", "outcome": "another_date",
}


class DateFeedbackTests(PairingCase):
    """Natasha (Anisha's) and David (Annastasia's) have had their first date."""

    def setUp(self):
        self.pairing = Pairing.objects.create(
            client_a=self.natasha, client_b=self.david, added_by=self.anisha,
            approval=Pairing.Approval.APPROVED, status=Pairing.Status.MUTUAL,
            a_presented_at=timezone.now(), a_decision="interested", b_decision="interested",
            introduced_on=timezone.localdate(), introduction_setting="coffee", introduction_minutes=90,
        )

    def add_url(self, client):
        return reverse("matchmaking:date-feedback-add", args=[self.pairing.pk, client.pk])

    def post(self, client, data, by):
        self.as_user(by)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.add_url(client), data)

    def test_form_is_filled_from_the_introduction(self):
        self.as_user(self.anisha)
        response = self.client.get(self.add_url(self.natasha))
        self.assertContains(response, f"INT-{self.pairing.pk:04d}-1")
        self.assertContains(response, 'value="coffee" selected')

    def test_own_matchmaker_records_feedback_and_pairing_stays_open(self):
        self.post(self.natasha, WENT_WELL, self.anisha)
        fb = DateFeedback.objects.get()
        self.assertEqual((fb.client, fb.date_number, fb.recorded_by), (self.natasha, 1, self.anisha))
        self.pairing.refresh_from_db()
        self.assertTrue(self.pairing.is_open)
        # second date gets number 2
        self.post(self.natasha, {**WENT_WELL, "date": "2026-11-08"}, self.anisha)
        self.assertEqual(DateFeedback.objects.filter(client=self.natasha).count(), 2)

    def test_other_matchmaker_can_neither_record_nor_see_it(self):
        self.as_user(self.annastasia)
        self.assertEqual(self.client.get(self.add_url(self.natasha)).status_code, 404)
        self.post(self.natasha, WENT_WELL, self.anisha)
        fb = DateFeedback.objects.get()
        self.as_user(self.annastasia)
        self.assertEqual(self.client.get(reverse("matchmaking:date-feedback-edit", args=[fb.pk])).status_code, 404)

    def test_ended_by_match_closes_the_pairing(self):
        self.post(self.natasha, {**WENT_WELL, "meet_again": "no", "outcome": "ended_by_match"}, self.anisha)
        self.pairing.refresh_from_db()
        self.assertFalse(self.pairing.is_open)
        self.assertEqual(self.pairing.closed_by, self.anisha)
        self.assertIn("by David", self.pairing.closed_reason)

    def test_cancelled_needs_who(self):
        response = self.post(self.natasha, {**WENT_WELL, "went_ahead": "cancelled", "outcome": "another_date"}, self.anisha)
        self.assertContains(response, "Say who cancelled")
        self.assertFalse(DateFeedback.objects.exists())

    def test_serious_flag_emails_admin(self):
        make_user("boss@x.com", Groups.ADMIN)
        mail.outbox.clear()
        self.post(self.natasha, {
            **WENT_WELL, "behaviour_flags": ["safety"], "flag_severity": "serious",
            "flag_notes": "Followed her to her car.", "outcome": "ended_by_client",
        }, self.anisha)
        self.assertTrue(any("boss@x.com" in m.to and "Serious flag" in m.subject for m in mail.outbox))