"""
Matching rules. Every step is a plain check: who is asking, and what state the pairing is in.
"""
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from domain.matchmaking.models import Client, ConsultationRequest, MatchAccessLog, Membership, Pairing
from domain.matchmaking.models.pairing import OPEN_PAIRING_LIMIT
from domain.matchmaking.services.consultation_request_service import InvalidTransitionError
from domain.matchmaking.services.member_service import members_visible_to

P = Pairing
Gender = ConsultationRequest.Gender
Seeking = ConsultationRequest.Seeking

# "seeking a man" means the other person's gender is male, and so on
SEEKING_GENDER = {Seeking.MAN: Gender.MALE, Seeking.WOMAN: Gender.FEMALE}
GENDER_SEEKING = {Gender.MALE: Seeking.MAN, Gender.FEMALE: Seeking.WOMAN}


# ---------------------------------------------------------------- who can see / do what

def can_manage(user, client):
    """The member's own matchmaker, or Admin (who sees everyone)."""
    return members_visible_to(user).filter(pk=client.pk).exists()


def pairings_visible_to(user):
    """Staff see pairings that involve at least one of their own members."""
    mine = members_visible_to(user).values("pk")
    return Pairing.objects.filter(Q(client_a__in=mine) | Q(client_b__in=mine)).select_related(
        "client_a__profile", "client_b__profile", "client_a__matchmaker", "client_b__matchmaker",
        "added_by", "approval_by", "b_presented_by",
    )


def pairings_for(client):
    """All pairings a member is part of, either side (staff view)."""
    return Pairing.objects.filter(Q(client_a=client) | Q(client_b=client)).select_related(
        "client_a__profile", "client_b__profile", "client_a__matchmaker", "client_b__matchmaker",
        "added_by", "approval_by",
    )


def open_pairing_counts(clients):
    """{client_id: number of open pairings} for the 'in 2 open pairings' badges."""
    ids = [c.pk for c in clients]
    counts = dict.fromkeys(ids, 0)
    open_ = Pairing.objects.exclude(status=P.Status.CLOSED)
    for row in open_.filter(client_a__in=ids).values("client_a").annotate(n=Count("pk")):
        counts[row["client_a"]] += row["n"]
    for row in open_.filter(client_b__in=ids).values("client_b").annotate(n=Count("pk")):
        counts[row["client_b"]] += row["n"]
    return counts


def log_access(user, action, client=None, detail=""):
    MatchAccessLog.objects.create(user=user, action=action, client=client, detail=detail[:300])


# ---------------------------------------------------------------- finding candidates

def candidates_for(client, *, age_min=None, age_max=None, city="", children="", religion=""):
    """
    People who could be paired with `client`: active members with a complete profile,
    whose gender and seeking fit both ways, who aren't already in an open pairing with them.
    Newest members first. The matchmaker chooses; the system never suggests.
    """
    profile = getattr(client, "profile", None)
    if not profile or not profile.is_complete:
        return Client.objects.none()

    today = timezone.localdate()
    qs = Client.objects.filter(
        user__is_active=True,
        membership__status=Membership.Status.ACTIVE,
        membership__end_date__gte=today,
        profile__completed_at__isnull=False,
        profile__gender=SEEKING_GENDER.get(profile.seeking, "-"),
        profile__seeking=GENDER_SEEKING.get(profile.gender, "-"),
    ).exclude(pk=client.pk)

    already = Pairing.objects.exclude(status=P.Status.CLOSED).filter(Q(client_a=client) | Q(client_b=client))
    paired_ids = set(already.values_list("client_a", flat=True)) | set(already.values_list("client_b", flat=True))
    qs = qs.exclude(pk__in=paired_ids)

    if age_min:
        qs = qs.filter(profile__age__gte=age_min)
    if age_max:
        qs = qs.filter(profile__age__lte=age_max)
    if city:
        qs = qs.filter(profile__location__icontains=city.strip())
    if children in ("yes", "no"):
        qs = qs.filter(profile__has_children=children)
    if religion:
        qs = qs.filter(profile__religion=religion)

    return qs.select_related("profile", "matchmaker", "membership").order_by("-created_at")


# ---------------------------------------------------------------- staff actions

