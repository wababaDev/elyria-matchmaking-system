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

    ALL_CHECKS = {
        "check_known_to_client": "on", "check_no_prior_rejection": "on", "check_no_power_imbalance": "on",
        "check_identity_verified": "on", "check_suitability": "on",
    }

    def test_more_info_waits_for_the_answer_before_approving(self):
        case = self.to_review()
        self.client.post(reverse("elite:case-checks", args=[case.pk]), self.ALL_CHECKS)
        self.client.post(reverse("elite:case-decide", args=[case.pk]), {"decision": "more_info", "note": "How do you know them?"})
        request = case.info_requests.get()
        self.assertTrue(request.is_open)
        self.assertContains(self.client.get(reverse("elite:case-detail", args=[case.pk])), "Waiting for the client")

        self.client.post(reverse("elite:case-decide", args=[case.pk]), {"decision": "approve"})
        case.refresh_from_db()
        self.assertEqual(case.status, EliteCase.Status.UNDER_REVIEW)              # locked while waiting

        response = self.client.post(reverse("elite:case-info-answer", args=[case.pk]), {
            "outcome": "answered", "answer": "Colleagues for three years.", "file": pdf("reply.pdf"),
        })
        self.assertIn("replied=1", response["Location"])
        request.refresh_from_db()
        self.assertEqual(request.answer, "Colleagues for three years.")
        self.assertTrue(case.documents.filter(kind=EliteDocument.Kind.CLIENT_REPLY).exists())
        self.assertTrue(case.events.filter(text__startswith="Client answered").exists())

        self.client.post(reverse("elite:case-decide", args=[case.pk]), {"decision": "approve"})
        case.refresh_from_db()
        self.assertEqual(case.status, EliteCase.Status.APPROVED)

    def test_no_answer_unlocks_and_only_one_open_question(self):
        case = self.to_review()
        self.client.post(reverse("elite:case-decide", args=[case.pk]), {"decision": "more_info", "note": "First question"})
        self.client.post(reverse("elite:case-decide", args=[case.pk]), {"decision": "more_info", "note": "Second question"})
        self.assertEqual(case.info_requests.count(), 1)                          # wait for the first answer
        self.client.post(reverse("elite:case-info-answer", args=[case.pk]), {"outcome": "no_answer"})
        self.assertTrue(case.info_requests.get().no_answer)
        self.assertIsNone(svc.open_info_request(case))

    def test_delete_from_inbox_message_only_when_all_documents_are_in(self):
        case = self.apply()
        self.confirm(case)
        self.client.force_login(self.admin)
        url = reverse("elite:case-detail", args=[case.pk]) + "?uploaded=1"
        self.client.post(reverse("elite:case-upload", args=[case.pk]), {"kind": "nda", "file": pdf("nda.pdf")})
        response = self.client.get(url)
        self.assertContains(response, "Don't delete the email from info@ yet")
        self.assertNotContains(response, "All the documents for this step are uploaded")
        for kind in ("declaration", "request_form"):
            self.client.post(reverse("elite:case-upload", args=[case.pk]), {"kind": kind, "file": pdf(f"{kind}.pdf")})
        self.assertContains(self.client.get(url), "All the documents for this step are uploaded")

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
        svc.record_person(case, name="Thandi Phiri", contact_type="phone", contact=contact,
                          met_where="A friend's wedding in Lusaka", occupation="Banker", by=self.matchmaker)
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

    def test_other_contact_route_needs_its_kind_and_is_encrypted(self):
        case = self.paid()
        self.client.force_login(self.matchmaker)
        url = reverse("elite:case-person", args=[case.pk])
        self.client.post(url, {"name": "Thandi Phiri", "contact": "Plot 12, Kabulonga", "met_where": "A friend's wedding in Lusaka"})
        case.refresh_from_db()
        self.assertEqual(case.person_contact_type, "phone")                    # refused: kind missing, unchanged
        self.client.post(url, {"name": "Thandi Phiri", "contact_type": "other", "contact_other": "Workplace address",
                               "contact": "Plot 12, Kabulonga", "met_where": "A friend's wedding in Lusaka"})
        case.refresh_from_db()
        self.assertEqual(case.person_contact_label, "Workplace address")
        self.assertNotIn("Workplace", case.person_contact_other_enc)            # stored encrypted
        self.assertContains(self.client.get(reverse("elite:case-detail", args=[case.pk])), "Workplace address")

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
        _, matches = svc.record_person(other, name="Thandi  phiri", contact_type="phone", contact="0977123456", by=self.matchmaker)
        self.assertEqual(len(matches), 1)                                          # warned, not blocked (names aren't unique)
        self.assertIn(case.reference, svc.describe_match(matches[0]))
        self.assertTrue(other.events.filter(text__startswith="Warning: someone with the same name").exists())
        entry = SuppressionEntry.objects.get()
        self.assertEqual((entry.person_name, entry.client_name, entry.met_where, entry.occupation),
                         ("Thandi Phiri", case.full_name, "A friend's wedding in Lusaka", "Banker"))
        self.assertNotIn("Thandi", entry.person_name_enc)                          # stored encrypted

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
        self.assertEqual(case.person_met_where, "")
        self.assertEqual(SuppressionEntry.objects.get().person_name, "Thandi Phiri")   # D16: the list entry stays


