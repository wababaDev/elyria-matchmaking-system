from django.apps import AppConfig


class BaseConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'domain.base'

    def ready(self):
        from domain.base import signals  # noqa: F401