from domain.elite.models.elite_case import EliteCase
from domain.matchmaking.models import Enquiry
from domain.matchmaking.services.pairing_service import pairing_queue
from domain.matchmaking.services.queue_service import queue_for


def queue_counts(request):
    """
    The numbers in the sidebar:
    - pairings_waiting: pairings waiting on you (red, on Pairings)
    - staff_queue_count: consultation requests in your queue (gold, on My Queue)
    - open_enquiries_count: website enquiries not yet answered (gold, on Enquiries)
    - elite_review_count: Elite cases waiting for Admin's decision (gold, on Elite cases; Admin only)
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not request.path.startswith("/management/"):
        return {}

    counts = {"open_enquiries_count": Enquiry.objects.filter(status=Enquiry.Status.OPEN).count()}
    if user.has_perm("base.manage_matching"):
        counts["pairings_waiting"] = sum(qs.count() for qs in pairing_queue(user).values())
    if user.has_perm("base.manage_consultation_request"):
        counts["staff_queue_count"] = sum(len(s["items"]) for s in queue_for(user))
    if user.has_perm("base.manage_staff"):
        counts["elite_review_count"] = EliteCase.objects.filter(status=EliteCase.Status.UNDER_REVIEW).count()
        counts["elite_pending_count"] = EliteCase.objects.filter(status=EliteCase.Status.AWAITING_DOCUMENTS).count()
        counts["elite_link"] = True
    elif user.has_perm("base.manage_matching"):
        mine = EliteCase.objects.filter(handler=user)
        if mine.exists():
            # A Case Handler sees the link only once she has a case; the gold number = cases waiting on her
            counts["elite_link"] = True
            counts["elite_review_count"] = mine.filter(status__in=EliteCase.HANDLER_STATUSES).count()
    return counts