@transaction.atomic
def propose(client_a, client_b, *, by, note_for_a, b_profession, b_location):
    if not can_manage(by, client_a):
        raise InvalidTransitionError("You can only propose pairings for your own members.")
    if not candidates_for(client_a).filter(pk=client_b.pk).exists():
        raise InvalidTransitionError("That member isn't available to pair with this member.")
    if not note_for_a.strip():
        raise InvalidTransitionError("Write the note your member will read.")

    same_matchmaker = client_b.matchmaker_id in (None, client_a.matchmaker_id)
    pairing = Pairing.objects.create(
        client_a=client_a, client_b=client_b, added_by=by,
        approval=P.Approval.NOT_NEEDED if same_matchmaker else P.Approval.PENDING,
        note_for_a=note_for_a.strip(), b_profession=b_profession.strip(), b_location=b_location.strip(),
    )
    log_access(by, MatchAccessLog.Action.PROPOSE, client_b, f"Proposed for {client_a.pk}")

    from notification.services import pairing_emails

    if same_matchmaker:
        transaction.on_commit(lambda: pairing_emails.notify_member_new_introduction(pairing, client_a))
    else:
        transaction.on_commit(lambda: pairing_emails.notify_approval_needed(pairing))

    # Someone else (e.g. Admin) proposed for this member: tell the member's own matchmaker
    if client_a.matchmaker_id and client_a.matchmaker_id != by.pk:
        transaction.on_commit(lambda: pairing_emails.notify_matchmaker_of_pairing(pairing))
    return pairing


def _lock(pairing):
    return Pairing.objects.select_for_update().get(pk=pairing.pk)


@transaction.atomic
def answer_approval(pairing, *, by, approve, reason=""):
    """B's matchmaker approves (A then sees the card) or declines (closed; A never sees it)."""
    pairing = _lock(pairing)
    if not can_manage(by, pairing.client_b):
        raise InvalidTransitionError("Only the other member's matchmaker can answer this.")
    if pairing.approval != P.Approval.PENDING:
        raise InvalidTransitionError("This pairing isn't waiting for approval.")

    pairing.approval = P.Approval.APPROVED if approve else P.Approval.DECLINED
    pairing.approval_by = by
    pairing.approval_at = timezone.now()
    if not approve:
        _close(pairing, reason or "Declined by the other member's matchmaker.")
    pairing.save()

    from notification.services import pairing_emails

    if approve:
        transaction.on_commit(lambda: pairing_emails.notify_member_new_introduction(pairing, pairing.client_a))
    transaction.on_commit(lambda: pairing_emails.notify_proposer_of_approval(pairing))
    return pairing


@transaction.atomic
def present_to_b(pairing, *, by, note_for_b, a_profession, a_location):
    pairing = _lock(pairing)
    if not can_manage(by, pairing.client_b):
        raise InvalidTransitionError("Only the other member's matchmaker can present this.")
    if pairing.a_decision != P.DecisionA.INTERESTED or pairing.b_decision != P.DecisionB.NOT_PRESENTED:
        raise InvalidTransitionError("This pairing isn't ready to present.")
    if not note_for_b.strip():
        raise InvalidTransitionError("Write the note your member will read.")

    pairing.note_for_b = note_for_b.strip()
    pairing.a_profession = a_profession.strip()
    pairing.a_location = a_location.strip()
    pairing.b_decision = P.DecisionB.PENDING
    pairing.b_presented_at = timezone.now()
    pairing.b_presented_by = by
    pairing.status = P.Status.PRESENTED_TO_B
    pairing.save()

    from notification.services import pairing_emails

    transaction.on_commit(lambda: pairing_emails.notify_member_new_introduction(pairing, pairing.client_b))
    return pairing


@transaction.atomic
def record_introduction(pairing, *, by, introduced_on):
    pairing = _lock(pairing)
    if not (can_manage(by, pairing.client_a) or can_manage(by, pairing.client_b)):
        raise InvalidTransitionError("You can't update this pairing.")
    if pairing.status != P.Status.MUTUAL:
        raise InvalidTransitionError("An introduction can only be recorded after mutual interest.")
    pairing.introduced_on = introduced_on
    pairing.save(update_fields=["introduced_on", "updated_at"])
    return pairing


@transaction.atomic
def close_pairing(pairing, *, by, reason):
    """Staff close an open pairing (e.g. a member changed their mind). Kept on record."""
    pairing = _lock(pairing)
    if not (can_manage(by, pairing.client_a) or can_manage(by, pairing.client_b)):
        raise InvalidTransitionError("You can't update this pairing.")
    if not pairing.is_open:
        raise InvalidTransitionError("This pairing is already closed.")
    if not reason.strip():
        raise InvalidTransitionError("Say why it's being closed.")
    _close(pairing, reason.strip())
    pairing.save()
    return pairing


