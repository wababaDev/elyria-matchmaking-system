from domain.matchmaking.services.pairing_service import pairing_queue
from domain.matchmaking.services.queue_service import queue_for


def queue_counts(request):
    """
    The two numbers next to "My Queue" in the sidebar:
    - pairings_waiting: pairings waiting on you (red: they hold up another matchmaker or member)
    - staff_queue_count: consultation requests in your queue (gold)
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not request.path.startswith("/management/"):
        return {}

    counts = {}
    if user.has_perm("base.manage_matching"):
        q = pairing_queue(user)
        counts["pairings_waiting"] = q["to_approve"].count() + q["to_present"].count() + q["to_introduce"].count()
    if user.has_perm("base.manage_consultation_request"):
        counts["staff_queue_count"] = sum(len(s["items"]) for s in queue_for(user))
    return counts