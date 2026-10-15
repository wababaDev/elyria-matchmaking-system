from .base import *  # noqa: F401,F403
from .base import BASE_DIR, env

DEBUG = True
SECRET_KEY = env("SECRET_KEY", default="local-dev-only-not-secret")
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

DATABASES = {"default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")}

EMAIL_BACKEND = env("EMAIL_BACKEND", default="notification.backends.OneLineConsoleBackend")

CELERY_TASK_ALWAYS_EAGER = True