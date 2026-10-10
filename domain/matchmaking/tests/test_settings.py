import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from domain.base.models import Groups
from domain.base.services.groups import create_groups_and_permissions
from domain.matchmaking.models import ConsultationRequest, MembershipTier
from domain.matchmaking.services.consultation_request_service import submit_consultation_request
from domain.website.models import SiteDocument, SiteSettings

User = get_user_model()
MEDIA = tempfile.mkdtemp()


def make_user(email, *groups):
    user = User.objects.create_user(email=email, password="pass12345", first_name="Ada", last_name="Admin")
    user.groups.add(*Group.objects.filter(name__in=groups))
    return user


@override_settings(MEDIA_ROOT=MEDIA)
class SettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        create_groups_and_permissions()
        cls.admin = make_user("admin@x.com", Groups.ADMIN)
        cls.matchmaker = make_user("mm@x.com", Groups.MATCHMAKER)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.client.force_login(self.admin)

    def test_matchmaker_cannot_open_settings(self):
        self.client.force_login(self.matchmaker)
        self.assertEqual(self.client.get(reverse("matchmaking:settings-general")).status_code, 403)

    def test_add_staff_member_sends_invite(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("matchmaking:settings-staff-add"), {
                "first_name": "Anisha", "last_name": "Namutowe", "email": "Anisha@Elyria.com",
                "job_title": "Senior Matchmaker", "role": Groups.MATCHMAKER,
            })
        user = User.objects.get(email="anisha@elyria.com")
        self.assertTrue(user.groups.filter(name=Groups.MATCHMAKER).exists())
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.profile.job_title, "Senior Matchmaker")
        self.assertIn("/account/set-password/", mail.outbox[0].body)

    def test_cannot_remove_own_admin_access(self):
        response = self.client.post(reverse("matchmaking:settings-staff-edit", args=[self.admin.pk]), {
            "first_name": "Ada", "last_name": "Admin", "job_title": "", "role": Groups.MATCHMAKER, "is_active": "on",
        })
        self.assertContains(response, "can't remove your own admin access")
        self.assertTrue(self.admin.groups.filter(name=Groups.ADMIN).exists())

    def test_deactivate_staff(self):
        self.client.post(reverse("matchmaking:settings-staff-edit", args=[self.matchmaker.pk]), {
            "first_name": "Ada", "last_name": "Admin", "job_title": "", "role": Groups.MATCHMAKER,
        })
        self.matchmaker.refresh_from_db()
        self.assertFalse(self.matchmaker.is_active)

    def test_edit_tier(self):
        gold = MembershipTier.objects.get(name="Gold")
        self.client.post(reverse("matchmaking:settings-tiers-edit", args=[gold.pk]), {
            "name": "Gold", "price": "15000", "currency": "ZMW",
            "duration_months": "12", "display_order": "3", "is_active": "on",
        })
        gold.refresh_from_db()
        self.assertEqual(str(gold.price), "15000.00")

    def test_payment_email_uses_settings(self):
        site = SiteSettings.load()
        site.bank_details = "Zanaco, Elyria Matchmaking Ltd, 0123456789"
        site.save()
        with self.captureOnCommitCallbacks(execute=True):
            submit_consultation_request(ConsultationRequest(
                full_name="Grace Lungu", gender="female", age=30, seeking="man",
                relationship_status="single", location="Lusaka", nationality="Zambian",
                occupation="Nurse", email="grace@example.com", phone="+260977000000",
            ))
        body = mail.outbox[0].body
        self.assertIn("K1,000", body)
        self.assertIn("Zanaco", body)

    def test_upload_privacy_policy(self):
        pdf = SimpleUploadedFile("policy.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        self.client.post(reverse("matchmaking:settings-documents"), {"file": pdf})
        self.assertIsNotNone(SiteDocument.current(SiteDocument.Kind.PRIVACY_POLICY))

        response = self.client.get(reverse("website:privacy"))
        self.assertContains(response, "Download PDF")

    def test_non_pdf_rejected(self):
        fake = SimpleUploadedFile("policy.pdf", b"not a pdf", content_type="application/pdf")
        response = self.client.post(reverse("matchmaking:settings-documents"), {"file": fake})
        self.assertContains(response, "valid PDF")
        self.assertIsNone(SiteDocument.current(SiteDocument.Kind.PRIVACY_POLICY))

    def test_privacy_page_hides_button_without_document(self):
        response = self.client.get(reverse("website:privacy"))
        self.assertNotContains(response, "Download PDF")