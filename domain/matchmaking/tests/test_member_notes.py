from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from domain.base.models import Groups
from domain.base.services.groups import create_groups_and_permissions
from domain.matchmaking.models import (
    Client,
    ClientProfile,
    ConsultationRequest,
    MemberNote,
    Membership,
    MembershipTier,
)
from domain.matchmaking.services.profile_service import save_profile

User = get_user_model()


def make_user(email, *groups):
    user = User.objects.create_user(email=email, password="pass12345", first_name="Test", last_name="User")
    user.groups.add(*Group.objects.filter(name__in=groups))
    return user


class NotesCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        create_groups_and_permissions()
        cls.matchmaker = make_user("mm@x.com", Groups.MATCHMAKER)
        cls.other_matchmaker = make_user("mm2@x.com", Groups.MATCHMAKER)
        cls.finance = make_user("fin@x.com", Groups.FINANCE)
        request = ConsultationRequest.objects.create(
            full_name="Natasha Kabwe", preferred_name="Natasha", gender="female", age=34, seeking="man",
            relationship_status="single", location="Lusaka, Zambia", nationality="Zambian",
            occupation="Accountant", email="natasha@example.com", phone="+260977000000",
            status=ConsultationRequest.Status.BECAME_MEMBER,
        )
        cls.member = Client.objects.create(
            user=make_user("natasha@example.com", Groups.MEMBER), consultation_request=request,
            full_name="Natasha Kabwe", preferred_name="Natasha", matchmaker=cls.matchmaker,
        )
        Membership.objects.create(
            client=cls.member, tier=MembershipTier.objects.get(name="Gold"),
            start_date=date(2026, 1, 1), end_date=date(2027, 1, 1),
        )

    def setUp(self):
        self.client.force_login(self.matchmaker)

    def url(self, name, *extra):
        return reverse(f"matchmaking:{name}", args=[self.member.pk, *extra])

    def add_discrepancy(self):
        return self.client.post(self.url("member-note-discrepancy"), {
            "subject": "Time since last relationship ended",
            "consultation_answer": "About three years",
            "profile_answer": "6–12 months",
            "difference": "material",
            "body": "Consultation says three years. Form says 6–12 months.",
            "follow_up": "call",
        })


class AddAndCloseTests(NotesCase):
    def test_add_observation(self):
        self.client.post(self.url("member-note-observation"), {"category": "readiness", "body": "Hesitant about family."})
        note = MemberNote.objects.get()
        self.assertEqual(note.kind, "observation")
        self.assertEqual(note.author, self.matchmaker)
        self.assertEqual(note.status, "")

    def test_discrepancy_is_open_until_closed_with_a_note(self):
        self.add_discrepancy()
        note = MemberNote.objects.get()
        self.assertTrue(note.is_open)
        self.assertTrue(note.affects_matching)

        self.client.post(self.url("member-note-close", note.pk), {"outcome": "no_concern", "resolution": ""})
        note.refresh_from_db()
        self.assertTrue(note.is_open)

        self.client.post(self.url("member-note-close", note.pk), {"outcome": "no_concern", "resolution": "Meant 3 years since divorce."})
        note.refresh_from_db()
        self.assertFalse(note.is_open)
        self.assertEqual(note.closed_by, self.matchmaker)

    def test_member_page_shows_notes(self):
        self.add_discrepancy()
        response = self.client.get(self.url("member-detail"))
        self.assertContains(response, "Time since last relationship ended")
        self.assertContains(response, "1</strong> open discrepancy")


class HistoryTests(NotesCase):
    def test_edit_keeps_old_text(self):
        self.client.post(self.url("member-note-observation"), {"category": "other", "body": "First version"})
        note = MemberNote.objects.get()
        self.client.post(self.url("member-note-edit", note.pk), {"body": "Second version"})
        note.refresh_from_db()
        self.assertEqual(note.body, "Second version")
        self.assertEqual(note.revisions.get().previous_body, "First version")

    def test_only_the_author_can_edit(self):
        note = MemberNote.objects.create(client=self.member, kind="observation", author=self.other_matchmaker, body="Theirs")
        self.client.post(self.url("member-note-edit", note.pk), {"body": "Changed"})
        note.refresh_from_db()
        self.assertEqual(note.body, "Theirs")

    def test_there_is_no_way_to_delete(self):
        self.add_discrepancy()
        note = MemberNote.objects.get()
        # No delete URL exists, and a GET to the action URLs is refused
        self.assertEqual(self.client.get(self.url("member-note-close", note.pk)).status_code, 405)
        self.assertEqual(MemberNote.objects.count(), 1)


class AccessTests(NotesCase):
    def test_other_matchmaker_gets_404(self):
        self.client.force_login(self.other_matchmaker)
        self.client.post(self.url("member-note-observation"), {"category": "other", "body": "x"})
        self.assertFalse(MemberNote.objects.exists())

    def test_finance_gets_403_and_sees_no_notes(self):
        MemberNote.objects.create(client=self.member, kind="observation", author=self.matchmaker, body="Private observation")
        self.client.force_login(self.finance)
        response = self.client.post(self.url("member-note-observation"), {"category": "other", "body": "x"})
        self.assertEqual(response.status_code, 403)
        self.assertNotContains(self.client.get(self.url("member-detail")), "Private observation")

    def test_member_cannot_reach_notes(self):
        self.client.force_login(self.member.user)
        response = self.client.post(self.url("member-note-observation"), {"category": "other", "body": "x"})
        self.assertIn(response.status_code, (302, 403))
        self.assertFalse(MemberNote.objects.exists())


# These profiles skip the "every required answer filled" check: that's tested in the portal tests
@mock.patch("domain.matchmaking.services.profile_service.incomplete_sections", return_value=[])
class ProfileChangeTests(NotesCase):
    def setUp(self):
        super().setUp()
        self.profile = ClientProfile.objects.create(
            client=self.member, occupation="Accountant", hobbies="Reading", completed_at=timezone.now()
        )

    def test_edit_after_completion_logs_each_change(self, _):
        self.profile.occupation = "Teacher"
        self.profile.hobbies = "Hiking"
        with self.captureOnCommitCallbacks(execute=True):
            save_profile(self.profile)
        notes = {n.subject: n for n in MemberNote.objects.filter(kind="profile_change")}
        self.assertEqual(notes["Occupation / profession"].first_value, "Accountant")
        self.assertEqual(notes["Occupation / profession"].second_value, "Teacher")
        self.assertTrue(notes["Occupation / profession"].affects_matching)
        self.assertFalse(notes["Hobbies"].affects_matching)
        self.assertTrue(all(n.is_open and n.by_system for n in notes.values()))

    def test_relationship_status_can_now_be_married(self, _):
        self.profile.relationship_status = "married"
        with self.captureOnCommitCallbacks(execute=True):
            save_profile(self.profile)
        note = MemberNote.objects.get(kind="profile_change")
        self.assertEqual(note.second_value, "Married")
        self.assertTrue(note.affects_matching)