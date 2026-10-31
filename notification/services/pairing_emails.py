"""
Matching emails. Tasks take IDs; the wording is decided here, in the worker.
"""
from django.conf import settings
from django.urls import reverse

from notification.services.mailer import send_templated_email
from notification.services.queue import enqueue


def _url(path):
    return settings.SITE_URL.rstrip("/") + path


def _staff_address(user):
    return user.email if user and user.email else settings.TEAM_INBOX_EMAIL


def _member_link(client):
    return _url(reverse("matchmaking:member-detail", args=[client.pk])) + "#pairings"


# Each kind: (who it goes to, subject, message, which member page the button opens)
def _staff_email(pairing, kind):
    a, b = pairing.client_a, pairing.client_b
    if kind == "approval_needed":
        return (
            b.matchmaker,
            f"Pairing to approve: {b.preferred_name}",
            f"{pairing.added_by.full_name} would like to pair your member {b.full_name} with one of their members. "
            f"Nobody sees anything until you approve. Please approve or decline it.",
            b,
        )
    if kind == "approval_answered":
        answer = "approved" if pairing.approval == pairing.Approval.APPROVED else "declined"
        return (
            pairing.added_by,
            f"Pairing {answer}: {a.preferred_name}",
            f"The pairing you proposed for {a.full_name} was {answer} by the other member's matchmaker."
            + (f" {a.preferred_name} can now see it in their portal." if answer == "approved" else ""),
            a,
        )
    if kind == "ready_to_present":
        return (
            b.matchmaker,
            f"Ready to present to {b.preferred_name}",
            f"{a.preferred_name} is interested. The pairing is ready for you to present to your member "
            f"{b.full_name}: open their Pairings tab, write their note and press Present.",
            b,
        )
    if kind == "mutual_interest_a":
        return (a.matchmaker, f"Mutual interest: {a.preferred_name}",
                f"Both members said yes. Arrange the introduction for {a.full_name}.", a)
    if kind == "mutual_interest_b":
        return (b.matchmaker, f"Mutual interest: {b.preferred_name}",
                f"Both members said yes. Arrange the introduction for {b.full_name}.", b)
    if kind == "proposed_for_your_member":
        return (
            a.matchmaker,
            f"New pairing for {a.preferred_name}",
            f"{pairing.added_by.full_name} proposed a pairing for your member {a.full_name}. "
            + ("It's waiting for the other matchmaker's approval." if pairing.approval == pairing.Approval.PENDING
               else f"{a.preferred_name} can already see it in their portal."),
            a,
        )
    raise ValueError(kind)


# ---------- Delivery (worker)

def deliver_pairing_staff_email(pairing, kind):
    to_user, subject, message, page_client = _staff_email(pairing, kind)
    send_templated_email(
        subject=subject,
        template="notification/email/pairing_update",
        context={"heading": subject, "message": message, "link": _member_link(page_client)},
        to=[_staff_address(to_user)],
    )


def deliver_new_introduction(client):
    send_templated_email(
        subject="A new introduction to review | Elyria Matchmaking",
        template="notification/email/new_introduction",
        context={"client": client, "link": _url(reverse("portal:matches"))},
        to=[client.user.email],
    )


# ---------- Called by the pairing service (queue only)

def _staff(pairing, kind):
    from notification import tasks

    enqueue(tasks.send_pairing_staff_email, pairing.pk, kind)


def notify_approval_needed(pairing):
    _staff(pairing, "approval_needed")


def notify_proposer_of_approval(pairing):
    _staff(pairing, "approval_answered")


def notify_ready_to_present(pairing):
    _staff(pairing, "ready_to_present")


def notify_mutual_interest(pairing):
    _staff(pairing, "mutual_interest_a")
    if pairing.client_b.matchmaker_id != pairing.client_a.matchmaker_id:
        _staff(pairing, "mutual_interest_b")


def notify_member_new_introduction(pairing, client):
    from notification import tasks

    enqueue(tasks.send_new_introduction_email, client.pk)


def notify_matchmaker_of_pairing(pairing):
    _staff(pairing, "proposed_for_your_member")