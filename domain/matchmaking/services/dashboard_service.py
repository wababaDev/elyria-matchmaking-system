from django.utils import timezone

from domain.matchmaking.models import  Consultation, ConsultationRequest
from domain.matchmaking.models import Consultation, ConsultationRequest, Membership

def dashboard_summary():
    month_start = timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    requests = ConsultationRequest.objects
    return {
        "requests_this_month": requests.filter(created_at__gte=month_start).count(),
        "awaiting_payment_count": requests.filter(
            status=ConsultationRequest.Status.AWAITING_PAYMENT
        ).count(),
        "recent_requests": requests.select_related("assigned_to")[:5],
        "upcoming_consultations": (
            Consultation.objects
            .filter(scheduled_for__gte=timezone.now(), request__status=ConsultationRequest.Status.FEE_PAID)
            .select_related("request", "request__assigned_to")
            .order_by("scheduled_for")[:5]
        ),
        "active_members": Membership.objects.filter(
           status=Membership.Status.ACTIVE, end_date__gte=timezone.localdate()
        ).count(),
    }