# ---------------------------------------------------------------- Part 2b

from datetime import datetime  # noqa: E402

from domain.elite.services import introduction_service as intro  # noqa: E402

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

    def test_took_place_then_feedback_notes_go_on_the_timeline(self):
        case = self.introduced()
        self.assertEqual(case.status, EliteCase.Status.INTRODUCED)
        mail.outbox.clear()
        intro.add_note(case, about="feedback_client", text="Felt well prepared.", by=self.matchmaker)
        intro.add_note(case, about="feedback_person", text="Uneasy about the venue.", concern=True, by=self.matchmaker)
        texts = list(case.events.values_list("text", flat=True))
        self.assertIn("Feedback from the client: Felt well prepared.", texts)
        self.assertIn("CONCERN · Feedback from the named person: Uneasy about the venue.", texts)
        self.assertEqual(mail.outbox, [])                              # nothing is emailed to anyone

    def test_only_the_handler_or_admin_can_add_notes(self):
        case = self.introduced()
        with self.assertRaises(svc.EliteError):
            intro.add_note(case, about="note", text="Hello", by=staff("other@x.com", Groups.MATCHMAKER))
        intro.add_note(case, about="note", text="Checked in with both.", by=self.admin)

    def test_forms_a_and_b_apply_after_the_introduction(self):
        case = self.introduced()
        self.assertEqual(intro.feedback_forms_for(case), ["A", "B"])
        self.client.force_login(self.matchmaker)
        response = self.client.get(reverse("elite:case-detail", args=[case.pk]))
        self.assertContains(response, "How discreet did the process feel?")
        self.assertContains(response, "How comfortable did you feel being approached?")

    def test_handler_records_form_a_with_flag_and_lead(self):
        case = self.introduced()
        self.client.force_login(self.matchmaker)
        response = self.client.post(reverse("elite:case-feedback", args=[case.pk]), {
            "form": "A", "discreet": "5", "prepared": "2", "recommend_elite": "10",
            "recommend_elyria": "yes", "referral_contact": "yes", "worked_best": "Very discreet.",
        })
        self.assertEqual(response.status_code, 302)
        form_a = case.feedback.get(form="A")
        self.assertEqual(form_a.answers["discreet"], 5)
        self.assertTrue(form_a.red_flag)                               # prepared rated 2
        self.assertTrue(form_a.referral_lead)
        self.assertNotIn("testimonial", form_a.answers)                # not asked, not stored
        texts = " ".join(case.events.values_list("text", flat=True))
        self.assertIn("Form A recorded", texts)
        self.assertIn("CONCERN · Red flag on Form A", texts)

    def test_correcting_form_b_updates_it(self):
        case = self.introduced()
        intro.save_feedback(case, form="B", data={"intrusive": "yes", "intrusive_details": "Too many calls"}, by=self.matchmaker)
        intro.save_feedback(case, form="B", data={"intrusive": "no", "intrusive_details": "Too many calls"}, by=self.matchmaker)
        form_b = case.feedback.get(form="B")
        self.assertFalse(form_b.red_flag)
        self.assertNotIn("intrusive_details", form_b.answers)          # follow-up dropped when they said No
        self.assertEqual(case.feedback.count(), 1)

    def test_form_c_after_closing_without_introduction(self):
        case = self.paid()
        svc.record_outreach(case, delivered=True, sent_on=date.today(), by=self.matchmaker)
        svc.record_answer(case, answer="declined", by=self.matchmaker)
        case.refresh_from_db()
        self.assertEqual(intro.feedback_forms_for(case), ["C"])
        with self.assertRaises(svc.EliteError):
            intro.save_feedback(case, form="A", data={"discreet": "4"}, by=self.matchmaker)
        intro.save_feedback(case, form="C", data={"discreet": "4"}, by=self.matchmaker)

    def test_no_feedback_before_the_introduction(self):
        case = self.at_introduction()
        self.assertEqual(intro.feedback_forms_for(case), [])
        with self.assertRaises(svc.EliteError):
            intro.save_feedback(case, form="A", data={"discreet": "4"}, by=self.matchmaker)

    def test_daily_run_sends_no_feedback_emails(self):
        self.introduced()
        mail.outbox.clear()
        intro.daily_run(today=date.today() + timedelta(days=3))
        self.assertEqual(mail.outbox, [])

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


