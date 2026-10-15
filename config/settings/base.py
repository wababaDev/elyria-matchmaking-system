from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # base.py → settings/ → config/ → project root

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")  # does nothing if there's no .env

ENVIRONMENT = env("ENVIRONMENT", default="local")  # local / uat / prod

# SECRET_KEY, DEBUG, ALLOWED_HOSTS, DATABASES and EMAIL_BACKEND live in local.py / production.py

# ---------------------------------------------------------------- Apps
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "domain.base",
    "domain.website",
    "domain.matchmaking",
    "domain.portal",
    "notification",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "domain.base.context_processors.environment",
                "domain.website.context_processors.consultation_form",
                "domain.website.context_processors.site_settings",
                "domain.matchmaking.context_processors.staff_queue",
            ],
        },
    },
]

# ---------------------------------------------------------------- Auth
AUTH_USER_MODEL = "base.User"
LOGIN_URL = "base:sign-in"
STAFF_LOGIN_URL = "base:staff-sign-in"
MEMBER_HOME_URL = "/portal/"
STAFF_HOME_URL = "matchmaking:dashboard"
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24 * 7  # set-password links: 7 days

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------- Locale
LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Lusaka"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------- Files
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---------------------------------------------------------------- Email
EMAIL_HOST = env("EMAIL_HOST", default="smtppro.zoho.com")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Elyria Matchmaking <info@example.com>")  # TODO: real Zoho address
TEAM_INBOX_EMAIL = env("TEAM_INBOX_EMAIL", default="info@example.com")  # TODO: real team inbox
EMAIL_SUBJECT_TAG = ""  # "[UAT]" on UAT, see production.py

# ---------------------------------------------------------------- Site
SITE_URL = env("SITE_URL", default="http://127.0.0.1:2004")  # used for links in emails

# Behind Caddy, the visitor's address comes from X-Forwarded-For (see domain/base/http.py)
TRUST_PROXY_HEADERS = False