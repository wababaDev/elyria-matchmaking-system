from django.conf import settings
from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import ImproperlyConfigured, PermissionDenied

from domain.base.models.permissions import STAFF_GROUPS, Groups
from domain.base.services.groups import in_groups


class GroupRequiredMixin(AccessMixin):
    """
    Not signed in           -> redirect to sign-in
    Wrong group             -> 403
    Missing permission_required (optional) -> 403
    """
    allowed_groups: list = []
    permission_required: str | None = None   # e.g. "base.manage_matching"

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return self.handle_no_permission()
        if not self.allowed_groups:
            raise ImproperlyConfigured(f"{type(self).__name__} must set allowed_groups.")
        if not in_groups(user, *self.allowed_groups):
            raise PermissionDenied
        if self.permission_required and not user.has_perm(self.permission_required):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class MemberRequiredMixin(GroupRequiredMixin):
    allowed_groups = [Groups.MEMBER]
    permission_required = "base.access_member_portal"


class StaffRequiredMixin(GroupRequiredMixin):
    allowed_groups = STAFF_GROUPS

    def get_login_url(self):
        return settings.STAFF_LOGIN_URL


class AdminRequiredMixin(StaffRequiredMixin):
    allowed_groups = [Groups.ADMIN]
    permission_required = "base.manage_staff"