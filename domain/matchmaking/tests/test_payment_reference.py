import re

from django.core import mail
from django.test import TestCase

from domain.matchmaking.models import ConsultationRequest
from notification.services.consultation_emails import deliver_payment_instructions


def make_request(**overrides):
    data = {
        "full_name": "Natasha Kabwe", "preferred_name": "Natasha", "gender": "female", "age": 34,
        "seeking": "man", "relationship_status": "single", "location": "Lusaka, Zambia",
        "nationality": "Zambian", "occupation": "Accountant", "email": "natasha@example.com",
        "phone": "+260977000000",
    }
    data.update(overrides)
    return ConsultationRequest.objects.create(**data)


class PaymentReferenceTests(TestCase):
    def test_generated_on_create(self):
        c = make_request()
        self.assertRegex(c.payment_reference, r"^EL-[A-HJ-NP-Z2-9]{6}$")

    def test_unique_per_request(self):
        refs = {make_request(email=f"{i}@x.com").payment_reference for i in range(20)}
        self.assertEqual(len(refs), 20)

    def test_kept_when_saved_again(self):
        c = make_request()
        original = c.payment_reference
        c.phone = "+260966000000"
        c.save()
        c.refresh_from_db()
        self.assertEqual(c.payment_reference, original)

    def test_in_payment_email(self):
        c = make_request()
        deliver_payment_instructions(c)
        self.assertIn(c.payment_reference, mail.outbox[0].body)
        html = mail.outbox[0].alternatives[0][0]
        self.assertIn(c.payment_reference, html)