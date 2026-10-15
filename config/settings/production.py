from .base import *  # noqa: F401,F403
from .base import ENVIRONMENT, env

DEBUG = False

# Required: the app refuses to start if any of these are missing
SECRET_KEY = env("SECRET_KEY")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS")  # e.g. https://uat.example.com

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = 60

# Shared between Gunicorn workers (rate limiting); table made by `createcachetable`
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    }
}

# Static files served by WhiteNoise with cache-busting file names
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# ---- Behind Caddy (HTTPS ends at Caddy)
TRUST_PROXY_HEADERS = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
# Turn on once HTTPS is confirmed working (start small, e.g. 3600, then 31536000)
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)

# ---- Email: real SMTP; UAT emails get "[UAT]" in the subject
EMAIL_BACKEND = env("EMAIL_BACKEND", default="notification.backends.EnvironmentTaggedSMTPBackend")
EMAIL_SUBJECT_TAG = "[UAT]" if ENVIRONMENT == "uat" else ""

# ---- Logs go to `docker compose logs`
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False}},
}