def _close(pairing, reason):
    pairing.status = P.Status.CLOSED
    pairing.closed_at = timezone.now()
    pairing.closed_reason = reason


# ---------------------------------------------------------------- member side

def member_pairings(client):
    """
    What a member may see, and nothing else:
    - as A: once approved (or no approval needed), unless A said "not interested"
    - as B: once presented, unless B said "not interested"
    """
    as_a = Pairing.objects.filter(
        client_a=client, approval__in=[P.Approval.NOT_NEEDED, P.Approval.APPROVED]
    ).exclude(a_decision=P.DecisionA.NOT_INTERESTED)
    as_b = Pairing.objects.filter(client_b=client).exclude(
        b_decision__in=[P.DecisionB.NOT_PRESENTED, P.DecisionB.NOT_INTERESTED]
    )
    return (as_a | as_b).select_related("client_a__profile", "client_b__profile").order_by("-created_at")


@transaction.atomic
def member_decides(pairing, client, *, interested):
    pairing = _lock(pairing)
    if not member_pairings(client).filter(pk=pairing.pk).exists():
        raise InvalidTransitionError("This introduction isn't available.")
    if not pairing.is_open:
        raise InvalidTransitionError("This introduction will not go ahead.")

    now = timezone.now()
    from notification.services import pairing_emails

    if pairing.side(client) == "a":
        if pairing.a_decision != P.DecisionA.PENDING:
            raise InvalidTransitionError("You've already answered.")
        pairing.a_decision = P.DecisionA.INTERESTED if interested else P.DecisionA.NOT_INTERESTED
        pairing.a_decided_at = now
        if interested:
            transaction.on_commit(lambda: pairing_emails.notify_ready_to_present(pairing))
        else:
            _close(pairing, "Client A not interested.")
    else:
        if pairing.b_decision != P.DecisionB.PENDING:
            raise InvalidTransitionError("You've already answered.")
        pairing.b_decision = P.DecisionB.INTERESTED if interested else P.DecisionB.NOT_INTERESTED
        pairing.b_decided_at = now
        if interested:
            pairing.status = P.Status.MUTUAL
            transaction.on_commit(lambda: pairing_emails.notify_mutual_interest(pairing))
        else:
            _close(pairing, "Client B not interested.")
    pairing.save()
    return pairing


def member_card(pairing, client):
    """Only the Shortlist-Visible fields of the other person, as written for this member."""
    other = pairing.other(client)
    profile = getattr(other, "profile", None)
    as_a = pairing.side(client) == "a"
    return {
        "pairing": pairing,
        "first_name": (profile.preferred_name if profile else "") or other.preferred_name,
        "age_band": age_band(profile.age if profile else None),
        "profession": pairing.b_profession if as_a else pairing.a_profession,
        "location": pairing.b_location if as_a else pairing.a_location,
        "note": pairing.note_for_a if as_a else pairing.note_for_b,
        "photo_client_id": other.pk,
        "my_decision": pairing.a_decision if as_a else pairing.b_decision,
        "closed": not pairing.is_open,
        "mutual": pairing.status == P.Status.MUTUAL,
    }


def age_band(age):
    """34 -> 'Early 30s'. Never the exact age."""
    if not age:
        return ""
    decade, unit = divmod(int(age), 10)
    word = "Early" if unit <= 3 else "Mid" if unit <= 6 else "Late"
    return f"{word} {decade * 10}s"


def member_can_see_photo(client, other_client_id):
    """A member may see another member's (blurred) photo only through a pairing shown to them."""
    return any(p.other(client).pk == other_client_id for p in member_pairings(client))


def warning_for(client):
    n = open_pairing_counts([client])[client.pk]
    if n >= OPEN_PAIRING_LIMIT:
        return f"Already in {n} open pairings (limit {OPEN_PAIRING_LIMIT})."
    return ""


def pairing_queue(user):
    """For My Queue: pairings waiting on this matchmaker."""
    mine = members_visible_to(user).values("pk")
    base = Pairing.objects.exclude(status=P.Status.CLOSED).select_related(
        "client_a", "client_b", "client_a__profile", "client_b__profile"
    )
    return {
        "to_approve": base.filter(approval=P.Approval.PENDING, client_b__in=mine),
        "to_present": base.filter(a_decision=P.DecisionA.INTERESTED, b_decision=P.DecisionB.NOT_PRESENTED,
                                  client_b__in=mine),
        "to_introduce": base.filter(status=P.Status.MUTUAL, introduced_on__isnull=True).filter(
            Q(client_a__in=mine) | Q(client_b__in=mine)
        ),
    }


