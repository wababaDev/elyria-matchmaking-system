from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from domain.matchmaking.models import Client, Membership, MembershipHold, MembershipPayment
from domain.matchmaking.models.membership import EXPIRING_SOON_DAYS, weeks_text
from domain.matchmaking.services.consultation_request_service import InvalidTransitionError
from domain.matchmaking.utils import add_months

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
    return Membership.objects.select_for_update().select_related("client__user", "tier").get(pk=membership.pk)


# ---------------------------------------------------------------- introductions

def introductions_used(membership):
    """
    Different people this member has been introduced to since the membership started.
    Several dates with the same person are one introduction (one pairing, one person).
    """
    from domain.matchmaking.models import Pairing

    client_id = membership.client_id
    pairs = Pairing.objects.filter(
        Q(client_a_id=client_id) | Q(client_b_id=client_id),
        introduced_on__isnull=False,
        introduced_on__gte=membership.start_date,
    ).values_list("client_a_id", "client_b_id")
    return len({b if a == client_id else a for a, b in pairs})


def introduction_status(membership):
    """
    {"allowed": 3 or None (unlimited), "used": 2, "left": 1 or None, "state": "ok" | "last" | "none_left"}
    "last" = the next introduction is their last one; "none_left" = all used.
    """
    if membership is None:
        return None
    allowed = membership.introductions_allowance
    used = introductions_used(membership)
    if allowed is None:
        return {"allowed": None, "used": used, "left": None, "state": "ok"}
    left = max(allowed - used, 0)
    state = "none_left" if left == 0 else "last" if left == 1 else "ok"
    return {"allowed": allowed, "used": used, "left": left, "state": state}


# ---------------------------------------------------------------- renew / upgrade

@transaction.atomic
def renew_membership(membership, *, tier, method, reference="", by):
    """
    Renew on the same tier, or upgrade to another. Price and the new end date come from the tier.
    The new tier's introductions are added to whatever the member hasn't used yet.
    """
    membership = _lock(membership)
    if membership.status == Membership.Status.CANCELLED:
        raise InvalidTransitionError("Cancelled memberships can't be renewed.")
    if tier.price is None:
        raise InvalidTransitionError(f"{tier.name} has no price yet. Set it in Settings → Membership tiers first.")

    is_upgrade = tier.pk != membership.tier_id
    current_allowance = membership.introductions_allowance
    if tier.max_introductions is None:
        new_allowance = None                                   # unlimited tier
    elif current_allowance is None:
        new_allowance = introductions_used(membership) + tier.max_introductions
    else:
        new_allowance = current_allowance + tier.max_introductions

    # Renewing early extends from the current end date; renewing late starts from today
    base = max(membership.end_date, timezone.localdate())
    membership.tier = tier
    membership.end_date = add_months(base, tier.duration_months)
    membership.introductions_allowed = new_allowance
    membership.hold_term_start = timezone.localdate()
    membership.save(update_fields=["tier", "end_date", "introductions_allowed", "updated_at"])

    MembershipPayment.objects.create(
        membership=membership,
        kind=MembershipPayment.Kind.UPGRADE if is_upgrade else MembershipPayment.Kind.RENEWAL,
        amount=tier.price,
        currency=tier.currency,
        method=method,
        reference=reference,
        recorded_by=by,
    )
    return membership


# ---------------------------------------------------------------- hold time

@transaction.atomic
def start_hold(membership, *, reason, started_on, ended_on, note="", by):
    """
    Book Hold Time from a first day to a last day (past or future).
    The end date moves forward by those days straight away.
    """
    membership = _lock(membership)
    tier = membership.tier
    today = timezone.localdate()

    if membership.status == Membership.Status.CANCELLED:
        raise InvalidTransitionError("A cancelled membership can't be put on hold.")
    if not membership.hold_allowance_days:
        raise InvalidTransitionError(f"{tier.name} membership doesn't include Hold Time.")
    if ended_on < started_on:
        raise InvalidTransitionError("The last day can't be before the first day.")
    if started_on < membership.start_date:
        raise InvalidTransitionError("The hold can't start before the membership started.")
    if started_on > membership.end_date:
        raise InvalidTransitionError("The hold can't start after the membership has ended.")
    unfinished = Q(ended_on__isnull=True) | Q(ended_on__gte=today)
    if membership.holds.filter(unfinished).exists():
        raise InvalidTransitionError("There's already a hold that hasn't finished. End or cancel it first.")
    overlap = membership.holds.filter(started_on__lte=ended_on).filter(
        Q(ended_on__isnull=True) | Q(ended_on__gte=started_on)
    )
    if overlap.exists():
        raise InvalidTransitionError("These dates overlap an earlier hold.")

    days = (ended_on - started_on).days + 1
    left = membership.hold_days_left
    if days > left:
        raise InvalidTransitionError(
            f"That's {weeks_text(days)}, but only {weeks_text(left)} of Hold Time is left "
            f"({tier.name}: {weeks_text(membership.hold_allowance_days)} per term)."
        )

    hold = MembershipHold.objects.create(
        membership=membership, reason=reason, note=note.strip(),
        started_on=started_on, ended_on=ended_on, days_added=days, started_by=by,
    )
    membership.end_date += timedelta(days=days)
    membership.renewal_reminder_days = None  # the end date moved, so reminders start again
    membership.save(update_fields=["end_date", "renewal_reminder_days", "updated_at"])
    return hold


@transaction.atomic
def end_hold(membership, *, back_on=None, by):
    """
    End the hold early, or cancel one that hasn't started. The unused days come off the end date again.
    Returns (hold, days_given_back). A cancelled hold is deleted (hold.pk is None afterwards).
    """
    membership = _lock(membership)
    today = timezone.localdate()
    hold = (
        membership.holds.select_for_update()
        .filter(Q(ended_on__isnull=True) | Q(ended_on__gte=today))
        .order_by("started_on")
        .first()
    )
    if hold is None:
        raise InvalidTransitionError("This membership has no hold to end.")

    if hold.started_on > today:
        # Not started yet: cancel it completely
        days_back = hold.days_added
        hold.delete()
    else:
        back_on = back_on or today
        last_day = back_on - timedelta(days=1)
        if last_day < hold.started_on:
            raise InvalidTransitionError(
                f"The back date has to be after the first day of the hold ({hold.started_on:%d %b %Y})."
            )
        if hold.ended_on and last_day >= hold.ended_on:
            raise InvalidTransitionError(
                f"The hold already ends on {hold.ended_on:%d %b %Y}. Pick an earlier date to end it early."
            )
        new_days = (last_day - hold.started_on).days + 1
        # Old open-ended holds have days_added = 0, so this is negative: the days get added instead
        days_back = hold.days_added - new_days
        hold.ended_on = last_day
        hold.days_added = new_days
        hold.ended_by = by
        hold.save(update_fields=["ended_on", "days_added", "ended_by", "updated_at"])

    membership.end_date -= timedelta(days=days_back)
    membership.renewal_reminder_days = None
    membership.save(update_fields=["end_date", "renewal_reminder_days", "updated_at"])
    return hold, days_back

# ---------------------------------------------------------------- cancel / reassign / email

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