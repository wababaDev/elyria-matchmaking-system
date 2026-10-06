from django.conf import settings
from django.db import models

from domain.base.models.permissions import STAFF_GROUPS, Groups
from domain.base.models.timestamped import TimeStampedModel


class Profile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    phone_number = models.CharField(max_length=20, blank=True)
    job_title = models.CharField(
        max_length=100,
        blank=True,
        help_text="Staff only, e.g. Senior Matchmaker.",
    )

    def __str__(self):
        return f"Profile of {self.user}"

    def _in(self, *names):
        from domain.base.services.groups import in_groups  # avoid import loop
        return in_groups(self.user, *names)

    @property
    def is_member(self):
        return self._in(Groups.MEMBER)

    @property
    def is_matchmaker(self):
        return self._in(Groups.MATCHMAKER)

    @property
    def is_admin(self):
        return self._in(Groups.ADMIN)

    @property
    def is_staff_member(self):
        return self._in(*STAFF_GROUPS)