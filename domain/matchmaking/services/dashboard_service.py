"""
The Overview page.

Admin sees the whole business, from request to introduction.
A matchmaker sees only their own work: requests assigned to them and members they look after.
No business-wide traffic or totals for matchmakers.

Every number is a plain count over real records. Months and weeks follow the local calendar
(Lusaka): a week starts on Monday.
"""
from datetime import date, datetime, time, timedelta

from django.db.models import Count, Q
from django.utils import timezone

from domain.matchmaking.models import Consultation, ConsultationRequest, Membership, MembershipHold, MembershipPayment
from domain.matchmaking.models.pairing import Pairing

TREND_MONTHS = 6
FUNNEL_DAYS = 90
RENEWAL_DAYS = 30
LIST_SIZE = 5


def sees_everything(user):
    """Admin is the only role that sees every request."""
    return user is None or user.has_perm("base.view_all_consultation_requests")


def _start_of(day):
    """Midnight at the start of a local date, as an aware datetime (for created_at / scheduled_for filters)."""
    return timezone.make_aware(datetime.combine(day, time.min))


def _months_back(today, count):
    """First day of each of the last `count` months, oldest first, ending with this month."""
    year, month = today.year, today.month
    firsts = []
    for _ in range(count):
        firsts.append(date(year, month, 1))
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    return list(reversed(firsts))


def _next_month(first):
    return date(first.year + 1, 1, 1) if first.month == 12 else date(first.year, first.month + 1, 1)


def _trend(today):
    """Consultation requests and new members per month, for the last TREND_MONTHS months."""
    labels, requests, members = [], [], []
    for first in _months_back(today, TREND_MONTHS):
        end = _next_month(first)
        labels.append(first.strftime("%b"))
        requests.append(ConsultationRequest.objects.filter(
            created_at__gte=_start_of(first), created_at__lt=_start_of(end)).count())
        members.append(MembershipPayment.objects.filter(
            kind=MembershipPayment.Kind.NEW, paid_on__gte=first, paid_on__lt=end).count())
    return {"labels": labels, "requests": requests, "members": members}


def _funnel(today):
    """Of the requests made in the last FUNNEL_DAYS days: how many reached each stage."""
    recent = ConsultationRequest.objects.filter(created_at__gte=_start_of(today - timedelta(days=FUNNEL_DAYS)))
    counts = recent.aggregate(
        requested=Count("pk"),
        fee_paid=Count("pk", filter=Q(fee_paid_at__isnull=False)),
        consulted=Count("pk", filter=Q(consultation__held_at__isnull=False)),
        members=Count("pk", filter=Q(status=ConsultationRequest.Status.BECAME_MEMBER)),
    )
    return {
        "labels": ["Requested", "Fee paid", "Consulted", "Became members"],
        "values": [counts["requested"], counts["fee_paid"], counts["consulted"], counts["members"]],
    }


def dashboard_summary(user=None):
    """user=None or Admin: everything. A matchmaker: only their own requests, members and pairings."""
    everything = sees_everything(user)
    today = timezone.localdate()
    month_start = today.replace(day=1)
    week_start = today - timedelta(days=today.weekday())

    requests = ConsultationRequest.objects.all()
    current = Membership.objects.filter(status=Membership.Status.ACTIVE, end_date__gte=today)
    pairings = Pairing.objects.all()
    consultations = Consultation.objects.all()
    if not everything:
        requests = requests.filter(assigned_to=user)
        current = current.filter(client__matchmaker=user)
        pairings = pairings.filter(Q(client_a__matchmaker=user) | Q(client_b__matchmaker=user))
        consultations = consultations.filter(request__assigned_to=user)

    open_pairings = pairings.exclude(status=Pairing.Status.CLOSED)
    by_tier = list(current.values("tier__name").annotate(total=Count("pk")).order_by("tier__name"))
    on_hold_ids = MembershipHold.objects.active_on(today).values("membership_id")

    summary = {
        "sees_everything": everything,

        # Row 1: the four headline numbers
        "awaiting_payment_count": requests.filter(status=ConsultationRequest.Status.AWAITING_PAYMENT).count(),
        "consultations_this_week": consultations.filter(
            scheduled_for__gte=_start_of(week_start), scheduled_for__lt=_start_of(week_start + timedelta(days=7)),
        ).count(),
        "active_members": current.count(),
        "on_hold_members": current.filter(pk__in=on_hold_ids).count(),
        "introductions_this_month": pairings.filter(introduced_on__gte=month_start, introduced_on__lte=today).count(),

        # Row 3: what needs attention
        "members_by_tier": {"labels": [r["tier__name"] for r in by_tier], "values": [r["total"] for r in by_tier]},
        "renewals_due": (
            current.filter(end_date__lte=today + timedelta(days=RENEWAL_DAYS))
            .select_related("client", "tier").order_by("end_date")[:LIST_SIZE]
        ),
        "renewal_days": RENEWAL_DAYS,
        "matching": {
            "open": open_pairings.count(),
            "waiting_on_members": open_pairings.filter(
                Q(a_presented_at__isnull=False, a_decision=Pairing.DecisionA.PENDING)
                | Q(b_decision=Pairing.DecisionB.PENDING)
            ).count(),
            "mutual_no_date": open_pairings.filter(status=Pairing.Status.MUTUAL, introduced_on__isnull=True).count(),
        },
        "upcoming_consultations": (
            consultations
            .filter(scheduled_for__gte=timezone.now(), request__status=ConsultationRequest.Status.FEE_PAID)
            .select_related("request", "request__assigned_to")
            .order_by("scheduled_for")[:LIST_SIZE]
        ),
    }

    if everything:
        # Business-wide numbers: Admin only
        summary.update({
            "requests_this_month": requests.filter(created_at__gte=_start_of(month_start)).count(),
            "trend": _trend(today),
            "funnel": _funnel(today),
            "funnel_days": FUNNEL_DAYS,
            "recent_requests": requests.select_related("assigned_to", "former_elite_case")[:LIST_SIZE],
            "elite": _elite_summary(),
        })
    else:
        # The matchmaker's own requests still in progress
        summary["my_open_requests"] = requests.filter(status__in=ConsultationRequest.OPEN_STATUSES).count()
    return summary


def _elite_summary():
    from domain.elite.models import EliteCase

    S = EliteCase.Status
    cases = EliteCase.objects
    return {
        "under_review": cases.filter(status=S.UNDER_REVIEW).count(),
        "awaiting_documents": cases.filter(status=S.AWAITING_DOCUMENTS).count(),
        "waiting_for_reply": cases.filter(status=S.OUTREACH_SENT).count(),
        "in_progress": cases.filter(status__in=[S.APPROVED, S.PAID, S.AGREED, S.INTRODUCTION, S.INTRODUCED, S.BRONZE_OFFERED]).count(),
    }