from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.shortcuts import resolve_url

from domain.base.models.permissions import (
    GROUP_PERMISSIONS,
    PERMISSIONS,
    STAFF_GROUPS,
    ElyriaPermissions,
    Groups,
)


@transaction.atomic
def create_groups_and_permissions():
    content_type = ContentType.objects.get_for_model(ElyriaPermissions)

    perms = {}
    for codename, name in PERMISSIONS:
        perm, _ = Permission.objects.update_or_create(
            codename=codename,
            content_type=content_type,
            defaults={"name": name},
        )
        perms[codename] = perm

    for group_name, codenames in GROUP_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        group.permissions.set([perms[c] for c in codenames])


def in_groups(user, *names) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser and Groups.ADMIN in names:
        return True
    return user.groups.filter(name__in=names).exists()


def home_url_for(user) -> str:
    """Where a user lands after signing in."""
    if in_groups(user, *STAFF_GROUPS):
        return resolve_url(settings.STAFF_HOME_URL)
    if in_groups(user, Groups.MEMBER):
        return resolve_url(settings.MEMBER_HOME_URL)
    return resolve_url("/")