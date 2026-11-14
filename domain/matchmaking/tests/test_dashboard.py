from django.test import TestCase

from domain.matchmaking.services.dashboard_service import TREND_MONTHS, dashboard_summary


class DashboardSummaryTests(TestCase):
    def test_empty_system_gives_zeros_not_errors(self):
        summary = dashboard_summary()
        self.assertEqual(summary["requests_this_month"], 0)
        self.assertEqual(summary["active_members"], 0)
        self.assertEqual(summary["introductions_this_month"], 0)
        self.assertEqual(len(summary["trend"]["labels"]), TREND_MONTHS)
        self.assertEqual(summary["funnel"]["values"], [0, 0, 0, 0])
        self.assertEqual(summary["elite"]["under_review"], 0)