# ---------------------------------------------------------------- former Elite clients starting Bronze

from domain.matchmaking.models import ConsultationRequest  # noqa: E402
from domain.matchmaking.services.consultation_request_service import submit_consultation_request  # noqa: E402


class FormerEliteTests(AfterApprovalBase):
    def bronze_client(self, email="mwila@example.com"):
        case = self.paid(email)
        svc.record_outreach(case, delivered=True, sent_on=date.today(), by=self.matchmaker)
        svc.record_answer(case, answer="declined", by=self.matchmaker)
        svc.record_bronze_answer(case, accepted=True, by=self.matchmaker)
        case.refresh_from_db()
        return case

    def request_for(self, email):
        return ConsultationRequest(
            full_name="Mwila Banda", gender="female", age=34, seeking="man", relationship_status="single",
            location="Lusaka", nationality="Zambian", occupation="Lawyer", email=email, phone="+260977000000",
        )

    def test_former_elite_request_is_flagged_and_gets_no_payment_email(self):
        case = self.bronze_client()
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            result = submit_consultation_request(self.request_for("Mwila@Example.com"))
        self.assertEqual(result.consultation_request.former_elite_case, case)
        to_client = [m for m in mail.outbox if "mwila@example.com" in m.to]
        self.assertEqual(len(to_client), 1)
        self.assertIn("Elite Grade", to_client[0].body)
        self.assertNotIn("K1,000", to_client[0].body)
        self.assertTrue(any("former Elite" in m.subject for m in mail.outbox))           # team alert says so
        self.assertTrue(case.events.filter(text__startswith="Started the Bronze journey").exists())

    def test_ordinary_request_is_not_flagged(self):
        self.bronze_client()
        with self.captureOnCommitCallbacks(execute=True):
            result = submit_consultation_request(self.request_for("someone.else@example.com"))
        self.assertIsNone(result.consultation_request.former_elite_case)

    def test_declined_bronze_is_not_flagged(self):
        case = self.paid()
        svc.record_outreach(case, delivered=True, sent_on=date.today(), by=self.matchmaker)
        svc.record_answer(case, answer="declined", by=self.matchmaker)
        svc.record_bronze_answer(case, accepted=False, by=self.matchmaker)
        self.assertIsNone(svc.former_elite_case_for(case.email))

    def test_do_not_approach_tab_lists_the_kept_details(self):
        case = self.bronze_client()
        self.client.force_login(self.admin)
        response = self.client.get(reverse("elite:cases") + "?show=register")
        self.assertContains(response, case.reference)
        self.assertContains(response, "The person declined")
        self.assertContains(response, "Thandi Phiri")                                     # D16: names are shown
        self.assertContains(response, "A friend&#x27;s wedding in Lusaka")
        self.assertNotContains(response, "977")                                           # no phone kept
        self.client.force_login(self.matchmaker)                                         # handlers don't get the tab
        self.assertNotContains(self.client.get(reverse("elite:cases") + "?show=register"), "Do not approach")