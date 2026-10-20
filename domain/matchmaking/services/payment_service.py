"""
Read-only view of every payment the system records, for Finance and Admin.

Payments live in two places and stay there:
- consultation fees, on ConsultationRequest (fee_* fields)
- membership payments (new + renewals), in MembershipPayment
This module reads both and returns one combined, filtered list.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from domain.matchmaking.models import ConsultationRequest, Membership, MembershipPayment
from domain.matchmaking.models.membership import EXPIRING_SOON_DAYS

KIND_FEE = "fee"
KIND_NEW = "new"
KIND_RENEWAL = "renewal"

KIND_CHOICES = [
    ("", "All payments"),
    (KIND_FEE, "Consultation fees"),
    (KIND_NEW, "New memberships"),
    (KIND_RENEWAL, "Renewals"),
]
KIND_LABELS = dict(KIND_CHOICES)


@dataclass
class PaymentRow:
    paid_on: date
    kind: str
    person: str
    payment_reference: str
    amount: Decimal
    currency: str
    method: str
    transaction_ref: str
    recorded_by: object  # User or None
    link: str

    @property
    def kind_label(self):
        return {KIND_FEE: "Consultation fee", KIND_NEW: "New membership", KIND_RENEWAL: "Renewal"}[self.kind]


def _fee_rows(*, q, staff, date_from, date_to):
    qs = ConsultationRequest.objects.filter(fee_paid_at__isnull=False).select_related("fee_marked_paid_by")
    if q:
        qs = qs.filter(
            Q(payment_reference__icontains=q) | Q(full_name__icontains=q)
            | Q(preferred_name__icontains=q) | Q(fee_reference__icontains=q)
        )
    if staff:
        qs = qs.filter(fee_marked_paid_by=staff)
    if date_from:
        qs = qs.filter(fee_paid_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(fee_paid_at__date__lte=date_to)

    for cr in qs:
        yield PaymentRow(
            paid_on=timezone.localtime(cr.fee_paid_at).date(),
            kind=KIND_FEE,
            person=cr.full_name,
            payment_reference=cr.payment_reference or "",
            amount=cr.fee_amount or Decimal("0"),
            currency=cr.fee_currency,
            method=cr.get_fee_payment_method_display(),
            transaction_ref=cr.fee_reference,
            recorded_by=cr.fee_marked_paid_by,
            link=reverse("matchmaking:consultation-request-detail", args=[cr.pk]),
        )


def _membership_rows(*, kind, q, staff, date_from, date_to):
    qs = MembershipPayment.objects.select_related(
        "recorded_by", "membership__client", "membership__client__consultation_request"
    )
    if kind in (KIND_NEW, KIND_RENEWAL):
        qs = qs.filter(kind=kind)
    if q:
        qs = qs.filter(
            Q(membership__client__consultation_request__payment_reference__icontains=q)
            | Q(membership__client__full_name__icontains=q)
            | Q(membership__client__preferred_name__icontains=q)
            | Q(reference__icontains=q)
        )
    if staff:
        qs = qs.filter(recorded_by=staff)
    if date_from:
        qs = qs.filter(paid_on__gte=date_from)
    if date_to:
        qs = qs.filter(paid_on__lte=date_to)

    for p in qs:
        client = p.membership.client
        request = client.consultation_request
        yield PaymentRow(
            paid_on=p.paid_on,
            kind=p.kind,
            person=client.full_name,
            payment_reference=(request.payment_reference if request else "") or "",
            amount=p.amount,
            currency=p.currency,
            method=p.get_method_display(),
            transaction_ref=p.reference,
            recorded_by=p.recorded_by,
            link=reverse("matchmaking:member-detail", args=[client.pk]),
        )


def payment_rows(*, kind="", q="", staff=None, date_from=None, date_to=None):
    """Every payment matching the filters, newest first."""
    q = (q or "").strip()
    rows = []
    if kind in ("", KIND_FEE):
        rows += _fee_rows(q=q, staff=staff, date_from=date_from, date_to=date_to)
    if kind in ("", KIND_NEW, KIND_RENEWAL):
        rows += _membership_rows(kind=kind, q=q, staff=staff, date_from=date_from, date_to=date_to)
    return sorted(rows, key=lambda r: r.paid_on, reverse=True)


def totals_by_currency(rows):
    """[("ZMW", Decimal(...)), ...]: never adds different currencies together."""
    totals = defaultdict(Decimal)
    for row in rows:
        totals[row.currency] += row.amount
    return sorted(totals.items())


def payment_summary(rows):
    today = timezone.localdate()
    month_start = today.replace(day=1)
    return {
        "all": totals_by_currency(rows),
        "this_month": totals_by_currency(r for r in rows if r.paid_on >= month_start),
        "fees": totals_by_currency(r for r in rows if r.kind == KIND_FEE),
        "memberships": totals_by_currency(r for r in rows if r.kind in (KIND_NEW, KIND_RENEWAL)),
        "count": len(rows),
    }


def staff_summary(rows, *, date_from=None, date_to=None):
    """Per staff member: what they recorded, plus memberships they cancelled."""
    people = {}

    def entry(user):
        key = user.pk if user else None
        if key not in people:
            people[key] = {
                "user": user,
                "fees": 0, "new": 0, "renewals": 0, "cancelled": 0,
                "totals": defaultdict(Decimal),
            }
        return people[key]

    for row in rows:
        e = entry(row.recorded_by)
        e[{KIND_FEE: "fees", KIND_NEW: "new", KIND_RENEWAL: "renewals"}[row.kind]] += 1
        e["totals"][row.currency] += row.amount

    cancelled = Membership.objects.filter(status=Membership.Status.CANCELLED).select_related("cancelled_by")
    if date_from:
        cancelled = cancelled.filter(cancelled_at__date__gte=date_from)
    if date_to:
        cancelled = cancelled.filter(cancelled_at__date__lte=date_to)
    for membership in cancelled:
        entry(membership.cancelled_by)["cancelled"] += 1

    result = []
    for e in people.values():
        e["totals"] = sorted(e["totals"].items())
        result.append(e)
    return sorted(result, key=lambda e: (e["user"] is None, e["user"].full_name if e["user"] else ""))


def member_counts():
    today = timezone.localdate()
    soon = today + timedelta(days=EXPIRING_SOON_DAYS)
    active = Membership.objects.filter(status=Membership.Status.ACTIVE)
    return {
        "active": active.filter(end_date__gte=today).count(),
        "expiring": active.filter(end_date__gte=today, end_date__lte=soon).count(),
        "expired": active.filter(end_date__lt=today).count(),
        "cancelled": Membership.objects.filter(status=Membership.Status.CANCELLED).count(),
        "total": Membership.objects.count(),
    }