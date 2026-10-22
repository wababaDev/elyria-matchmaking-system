import io
import shutil
import tempfile
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from domain.base.models import Groups
from domain.base.services.groups import create_groups_and_permissions
from domain.matchmaking.models import (
    Client,
    ClientProfile,
    ConsultationRequest,
    Membership,
    MembershipTier,
    ProfilePhoto,
)
from domain.matchmaking.profile_sections import CHECKS, CHIPS, FIELD_NAMES, FIELDS_BY_NAME, SCALE, SELECT, SLIDER
from domain.portal.forms.portal_forms import ProfileForm

User = get_user_model()
PRIVATE_ROOT = tempfile.mkdtemp()

NUMBERS = {"age": 34, "previous_marriages": 0, "children_count": 1, "partner_age_min": 30, "partner_age_max": 45}


def make_user(email, *groups, password="pass12345"):
    user = User.objects.create_user(email=email, password=password, first_name="Test", last_name="User")
    user.groups.add(*Group.objects.filter(name__in=groups))
    return user


def make_member(email, matchmaker=None):
    request = ConsultationRequest.objects.create(
        full_name="Natasha Kabwe", preferred_name="Natasha", gender="female", age=34, seeking="man",
        relationship_status="single", location="Lusaka, Zambia", nationality="Zambian",
        occupation="Accountant", email=email, phone="+260977000000",
        status=ConsultationRequest.Status.BECAME_MEMBER,
    )
    client = Client.objects.create(
        user=make_user(email, Groups.MEMBER), consultation_request=request,
        full_name="Natasha Kabwe", preferred_name="Natasha", matchmaker=matchmaker,
    )
    Membership.objects.create(
        client=client, tier=MembershipTier.objects.get(name="Gold"),
        start_date=date(2026, 1, 1), end_date=date(2027, 1, 1),
    )
    return client


