from django.template.loader import render_to_string
from django.test import TestCase


class ErrorPageTests(TestCase):
    def test_404_uses_branded_page(self):
        response = self.client.get("/this-page-does-not-exist/")
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")
        self.assertContains(response, "Page not found", status_code=404)

    def test_standalone_pages_render_without_context(self):
        # Django renders these with no request, so they must never depend on one
        for name in ("500.html", "400.html", "403_csrf.html"):
            with self.subTest(page=name):
                self.assertIn("Elyria Matchmaking", render_to_string(name))