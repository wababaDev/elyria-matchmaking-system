from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from domain.base.models import Groups
from domain.base.services.groups import create_groups_and_permissions
from domain.matchmaking.models import Consultation, ConsultationRequest

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


class BaseCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        create_groups_and_permissions()
        cls.admin = make_user("admin@x.com", Groups.ADMIN, first="Ada")
        cls.matchmaker = make_user("mm@x.com", Groups.MATCHMAKER, first="Anisha")

    def url(self, name, c):
        return reverse(f"matchmaking:{name}", args=[c.pk])


class AssignTests(BaseCase):
    def test_admin_assigns_to_matchmaker(self):
        c = make_request()
        self.client.force_login(self.admin)
        self.client.post(self.url("consultation-request-assign-to", c), {"assigned_to": self.matchmaker.pk})
        c.refresh_from_db()
        self.assertEqual(c.assigned_to, self.matchmaker)

    def test_admin_can_unassign(self):
        c = make_request(assigned_to=self.matchmaker)
        self.client.force_login(self.admin)
        self.client.post(self.url("consultation-request-assign-to", c), {"assigned_to": ""})
        c.refresh_from_db()
        self.assertIsNone(c.assigned_to)

    def test_matchmaker_cannot_assign_others(self):
        c = make_request()
        self.client.force_login(self.matchmaker)
        response = self.client.post(self.url("consultation-request-assign-to", c), {"assigned_to": self.matchmaker.pk})
        self.assertEqual(response.status_code, 403)

    def test_list_filter_unassigned(self):
        make_request(full_name="Mine Person", email="a@x.com", assigned_to=self.matchmaker)
        make_request(full_name="Nobody Person", email="b@x.com")
        self.client.force_login(self.admin)
        response = self.client.get(reverse("matchmaking:consultation-requests"), {"assigned": "none"})
        self.assertContains(response, "Nobody Person")
        self.assertNotContains(response, "Mine Person")


class ConsultationTests(BaseCase):
    def setUp(self):
        self.client.force_login(self.matchmaker)

    def test_cannot_book_before_fee_paid(self):
        c = make_request()
        response = self.client.post(self.url("consultation-request-book", c), {"scheduled_for": "2026-11-02T10:00"}, follow=True)
        self.assertContains(response, "once the fee has been paid")
        self.assertFalse(Consultation.objects.exists())

    def test_book_consultation(self):
        c = make_request(status=S.FEE_PAID)
        self.client.post(self.url("consultation-request-book", c), {"scheduled_for": "2026-11-02T10:00"})
        self.assertEqual(timezone.localtime(c.consultation.scheduled_for).hour, 10)

    def test_save_notes(self):
        c = make_request(status=S.FEE_PAID)
        self.client.post(self.url("consultation-request-notes", c), {"notes": "Warm, family-oriented."})
        self.assertEqual(Consultation.objects.get(request=c).notes, "Warm, family-oriented.")

    def test_mark_consulted_needs_notes(self):
        c = make_request(status=S.FEE_PAID)
        response = self.client.post(self.url("consultation-request-mark-consulted", c), {"notes": ""}, follow=True)
        self.assertContains(response, "Add the consultation notes")
        c.refresh_from_db()
        self.assertEqual(c.status, S.FEE_PAID)

    def test_mark_consulted(self):
        c = make_request(status=S.FEE_PAID)
        self.client.post(self.url("consultation-request-mark-consulted", c), {"notes": "Ready to proceed."})
        c.refresh_from_db()
        self.assertEqual(c.status, S.CONSULTED)
        self.assertEqual(c.consultation.conducted_by, self.matchmaker)
        self.assertIsNotNone(c.consultation.held_at)


class QueueTests(BaseCase):
    def setUp(self):
        self.client.force_login(self.matchmaker)

    def test_queue_groups_my_requests(self):
        awaiting = make_request(email="1@x.com", assigned_to=self.matchmaker)
        to_book = make_request(email="2@x.com", status=S.FEE_PAID, assigned_to=self.matchmaker)
        booked = make_request(email="3@x.com", status=S.FEE_PAID, assigned_to=self.matchmaker)
        Consultation.objects.create(request=booked, scheduled_for=timezone.now() + timedelta(days=1))
        make_request(email="4@x.com")  # unassigned: not in my queue

        response = self.client.get(reverse("matchmaking:my-queue"))
        sections = {s["key"]: s["items"] for s in response.context["sections"]}

        self.assertEqual(sections["booked"], [booked])
        self.assertEqual(sections["to-book"], [to_book])
        self.assertEqual(sections["awaiting-payment"], [awaiting])
        self.assertEqual(response.context["staff_queue_count"], 3)
        self.assertEqual(len(response.context["rows"]), 3)

    def test_upcoming_consultations_on_dashboard(self):
        c = make_request(status=S.FEE_PAID, assigned_to=self.matchmaker)
        Consultation.objects.create(request=c, scheduled_for=timezone.now() + timedelta(days=2))
        response = self.client.get(reverse("matchmaking:dashboard"))
        self.assertEqual(len(response.context["upcoming_consultations"]), 1)
    def test_booking_emails_applicant(self):
        c = make_request(status=S.FEE_PAID)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.url("consultation-request-book", c), {"scheduled_for": "2026-11-02T10:00"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [c.email])
        self.assertIn("booked", mail.outbox[0].subject)

    def test_rescheduling_says_so(self):
        c = make_request(status=S.FEE_PAID)
        url = self.url("consultation-request-book", c)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url, {"scheduled_for": "2026-11-02T10:00"})
            self.client.post(url, {"scheduled_for": "2026-11-03T14:00"})
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("rescheduled", mail.outbox[1].subject)

    def test_same_time_sends_no_email(self):
        c = make_request(status=S.FEE_PAID)
        url = self.url("consultation-request-book", c)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url, {"scheduled_for": "2026-11-02T10:00"})
            self.client.post(url, {"scheduled_for": "2026-11-02T10:00"})
        self.assertEqual(len(mail.outbox), 1)