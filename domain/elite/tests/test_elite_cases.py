import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from domain.base.models import Groups
from domain.base.services.groups import create_groups_and_permissions
from domain.elite.models import EliteAccessLog, EliteCase, EliteCaseEvent
from domain.elite.services.elite_service import delete_abandoned
from domain.website.models import SiteDocument

User = get_user_model()
TMP_MEDIA = tempfile.mkdtemp()


def pdf(name="file.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4 test", content_type="application/pdf")


def staff(email, group):
    user = User.objects.create_user(email=email, password="pass12345", first_name=email.split("@")[0].title(), last_name="User")
    user.groups.add(Group.objects.get(name=group))
    return user


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class EliteTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        create_groups_and_permissions()
        cls.admin = staff("boss@x.com", Groups.ADMIN)
        cls.matchmaker = staff("mm@x.com", Groups.MATCHMAKER)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)

    def tearDown(self):
        for case in EliteCase.objects.all():
            for document in case.documents.all():
                document.file.delete(save=False)

    def apply(self, email="mwila@example.com"):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("elite:apply"), {
                "full_name": "Mwila Banda", "email": email, "phone": "", "understood": "on", "website": "",
            })
        return EliteCase.objects.get(email=email)

    def confirm(self, case):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.get(reverse("elite:confirm", args=[case.verify_token]))

    def to_review(self):
        case = self.apply()
        self.confirm(case)
        self.client.force_login(self.admin)
        for kind in ("nda", "declaration", "request_form"):
            self.client.post(reverse("elite:case-upload", args=[case.pk]), {"kind": kind, "file": pdf(f"{kind}.pdf")})
        self.client.post(reverse("elite:case-received", args=[case.pk]), {"nda": "on", "declaration": "on", "request_form": "on"})
        case.refresh_from_db()
        return case


class ApplyTests(EliteTestCase):
    def test_apply_sends_confirmation_link(self):
        case = self.apply()
        self.assertEqual(case.status, EliteCase.Status.AWAITING_EMAIL)
        self.assertIn(case.verify_token, mail.outbox[-1].body)

    def test_applying_again_reuses_the_case_with_a_new_link(self):
        first = self.apply()
        old_token = first.verify_token
        again = self.apply()
        self.assertEqual(first.pk, again.pk)
        self.assertNotEqual(old_token, again.verify_token)

    def test_honeypot_creates_nothing(self):
        self.client.post(reverse("elite:apply"), {
            "full_name": "Bot", "email": "bot@example.com", "understood": "on", "website": "spam.example",
        })
        self.assertFalse(EliteCase.objects.exists())

    def test_confirming_sends_documents_as_attachments(self):
        SiteDocument.objects.create(kind=SiteDocument.Kind.ELITE_NDA, file=pdf("nda.pdf"))
        case = self.apply()
        mail.outbox.clear()
        self.confirm(case)
        case.refresh_from_db()
        self.assertEqual(case.status, EliteCase.Status.AWAITING_DOCUMENTS)
        documents_email = next(m for m in mail.outbox if case.email in m.to)
        self.assertEqual(len(documents_email.attachments), 1)
        self.assertTrue(documents_email.reply_to)

    def test_expired_link(self):
        case = self.apply()
        EliteCase.objects.filter(pk=case.pk).update(verify_sent_at=timezone.now() - timedelta(hours=49))
        self.assertEqual(self.confirm(case).status_code, 400)


class StaffTests(EliteTestCase):
    def test_other_staff_see_nothing_and_every_view_logged(self):
        case = self.apply()
        self.client.force_login(self.matchmaker)                     # not this case's handler
        self.assertNotContains(self.client.get(reverse("elite:cases")), case.reference)
        self.assertEqual(self.client.get(reverse("elite:case-detail", args=[case.pk])).status_code, 404)

        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("elite:case-detail", args=[case.pk])).status_code, 200)
        self.assertTrue(EliteAccessLog.objects.filter(case=case, user=self.admin).exists())

    def test_all_three_documents_move_it_to_review(self):
        case = self.to_review()
        self.assertEqual(case.status, EliteCase.Status.UNDER_REVIEW)
        self.assertEqual(case.documents.count(), 3)

    def test_approve_needs_all_checks(self):
        case = self.to_review()
        self.client.post(reverse("elite:case-decide", args=[case.pk]), {"decision": "approve"})
        case.refresh_from_db()
        self.assertEqual(case.status, EliteCase.Status.UNDER_REVIEW)

        self.client.post(reverse("elite:case-checks", args=[case.pk]), {
            "check_known_to_client": "on", "check_no_prior_rejection": "on", "check_no_power_imbalance": "on",
            "check_identity_verified": "on", "check_suitability": "on",
        })
        self.client.post(reverse("elite:case-decide", args=[case.pk]), {"decision": "approve"})
        case.refresh_from_db()
        self.assertEqual(case.status, EliteCase.Status.APPROVED)

    def test_decline_sends_message_without_reason(self):
        case = self.to_review()
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("elite:case-decide", args=[case.pk]), {"decision": "decline", "note": "Power imbalance"})
        case.refresh_from_db()
        self.assertEqual(case.status, EliteCase.Status.DECLINED)
        self.assertNotIn("Power imbalance", mail.outbox[-1].body)

    def test_timeline_is_append_only(self):
        case = self.apply()
        event = case.events.first()
        event.text = "changed"
        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(ValidationError):
            event.delete()