def image_file(name="photo.png"):
    buffer = io.BytesIO()
    Image.new("RGB", (40, 50), "maroon").save(buffer, "PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def full_answers():
    """A POST with every required answer filled in."""
    form = ProfileForm()
    data = {}
    for name in FIELD_NAMES:
        kind = FIELDS_BY_NAME[name].kind
        if name in NUMBERS:
            data[name] = NUMBERS[name]
        elif kind in (SLIDER, SCALE):
            data[name] = 3
        elif kind in (SELECT, CHIPS):
            data[name] = next(value for value, _ in form.fields[name].choices if value != "")
        elif kind == CHECKS:
            data[name] = ["honesty", "family"]
        else:
            data[name] = "An answer"
    data["has_children"] = "no"
    data["non_negotiables"] = ["Must not smoke"]
    return data


@override_settings(PRIVATE_MEDIA_ROOT=PRIVATE_ROOT)
class PortalCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        create_groups_and_permissions()
        cls.matchmaker = make_user("mm@x.com", Groups.MATCHMAKER)
        cls.other_matchmaker = make_user("mm2@x.com", Groups.MATCHMAKER)
        cls.finance = make_user("fin@x.com", Groups.FINANCE)
        cls.member = make_member("natasha@example.com", matchmaker=cls.matchmaker)
        cls.other = make_member("grace@example.com")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(PRIVATE_ROOT, ignore_errors=True)

    def setUp(self):
        self.client.force_login(self.member.user)

    def post_profile(self, data, action="save"):
        return self.client.post(reverse("portal:profile"), {**data, "action": action})

    def profile(self):
        return ClientProfile.objects.get(client=self.member)


class AccessTests(PortalCase):
    def test_home_sends_new_member_to_profile(self):
        self.assertRedirects(self.client.get(reverse("portal:home")), reverse("portal:profile"))

    def test_pages_open(self):
        for name in ("profile", "matches", "account"):
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(f"portal:{name}")).status_code, 200)

    def test_staff_cannot_open_portal(self):
        self.client.force_login(self.matchmaker)
        self.assertEqual(self.client.get(reverse("portal:profile")).status_code, 403)

    def test_signed_out_goes_to_sign_in(self):
        self.client.logout()
        response = self.client.get(reverse("portal:profile"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("sign-in", response["Location"])


class ProfileTests(PortalCase):
    def test_first_visit_prefills_from_request(self):
        self.client.get(reverse("portal:profile"))
        profile = self.profile()
        self.assertEqual(profile.age, 34)
        self.assertEqual(profile.location, "Lusaka, Zambia")
        self.assertEqual(profile.partner_gender, "male")

    def test_save_progress_keeps_partial_answers(self):
        self.client.get(reverse("portal:profile"))
        response = self.post_profile({"full_name": "Natasha Kabwe", "hobbies": "Reading", "core_values": ["honesty"]})
        self.assertRedirects(response, reverse("portal:profile"))
        profile = self.profile()
        self.assertEqual(profile.hobbies, "Reading")
        self.assertEqual(profile.core_values, ["honesty"])
        self.assertFalse(profile.is_complete)

    def test_mark_complete_with_gaps_saves_but_lists_whats_missing(self):
        response = self.post_profile({"hobbies": "Reading"}, action="complete")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Still needed")
        self.assertEqual(self.profile().hobbies, "Reading")
        self.assertFalse(self.profile().is_complete)

    def test_photo_is_required_to_complete(self):
        response = self.post_profile(full_answers(), action="complete")
        self.assertContains(response, "At least one profile photo")
        self.assertFalse(self.profile().is_complete)

    def test_mark_complete_alerts_matchmaker(self):
        data = {**full_answers(), "photo_close_up": image_file()}
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post_profile(data, action="complete")
        self.assertRedirects(response, reverse("portal:profile"))
        profile = self.profile()
        self.assertTrue(profile.is_complete)
        self.assertEqual(profile.photos.count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["mm@x.com"])
        self.assertRedirects(self.client.get(reverse("portal:home")), reverse("portal:matches"))

    def test_completed_profile_cannot_lose_required_answers(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.post_profile({**full_answers(), "photo_close_up": image_file()}, action="complete")
        data = {**full_answers(), "hobbies": ""}
        response = self.post_profile(data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.profile().hobbies, "An answer")

    def test_children_details_only_needed_with_children(self):
        data = {**full_answers(), "has_children": "yes", "children_count": "", "photo_close_up": image_file()}
        response = self.post_profile(data, action="complete")
        self.assertContains(response, "How many?")
        self.assertFalse(self.profile().is_complete)

    def test_non_negotiables_capped_at_five(self):
        data = {"non_negotiables": [f"Rule {n}" for n in range(6)]}
        response = self.post_profile(data)
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(len(self.profile().non_negotiables), 6)

    def test_partner_age_range_must_make_sense(self):
        response = self.post_profile({"partner_age_min": 50, "partner_age_max": 30})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.profile().partner_age_min)

    def test_new_photo_replaces_old_one(self):
        self.post_profile({"photo_close_up": image_file("a.png")})
        self.post_profile({"photo_close_up": image_file("b.png")})
        self.assertEqual(self.profile().photos.filter(kind=ProfilePhoto.Kind.CLOSE_UP).count(), 1)


class PhotoPrivacyTests(PortalCase):
    def setUp(self):
        super().setUp()
        self.post_profile({"photo_close_up": image_file()})
        self.photo = self.profile().photos.get()

    def test_member_sees_own_photo(self):
        self.assertEqual(self.client.get(reverse("portal:photo", args=[self.photo.pk])).status_code, 200)

    def test_other_member_cannot(self):
        self.client.force_login(self.other.user)
        self.assertEqual(self.client.get(reverse("portal:photo", args=[self.photo.pk])).status_code, 404)

    def test_assigned_matchmaker_can(self):
        self.client.force_login(self.matchmaker)
        url = reverse("matchmaking:member-photo", args=[self.member.pk, self.photo.pk])
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_other_matchmaker_and_finance_cannot(self):
        url = reverse("matchmaking:member-photo", args=[self.member.pk, self.photo.pk])
        self.client.force_login(self.other_matchmaker)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.finance)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_staff_member_page_shows_profile(self):
        self.client.force_login(self.matchmaker)
        response = self.client.get(reverse("matchmaking:member-detail", args=[self.member.pk]))
        self.assertContains(response, "Self-Service Profile")


class AccountTests(PortalCase):
    def post(self, data):
        return self.client.post(reverse("portal:account"), data)

    def test_change_phone(self):
        self.post({"form": "contact", "email": "natasha@example.com", "phone": "+260966111111"})
        self.assertEqual(self.profile().phone, "+260966111111")

    def test_email_change_needs_password(self):
        response = self.post({"form": "contact", "email": "new@example.com", "phone": "1"})
        self.assertEqual(response.status_code, 200)
        self.member.user.refresh_from_db()
        self.assertEqual(self.member.user.email, "natasha@example.com")

        self.post({"form": "contact", "email": "new@example.com", "phone": "1", "current_password": "pass12345"})
        self.member.user.refresh_from_db()
        self.assertEqual(self.member.user.email, "new@example.com")

    def test_email_already_used_is_refused(self):
        response = self.post({
            "form": "contact", "email": "grace@example.com", "phone": "1", "current_password": "pass12345",
        })
        self.assertEqual(response.status_code, 200)
        self.member.user.refresh_from_db()
        self.assertEqual(self.member.user.email, "natasha@example.com")

    def test_change_password_keeps_member_signed_in(self):
        response = self.post({
            "form": "password", "old_password": "pass12345",
            "new_password1": "A-much-better-pass-2026", "new_password2": "A-much-better-pass-2026",
        })
        self.assertRedirects(response, reverse("portal:account"))
        self.member.user.refresh_from_db()
        self.assertTrue(self.member.user.check_password("A-much-better-pass-2026"))
        self.assertEqual(self.client.get(reverse("portal:account")).status_code, 200)