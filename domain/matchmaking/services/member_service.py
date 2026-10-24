from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from domain.matchmaking.models import Client, Membership, MembershipPayment
from domain.matchmaking.models.membership import EXPIRING_SOON_DAYS
from domain.matchmaking.services.consultation_request_service import InvalidTransitionError
from domain.matchmaking.utils import add_months
from django.contrib.auth import get_user_model

MEMBER_FILTERS = [
    ("active", "Active"),
    ("expiring", "Expiring soon"),
    ("expired", "Expired"),
    ("cancelled", "Cancelled"),
    ("all", "All"),
]


def members_visible_to(user):
    """Admin sees everyone; matchmakers only their own members."""
    qs = Client.objects.all()
    if user.has_perm("base.view_all_members"):
        return qs
    return qs.filter(matchmaker=user)


def filter_members(qs, *, status="active", query="", matchmaker=""):
    qs = qs.select_related("user", "matchmaker", "membership", "membership__tier")
    today = timezone.localdate()
    soon = today + timedelta(days=EXPIRING_SOON_DAYS)
    active = Q(membership__status=Membership.Status.ACTIVE)

    if status == "active":
        qs = qs.filter(active, membership__end_date__gte=today)
    elif status == "expiring":
        qs = qs.filter(active, membership__end_date__gte=today, membership__end_date__lte=soon)
    elif status == "expired":
        qs = qs.filter(active, membership__end_date__lt=today)
    elif status == "cancelled":
        qs = qs.filter(membership__status=Membership.Status.CANCELLED)

    if matchmaker == "none":
        qs = qs.filter(matchmaker__isnull=True)
    elif matchmaker.isdigit():
        qs = qs.filter(matchmaker_id=int(matchmaker))

    query = query.strip()
    if query:
        qs = qs.filter(
            Q(full_name__icontains=query) | Q(preferred_name__icontains=query) | Q(user__email__icontains=query)
        )
    return qs.order_by("full_name")


def _lock(membership):
    return Membership.objects.select_for_update().select_related("client__user").get(pk=membership.pk)


@transaction.atomic
def renew_membership(membership, *, tier, method, reference="", by):
    """Price and new end date come from the tier; staff only record how it was paid."""
    membership = _lock(membership)
    if membership.status == Membership.Status.CANCELLED:
        raise InvalidTransitionError("Cancelled memberships can't be renewed.")
    if tier.price is None:
        raise InvalidTransitionError(f"{tier.name} has no price yet. Set it in Settings → Membership tiers first.")

    # Renewing early extends from the current end date; renewing late starts from today
    base = max(membership.end_date, timezone.localdate())
    membership.tier = tier
    membership.end_date = add_months(base, tier.duration_months)
    membership.save(update_fields=["tier", "end_date", "updated_at"])

    MembershipPayment.objects.create(
        membership=membership,
        kind=MembershipPayment.Kind.RENEWAL,
        amount=tier.price,
        currency=tier.currency,
        method=method,
        reference=reference,
        recorded_by=by,
    )
    return membership


@transaction.atomic
def cancel_membership(membership, *, reason, by):
    membership = _lock(membership)
    if membership.status == Membership.Status.CANCELLED:
        raise InvalidTransitionError("This membership is already cancelled.")

    membership.status = Membership.Status.CANCELLED
    membership.cancelled_at = timezone.now()
    membership.cancelled_by = by
    membership.cancellation_reason = reason.strip()
    membership.save(update_fields=["status", "cancelled_at", "cancelled_by", "cancellation_reason", "updated_at"])

    # A cancelled member can no longer sign in to the portal
    user = membership.client.user
    user.is_active = False
    user.save(update_fields=["is_active"])
    return membership


@transaction.atomic
def reassign_matchmaker(client, *, to, by):
    client.matchmaker = to
    client.save(update_fields=["matchmaker", "updated_at"])
    return client


def change_sign_in_email(client, *, email, by):
    """
    Staff change a member's sign-in email (members can't do it themselves).
    Old and new addresses both get a notice. If they never set a password, the old
    sign-in link stops working (Django ties it to the email), so a fresh one is sent.
    """
    from notification.services.member_emails import send_sign_in_email_changed, send_sign_in_link

    user = client.user
    old_email = user.email
    email = email.strip().lower()
    if email == old_email.lower():
        return
    if get_user_model().objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
        raise InvalidTransitionError("That email address is already used by another account.")

    with transaction.atomic():
        user.email = email
        user.save(update_fields=["email"])
        transaction.on_commit(lambda: send_sign_in_email_changed(client, old_email))
        if not user.has_usable_password():
            transaction.on_commit(lambda: send_sign_in_link(client))