class CleanupTests(EliteTestCase):
    def test_abandoned_applications_are_deleted(self):
        old = self.apply("old@example.com")
        self.apply("new@example.com")
        EliteCase.objects.filter(pk=old.pk).update(verify_sent_at=timezone.now() - timedelta(days=31))
        self.assertEqual(delete_abandoned(), 1)
        self.assertFalse(EliteCase.objects.filter(pk=old.pk).exists())
        self.assertFalse(EliteCaseEvent.objects.filter(case_id=old.pk).exists())


# ---------------------------------------------------------------- Part 2a

from datetime import date  # noqa: E402

from domain.elite.models import SuppressionEntry  # noqa: E402
from domain.elite.models.elite_case import EliteDocument  # noqa: E402
from domain.elite.services import elite_service as svc  # noqa: E402


class AfterApprovalBase(EliteTestCase):
    """Helpers to walk a case forward. No tests of its own."""

    def setUp(self):
        from domain.matchmaking.models import MembershipTier

        MembershipTier.objects.update_or_create(name="Elite Grade", defaults={"price": 35000, "is_active": False})

    def approved(self, email="mwila@example.com"):
        case = self.apply(email)
        self.confirm(case)
        case.refresh_from_db()
        for kind in ("nda", "declaration", "request_form"):
            svc.add_document(case, kind=kind, file=pdf(f"{kind}.pdf"), by=self.admin)
        svc.confirm_documents(case, nda=True, declaration=True, request_form=True, by=self.admin)
        svc.save_checks(case, checks={field: True for field, _ in svc.CHECKS}, by=self.admin)
        svc.decide(case, decision="approve", by=self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            svc.assign_handler(case, handler=self.matchmaker, by=self.admin)
        case.refresh_from_db()
        return case

    def paid(self, email="mwila@example.com", contact="+260 977 123456"):
        case = self.approved(email)
        svc.record_fee(case, method="bank_transfer", reference="TX1", paid_on=date.today(), by=self.matchmaker)
        svc.add_document(case, kind=EliteDocument.Kind.INDEMNITY, file=pdf("indemnity.pdf"), by=self.matchmaker)
        svc.confirm_indemnity(case, by=self.matchmaker)
        svc.record_person(case, name="Thandi Phiri", contact_type="phone", contact=contact, by=self.matchmaker)
        case.refresh_from_db()
        return case

class AfterApprovalTests(AfterApprovalBase):
    def test_assigning_handler_emails_payment_request_and_handler_sees_only_her_case(self):
        case = self.approved()
        self.assertTrue(any("approved" in m.subject.lower() for m in mail.outbox if case.email in m.to))
        self.client.force_login(self.matchmaker)
        self.assertContains(self.client.get(reverse("elite:case-detail", args=[case.pk])), case.reference)

    def test_fee_and_indemnity_unlock_outreach_and_details_are_encrypted(self):
        case = self.paid()
        self.assertEqual(case.status, EliteCase.Status.PAID)
        self.assertEqual(case.fee_amount, 35000)                     # from the tier, not typed in
        self.assertNotIn("Thandi", case.person_name_enc)
        self.assertEqual(case.person_name, "Thandi Phiri")

    def test_full_path_to_introduction(self):
        case = self.paid()
        svc.record_outreach(case, delivered=True, sent_on=date.today(), by=self.matchmaker)
        case.refresh_from_db()
        self.assertEqual(case.reply_due_on, date.today() + timedelta(days=14))
        with self.assertRaises(svc.EliteError):
            svc.record_answer(case, answer="no_response", by=self.matchmaker)   # 14 days not over yet
        SiteDocument.objects.create(kind=SiteDocument.Kind.ELITE_ACKNOWLEDGEMENT, file=pdf("ack-blank.pdf"))
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            svc.record_answer(case, answer="agreed", person_email="thandi@example.com", by=self.matchmaker)
        ack_email = next(m for m in mail.outbox if "thandi@example.com" in m.to)
        self.assertEqual(len(ack_email.attachments), 1)
        self.assertNotIn("Mwila", ack_email.body)                    # never names the client
        svc.add_document(case, kind=EliteDocument.Kind.ACKNOWLEDGEMENT, file=pdf("ack.pdf"), by=self.matchmaker)
        svc.record_acknowledgement(case, signed=True, by=self.matchmaker)
        case.refresh_from_db()
        self.assertEqual(case.status, EliteCase.Status.INTRODUCTION)
        self.assertEqual(case.person_email, "thandi@example.com")

    def test_bounce_does_not_count_and_asks_client_for_another_route(self):
        case = self.paid()
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            svc.record_outreach(case, delivered=False, sent_on=date.today(), by=self.matchmaker)
        case.refresh_from_db()
        self.assertEqual((case.status, case.outreach_bounces), (EliteCase.Status.PAID, 1))
        self.assertTrue(any("another way" in m.subject for m in mail.outbox))

    def test_decline_adds_to_register_offers_bronze_and_blocks_a_new_request(self):
        case = self.paid()
        svc.record_outreach(case, delivered=True, sent_on=date.today(), by=self.matchmaker)
        with self.captureOnCommitCallbacks(execute=True):
            svc.record_answer(case, answer="declined", by=self.matchmaker)
        case.refresh_from_db()
        self.assertEqual(case.status, EliteCase.Status.BRONZE_OFFERED)
        self.assertEqual(SuppressionEntry.objects.count(), 1)
        self.assertTrue(any("Bronze" in m.body for m in mail.outbox if case.email in m.to))

        # Someone asks for the same person again (same number written differently): refused
        other = self.approved("other@example.com")
        svc.record_fee(other, method="bank_transfer", reference="", paid_on=date.today(), by=self.matchmaker)
        with self.assertRaises(svc.EliteError):
            svc.record_person(other, name="T. Phiri", contact_type="phone", contact="0977123456", by=self.matchmaker)

        svc.record_bronze_answer(case, accepted=True, by=self.matchmaker)
        case.refresh_from_db()
        self.assertEqual(case.status, EliteCase.Status.CLOSED)

    def test_named_person_deleted_30_days_after_closing(self):
        case = self.paid()
        svc.record_outreach(case, delivered=True, sent_on=date.today(), by=self.matchmaker)
        svc.record_answer(case, answer="declined", by=self.matchmaker)
        svc.record_bronze_answer(case, accepted=False, by=self.matchmaker)
        EliteCase.objects.filter(pk=case.pk).update(closed_at=timezone.now() - timedelta(days=31))
        self.assertEqual(svc.wipe_named_person(), 1)
        case.refresh_from_db()
        self.assertEqual(case.person_name, "")
        self.assertFalse(case.documents.filter(kind=EliteDocument.Kind.REQUEST_FORM).exists())
        self.assertTrue(case.documents.filter(kind=EliteDocument.Kind.NDA).exists())
        self.assertEqual(SuppressionEntry.objects.count(), 1)   # the fingerprint stays


# ---------------------------------------------------------------- Part 2b

from datetime import datetime  # noqa: E402

from domain.elite.models import EliteFeedback  # noqa: E402
from domain.elite.services import introduction_service as intro  # noqa: E402

GOOD_A = {
    "discreet": "5", "approach_respectful": "5", "handler_clear": "4", "prepared": "5", "expectations": "above",
    "fee_worth": "yes", "recommend_elite": "10", "recommend_elyria": "yes", "referral_contact": "yes",
}


class IntroductionTests(AfterApprovalBase):
    def at_introduction(self):
        case = self.paid()
        svc.record_outreach(case, delivered=True, sent_on=date.today(), by=self.matchmaker)
        svc.record_answer(case, answer="agreed", person_email="thandi@example.com", by=self.matchmaker)
        svc.add_document(case, kind=EliteDocument.Kind.ACKNOWLEDGEMENT, file=pdf("ack.pdf"), by=self.matchmaker)
        svc.record_acknowledgement(case, signed=True, by=self.matchmaker)
        case.refresh_from_db()
        return case

    def introduced(self):
        case = self.at_introduction()
        when = timezone.make_aware(datetime.combine(date.today(), datetime.min.time())) + timedelta(hours=18)
        with self.captureOnCommitCallbacks(execute=True):
            intro.schedule_introduction(case, intro_at=when, venue="The Deli, Lusaka", by=self.matchmaker)
        intro.record_intro_result(case, result="took_place", on=date.today(), by=self.matchmaker)
        case.refresh_from_db()
        return case

    def test_alerts_go_to_both(self):
        case = self.at_introduction()
        mail.outbox.clear()
        when = timezone.now() + timedelta(days=3)
        with self.captureOnCommitCallbacks(execute=True):
            intro.schedule_introduction(case, intro_at=when, venue="The Deli, Lusaka", by=self.matchmaker)
        recipients = {address for m in mail.outbox for address in m.to}
        self.assertTrue({"mwila@example.com", "thandi@example.com"} <= recipients)

    def test_took_place_schedules_forms_a_and_b_for_day_3(self):
        case = self.introduced()
        self.assertEqual(case.status, EliteCase.Status.INTRODUCED)
        forms = {f.form: f for f in case.feedback.all()}
        self.assertEqual(set(forms), {"A", "B"})
        self.assertEqual(forms["A"].send_on, date.today() + timedelta(days=3))
        self.assertEqual(forms["A"].closes_on, date.today() + timedelta(days=14))

    def test_daily_run_sends_reminds_and_never_deletes(self):
        case = self.introduced()
        mail.outbox.clear()
        intro.daily_run(today=date.today() + timedelta(days=3))
        invites = [m for m in mail.outbox if m.subject == "Elyria would value your feedback"]
        self.assertEqual(len(invites), 2)
        self.assertNotIn("Mwila", invites[0].body)                     # no names, no details
        intro.daily_run(today=date.today() + timedelta(days=7))
        self.assertEqual(EliteFeedback.objects.filter(reminded_at__isnull=False).count(), 2)
        self.assertTrue(EliteCase.objects.filter(pk=case.pk).exists())

    def test_submitting_form_a_with_low_rating_flags_and_lead(self):
        case = self.introduced()
        intro.daily_run(today=date.today() + timedelta(days=3))
        form_a = case.feedback.get(form="A")
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("elite:feedback", args=[form_a.token]), {**GOOD_A, "prepared": "2"})
        self.assertContains(response, "Thank you")
        form_a.refresh_from_db()
        self.assertTrue(form_a.red_flag)
        self.assertTrue(form_a.referral_lead)
        self.assertEqual(form_a.answers["testimonial"], "no")          # default is No
        self.assertTrue(any("Red flag" in m.subject for m in mail.outbox))
        # one time only
        response = self.client.post(reverse("elite:feedback", args=[form_a.token]), GOOD_A)
        self.assertContains(response, "already been completed")

    def test_form_b_intrusive_needs_details_and_flags(self):
        case = self.introduced()
        intro.daily_run(today=date.today() + timedelta(days=3))
        form_b = case.feedback.get(form="B")
        answers = {"comfortable": "4", "first_contact_respectful": "4", "acknowledgement_clear": "4",
                   "free_to_decline": "yes", "prepared": "4", "intrusive": "yes", "open_to_joining": "maybe",
                   "recommend_approach": "yes", "contact_referral": "no"}
        response = self.client.post(reverse("elite:feedback", args=[form_b.token]), answers)
        self.assertEqual(response.status_code, 400)                    # details are required when Yes
        self.client.post(reverse("elite:feedback", args=[form_b.token]), {**answers, "intrusive_details": "Too many calls"})
        form_b.refresh_from_db()
        self.assertTrue(form_b.red_flag)

    def test_closed_link_and_reopen(self):
        case = self.introduced()
        intro.daily_run(today=date.today() + timedelta(days=3))
        form_a = case.feedback.get(form="A")
        EliteFeedback.objects.filter(pk=form_a.pk).update(closes_on=date.today() - timedelta(days=1))
        self.assertContains(self.client.get(reverse("elite:feedback", args=[form_a.token])), "has closed")
        intro.extend_feedback(form_a, days=7, by=self.matchmaker)
        self.assertContains(self.client.get(reverse("elite:feedback", args=[form_a.token])), "Send my feedback")

    def test_form_c_after_closing_without_introduction(self):
        case = self.paid()
        svc.record_outreach(case, delivered=True, sent_on=date.today(), by=self.matchmaker)
        svc.record_answer(case, answer="declined", by=self.matchmaker)
        self.assertEqual(case.feedback.get().form, "C")

    def test_extend_reply_window(self):
        case = self.paid()
        svc.record_outreach(case, delivered=True, sent_on=date.today(), by=self.matchmaker)
        case = intro.extend_reply_window(case, days=7, reason="Travelling", by=self.matchmaker)
        self.assertEqual(case.reply_due_on, date.today() + timedelta(days=21))

    def test_deletion_is_manual_and_admin_only(self):
        case = self.introduced()
        intro.close_case(case, outcome="continuing", by=self.matchmaker)
        EliteCase.objects.filter(pk=case.pk).update(closed_at=timezone.now() - timedelta(days=31))
        intro.daily_run(today=date.today())
        case.refresh_from_db()
        self.assertEqual(case.person_name, "Thandi Phiri")             # the daily job never deletes
        with self.assertRaises(svc.EliteError):
            intro.delete_now(case, by=self.matchmaker)
        intro.delete_now(case, by=self.admin)
        case.refresh_from_db()
        self.assertEqual(case.person_name, "")