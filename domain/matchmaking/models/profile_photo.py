import uuid
from pathlib import Path

from django.db import models

from domain.base.models import TimeStampedModel
from domain.base.storage import private_storage
from domain.matchmaking.models.client_profile import ClientProfile


def photo_path(instance, filename):
    """
    profile_photos/<payment reference>/<kind>-<short random>.<ext>
    Staff can find the member by searching the reference; the name itself is never in the path.
    """
    client = instance.profile.client
    folder = client.consultation_request.payment_reference or f"client-{client.pk}"
    kind = instance.kind.replace("_", "-")
    ext = Path(filename).suffix.lower() or ".jpg"
    return f"profile_photos/{folder}/{kind}-{uuid.uuid4().hex[:6]}{ext}"


class ProfilePhoto(TimeStampedModel):
    """
    A member's photo. Stored in PRIVATE_MEDIA_ROOT, which the web server never serves:
    the only way to see one is through a view that checks who is asking.
    """

    class Kind(models.TextChoices):
        FULL_LENGTH = "full_length", "Full-length"
        CLOSE_UP = "close_up", "Close-up"
        OTHER = "other", "Another"

    profile = models.ForeignKey(ClientProfile, on_delete=models.CASCADE, related_name="photos")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    image = models.ImageField(upload_to=photo_path, storage=private_storage)

    class Meta:
        ordering = ["kind"]
        constraints = [
            models.UniqueConstraint(fields=["profile", "kind"], name="one_photo_per_kind"),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} photo of {self.profile.client}"