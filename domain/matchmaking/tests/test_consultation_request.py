from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from domain.matchmaking.forms import ConsultationRequestForm
from domain.matchmaking.models import ConsultationRequest
from domain.matchmaking.services.consultation_request_service import (
    NotEligibleError,
    submit_consultation_request,
)

VALID = {
    "full_name": "Natasha Kabwe",
    "preferred_name": "Natasha",
    "gender": "female",
    "age": "34",
    "seeking": "man",
    "relationship_status": "single",
    "location": "Lusaka, Zambia",
    "nationality": "Zambian",
    "occupation": "Accountant",
    "email": "Natasha@Example.com",
    "phone": "+260977000000",
}


def candidate(**overrides):
    form = ConsultationRequestForm(data={**VALID, **overrides})
    assert form.is_valid(), form.errors
    return form.save(commit=False)


class FormTests(TestCase):
    def form(self, **overrides):
        return ConsultationRequestForm(data={**VALID, **overrides})

    def test_valid(self):
        self.assertTrue(self.form().is_valid())

    def test_age_limits(self):
        self.assertFalse(self.form(age="19").is_valid())
        self.assertFalse(self.form(age="91").is_valid())
        self.assertTrue(self.form(age="20").is_valid())
        self.assertTrue(self.form(age="90").is_valid())

    def test_married_and_separated_blocked(self):
        for status in ("married", "separated"):
            form = self.form(relationship_status=status)
            self.assertFalse(form.is_valid())
            self.assertTrue(form.has_error("relationship_status", code="not_eligible"))

    def test_email_lowercased(self):
        form = self.form()
        form.is_valid()
        self.assertEqual(form.cleaned_data["email"], "natasha@example.com")


class ServiceTests(TestCase):
    def test_creates_request_and_sends_two_emails(self):
        with self.captureOnCommitCallbacks(execute=True):
            result = submit_consultation_request(candidate())

        self.assertTrue(result.created)
        self.assertEqual(result.consultation_request.status, ConsultationRequest.Status.AWAITING_PAYMENT)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].to, ["natasha@example.com"])
        self.assertIn("New consultation request", mail.outbox[1].subject)

    def test_duplicate_open_request_is_not_created(self):
        with self.captureOnCommitCallbacks(execute=True):
            submit_consultation_request(candidate())
        mail.outbox.clear()

        with self.captureOnCommitCallbacks(execute=True):
            result = submit_consultation_request(candidate(email="NATASHA@example.com"))

        self.assertFalse(result.created)
        self.assertEqual(ConsultationRequest.objects.count(), 1)
        self.assertEqual(result.consultation_request.resubmission_count, 1)
        self.assertEqual(len(mail.outbox), 0)

    def test_closed_request_allows_a_new_one(self):
        first = submit_consultation_request(candidate()).consultation_request
        first.status = ConsultationRequest.Status.CLOSED
        first.save()

        result = submit_consultation_request(candidate())
        self.assertTrue(result.created)
        self.assertEqual(ConsultationRequest.objects.count(), 2)

    def test_blocked_status_rejected_by_service_too(self):
        blocked = candidate()
        blocked.relationship_status = ConsultationRequest.RelationshipStatus.MARRIED
        with self.assertRaises(NotEligibleError):
            submit_consultation_request(blocked)
        self.assertEqual(ConsultationRequest.objects.count(), 0)


class ViewTests(TestCase):
    url = reverse("website:consultation-request")

    def setUp(self):
        cache.clear()

    def test_page_loads(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_valid_post_redirects_to_thanks(self):
        response = self.client.post(self.url, VALID)
        self.assertRedirects(response, reverse("website:consultation-thanks"), fetch_redirect_response=False)
        self.assertEqual(ConsultationRequest.objects.count(), 1)

    def test_blocked_status_shows_message_and_saves_nothing(self):
        response = self.client.post(self.url, {**VALID, "relationship_status": "married"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "married or separated")
        self.assertEqual(ConsultationRequest.objects.count(), 0)

    def test_honeypot_saves_nothing(self):
        response = self.client.post(self.url, {**VALID, "website": "spam.example"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ConsultationRequest.objects.count(), 0)

    def test_rate_limited_after_five_attempts(self):
        for _ in range(5):
            self.client.post(self.url, {})
        response = self.client.post(self.url, VALID)
        self.assertContains(response, "Too many requests")
        self.assertEqual(ConsultationRequest.objects.count(), 0)