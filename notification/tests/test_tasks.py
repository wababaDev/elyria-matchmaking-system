from django.core import mail
from django.test import TestCase

from notification.tasks import send_member_welcome_email, send_payment_instructions_email


class EmailTaskTests(TestCase):
    def test_missing_records_are_skipped_quietly(self):
        send_payment_instructions_email(999999)
        send_member_welcome_email(999999)
        self.assertEqual(len(mail.outbox), 0)