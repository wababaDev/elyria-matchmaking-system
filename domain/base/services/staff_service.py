from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction

from domain.base.models import STAFF_GROUPS, Groups, Profile
from notification.services.staff_emails import send_staff_invite

User = get_user_model()


class StaffError(Exception):
    pass


def staff_users():
    return (
        User.objects.filter(groups__name__in=STAFF_GROUPS)
        .distinct()
        .select_related("profile")
        .prefetch_related("groups")
        .order_by("-is_active", "first_name", "last_name")
    )


def role_of(user):
    names = {g.name for g in user.groups.all()}
    return Groups.ADMIN if Groups.ADMIN in names else Groups.MATCHMAKER


def _set_role(user, role):
    user.groups.remove(*Group.objects.filter(name__in=STAFF_GROUPS))
    user.groups.add(Group.objects.get(name=role))


@transaction.atomic
def create_staff_member(*, email, first_name, last_name, job_title, role, by):
    if User.objects.filter(email__iexact=email).exists():
        raise StaffError("Someone with this email already has an account.")
    user = User.objects.create_user(
        email=email, password=None, first_name=first_name, last_name=last_name,
    )
    _set_role(user, role)
    profile, _ = Profile.objects.get_or_create(user=user)
    profile.job_title = job_title
    profile.save(update_fields=["job_title", "updated_at"])

    transaction.on_commit(lambda: send_staff_invite(user))
    return user


@transaction.atomic
def update_staff_member(user, *, first_name, last_name, job_title, role, is_active, by):
    if user == by and (role != Groups.ADMIN or not is_active):
        raise StaffError("You can't remove your own admin access.")

    user.first_name, user.last_name, user.is_active = first_name, last_name, is_active
    user.save(update_fields=["first_name", "last_name", "is_active"])
    _set_role(user, role)

    profile, _ = Profile.objects.get_or_create(user=user)
    profile.job_title = job_title
    profile.save(update_fields=["job_title", "updated_at"])
    return user