def pairing_queue_rows(user):
    """
    One row per thing waiting on this staff member, oldest first:
    {"p", "step": approve|present|introduce, "mine", "other", "other_profile", "since"}
    """
    mine_ids = set(members_visible_to(user).values_list("pk", flat=True))
    q = pairing_queue(user)
    rows = []

    def add(p, step, mine, since):
        other = p.other(mine)
        rows.append({"p": p, "step": step, "mine": mine, "other": other,
                     "other_profile": getattr(other, "profile", None), "since": since})

    for p in q["to_approve"]:
        add(p, "approve", p.client_b, p.created_at)
    for p in q["to_present"]:
        add(p, "present", p.client_b, p.a_decided_at or p.updated_at)
    for p in q["to_introduce"]:
        mine = p.client_a if p.client_a_id in mine_ids else p.client_b
        add(p, "introduce", mine, p.b_decided_at or p.updated_at)
    return sorted(rows, key=lambda r: r["since"])


# ---------------------------------------------------------------- overview (all pairings involving my members)

OVERVIEW_FILTERS = [
    ("open", "Open"),
    ("me", "Waiting on me"),
    ("others", "Waiting on others"),
    ("mutual", "Mutual interest"),
    ("closed", "Closed"),
    ("all", "All"),
]


def where_it_stands(pairing, user):
    """(text, waiting_on_me) for one pairing, from the point of view of `user`."""
    a, b = pairing.client_a, pairing.client_b
    a_mm = a.matchmaker.full_name if a.matchmaker else "the other matchmaker"
    b_mm = b.matchmaker.full_name if b.matchmaker else "the other matchmaker"
    on_b_side = can_manage(user, b)

    if not pairing.is_open:
        return f"Closed: {pairing.closed_reason}", False
    if pairing.approval == P.Approval.PENDING:
        if on_b_side:
            return f"Approve: {a_mm} wants to show {b.preferred_name} to their member", True
        return f"Waiting for {b_mm} to approve", False
    if pairing.a_decision == P.DecisionA.PENDING:
        return f"Waiting for {a.preferred_name} to decide", False
    if pairing.b_decision == P.DecisionB.NOT_PRESENTED:
        if on_b_side:
            return f"Present to {b.preferred_name}: {a.preferred_name} is interested", True
        return f"{a.preferred_name} is interested. Waiting for {b_mm} to present", False
    if pairing.b_decision == P.DecisionB.PENDING:
        return f"Waiting for {b.preferred_name} to decide", False
    if pairing.status == P.Status.MUTUAL and not pairing.introduced_on:
        return "Both interested: arrange the introduction", True
    if pairing.introduced_on:
        return f"Introduced {pairing.introduced_on:%d %b %Y}", False
    return pairing.get_status_display(), False


def pairing_overview(user, show="open"):
    """Every pairing involving the user's members (Admin: all), with where each one stands."""
    mine_ids = set(members_visible_to(user).values_list("pk", flat=True))
    qs = pairings_visible_to(user).select_related("client_a__membership__tier", "client_b__membership__tier")
    if show == "closed":
        qs = qs.filter(status=P.Status.CLOSED)
    elif show == "mutual":
        qs = qs.filter(status=P.Status.MUTUAL)
    elif show != "all":
        qs = qs.exclude(status=P.Status.CLOSED)

    rows = []
    for p in qs.order_by("-updated_at"):
        a_mine, b_mine = p.client_a_id in mine_ids, p.client_b_id in mine_ids
        # internal: both are my members (no approval needed); sent: my member is A; received: my member is B
        kind = "internal" if a_mine and b_mine else "sent" if a_mine else "received"
        text, on_me = where_it_stands(p, user)
        if show == "me" and not on_me:
            continue
        if show == "others" and on_me:
            continue
        mine = p.client_a if a_mine else p.client_b
        other = p.other(mine)
        rows.append({
            "p": p, "mine": mine, "other": other, "other_profile": getattr(other, "profile", None),
            "other_is_mine": other.pk in mine_ids, "kind": kind,
            "stands": text, "on_me": on_me,
        })
    return rows