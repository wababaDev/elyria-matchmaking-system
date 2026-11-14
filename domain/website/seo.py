"""
SEO basics for the public website, in one place.

PAGES: the title and description search engines show for each public page, keyed by the page's URL
name (what you'd pass to {% url %}, without the "website:" part). Edit the wording here, not in the
templates. A page not listed falls back to DEFAULT. Wording follows the brief: no prices or fees
(except the consultation fee on Membership), no tier detail, no "dating site" language.

Also here: the sitemap (public pages only), robots.txt, and the "no indexing on UAT" header.
"""
from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.http import HttpResponse
from django.urls import NoReverseMatch, reverse

SITE_NAME = "Elyria Matchmaking"

DEFAULT = {
    "title": "Elyria Matchmaking | Private, human-led matchmaking",
    "description": (
        "Elyria Matchmaking is a bespoke, invitation-led matchmaking concierge for individuals who value "
        "depth, discretion and long-term partnership. No public profiles. No algorithms."
    ),
}

# Rename the keys to match your URL names if they differ (see the check in tests/test_seo.py).
PAGES = {
    "home": DEFAULT,
    "about": {
        "title": "About Us | Elyria Matchmaking",
        "description": "Human-led, guided and selective. Why Elyria exists, and the values behind every introduction: discretion, consent, intentionality, integrity and dignity.",
    },
    "services": {
        "title": "Our Services | Elyria Matchmaking",
        "description": "Bespoke matchmaking, comprehensive verification and vetting, curated date experiences, and private relationship and dating advisory.",
    },
    "who-we-serve": {
        "title": "Who We Serve | Elyria Matchmaking",
        "description": "Discreet matchmaking for high-net-worth individuals, professionals and executives, faith-oriented singles, and expatriates and the diaspora.",
    },
    "membership": {
        "title": "Membership | Elyria Matchmaking",
        "description": "Bronze, Silver, Gold and Elite Grade membership: personalised matchmaking, professional vetting and dedicated support, tailored to the level of service you need.",
    },
    "team": {
        "title": "Our Team | Elyria Matchmaking",
        "description": "Meet the Elyria matchmakers: corporate, international and faith-based matchmaking led by founder and CEO Anisha Namutowe.",
    },
    "events": {
        "title": "Events | Elyria Matchmaking",
        "description": "Elyria Social Events: a relaxed way to experience the Elyria community before you apply.",
    },
    "faq": {
        "title": "Frequently Asked Questions | Elyria Matchmaking",
        "description": "How Elyria works: who it's for, the private consultation, confidentiality, consent and what to expect.",
    },
    "privacy": {
        "title": "Privacy Policy | Elyria Matchmaking",
        "description": "How Elyria Matchmaking collects, uses and protects your personal information.",
    },
}

# Public pages listed in the sitemap, in this order. Forms, sign-in, the portal and Elite pages are left out on purpose.
SITEMAP_PAGES = ["home", "about", "services", "who-we-serve", "membership", "team", "events", "faq", "privacy"]
URL_NAMESPACE = "website"

# Never shown to search engines, even on the live site
PRIVATE_PREFIXES = ["/management/", "/portal/", "/elite/", "/sign-in/", "/sign-out/", "/admin/", "/accounts/"]


def _is_uat():
    return getattr(settings, "ENVIRONMENT", "") == "uat"


def site_url():
    return getattr(settings, "SITE_URL", "").rstrip("/")


def seo(request):
    """Context processor: {{ seo.title }}, {{ seo.description }}, {{ seo.canonical }}, {{ seo.noindex }}."""
    match = getattr(request, "resolver_match", None)
    name = match.url_name if match else ""
    page = PAGES.get(name, DEFAULT)
    path = request.path
    return {"seo": {
        "title": page["title"],
        "description": page["description"],
        "canonical": site_url() + path,
        "site_name": SITE_NAME,
        "site_url": site_url(),
        "noindex": _is_uat() or any(path.startswith(p) for p in PRIVATE_PREFIXES),
    }}


class StaticPagesSitemap(Sitemap):
    protocol = "https"
    changefreq = "monthly"

    def items(self):
        names = []
        for name in SITEMAP_PAGES:
            try:
                reverse(f"{URL_NAMESPACE}:{name}")
                names.append(name)
            except NoReverseMatch:
                continue  # a page that doesn't exist (yet) is skipped rather than breaking the sitemap
        return names

    def location(self, item):
        return reverse(f"{URL_NAMESPACE}:{item}")

    def priority(self, item):
        return 1.0 if item == "home" else 0.6


SITEMAPS = {"pages": StaticPagesSitemap}


def robots_txt(request):
    if _is_uat():
        lines = ["User-agent: *", "Disallow: /"]  # UAT is never indexed
    else:
        lines = ["User-agent: *"] + [f"Disallow: {p}" for p in PRIVATE_PREFIXES] + ["", f"Sitemap: {site_url()}/sitemap.xml"]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")