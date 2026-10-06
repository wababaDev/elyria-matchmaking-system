from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from domain.base.models import Profile
from domain.base.services.groups import create_groups_and_permissions


class Command(BaseCommand):
    help = "Create/refresh groups and permissions, and add missing profiles."

    def handle(self, *args, **options):
        create_groups_and_permissions()

        missing = get_user_model().objects.filter(profile__isnull=True)
        created = Profile.objects.bulk_create([Profile(user=u) for u in missing])

        self.stdout.write(self.style.SUCCESS(
            f"Groups and permissions ready. {len(created)} missing profile(s) created."
        ))