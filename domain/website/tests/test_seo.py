from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from domain.website import seo


class SeoTests(TestCase):
    def test_every_sitemap_page_exists(self):
        """If this fails, rename the key in seo.PAGES / SITEMAP_PAGES to your real URL name."""
        missing = []
        for name in seo.SITEMAP_PAGES:
            try:
                reverse(f"{seo.URL_NAMESPACE}:{name}")
            except NoReverseMatch:
                missing.append(name)
        self.assertEqual(missing, [], f"No URL named: {missing}")

    @override_settings(ENVIRONMENT="production", SITE_URL="https://elyriamatchmaking.com")
    def test_live_robots_hides_private_areas_and_lists_sitemap(self):
        body = self.client.get("/robots.txt").content.decode()
        self.assertIn("Disallow: /management/", body)
        self.assertIn("Disallow: /elite/", body)
        self.assertIn("Sitemap: https://elyriamatchmaking.com/sitemap.xml", body)
        self.assertNotIn("Disallow: /\n", body)

    @override_settings(ENVIRONMENT="uat")
    def test_uat_is_never_indexed(self):
        self.assertIn("Disallow: /\n", self.client.get("/robots.txt").content.decode())

    def test_sitemap_lists_public_pages_only(self):
        body = self.client.get("/sitemap.xml").content.decode()
        self.assertIn("<loc>", body)
        for private in ("/management/", "/portal/", "/elite/"):
            self.assertNotIn(private, body)

    def test_home_page_has_title_description_and_canonical(self):
        body = self.client.get(reverse(f"{seo.URL_NAMESPACE}:home")).content.decode()
        self.assertIn('<meta name="description"', body)
        self.assertIn('rel="canonical"', body)