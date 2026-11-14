from django.test import SimpleTestCase

from domain.matchmaking.services.renewal_reminder_service import due_reminder


class DueReminderTests(SimpleTestCase):
    def test_each_reminder_once(self):
        self.assertIsNone(due_reminder(61, None))
        self.assertEqual(due_reminder(60, None), 60)
        self.assertIsNone(due_reminder(59, 60))           # already sent
        self.assertEqual(due_reminder(30, 60), 30)
        self.assertIsNone(due_reminder(20, 30))
        self.assertEqual(due_reminder(14, 30), 14)
        self.assertIsNone(due_reminder(3, 14))

    def test_missed_days_send_only_the_latest(self):
        self.assertEqual(due_reminder(25, None), 30)      # job was off: send the 30-day one, not 60 and 30
        self.assertEqual(due_reminder(10, 60), 14)

    def test_expired_or_far_away_sends_nothing(self):
        self.assertIsNone(due_reminder(-1, None))
        self.assertIsNone(due_reminder(200, None))