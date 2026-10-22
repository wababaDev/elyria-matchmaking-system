import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateMediaStorage(FileSystemStorage):
    """
    Files that must never be public (member photos).

    They live in PRIVATE_MEDIA_ROOT, outside MEDIA_ROOT. Caddy only serves /media/,
    so these files have no public address; views stream them after checking permissions.
    """

    @property
    def base_location(self):
        return settings.PRIVATE_MEDIA_ROOT  # read each time, so tests can point it at a temp folder

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    def url(self, name):
        raise NotImplementedError("Private files have no public URL. Use the permission-checked view.")


_private_storage = PrivateMediaStorage()


def private_storage():
    """Used as storage=private_storage on the model, which keeps settings out of the migration."""
    return _private_storage