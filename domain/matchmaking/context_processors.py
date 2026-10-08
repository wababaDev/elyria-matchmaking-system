from domain.base.models import STAFF_GROUPS
from domain.base.services.groups import in_groups
from domain.matchmaking.services.queue_service import queue_count


def staff_queue(request):
    user = getattr(request, "user", None)
    if user is None or not in_groups(user, *STAFF_GROUPS):
        return {}
    return {"staff_queue_count": queue_count(user)}