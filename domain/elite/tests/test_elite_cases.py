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
    def test_admin_only_and_every_view_logged(self):
        case = self.apply()
        self.client.force_login(self.matchmaker)
        self.assertEqual(self.client.get(reverse("elite:cases")).status_code, 403)
        self.assertEqual(self.client.get(reverse("elite:case-detail", args=[case.pk])).status_code, 403)

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