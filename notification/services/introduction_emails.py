"""
Introduction allowance reminders. Sent after an introduction date is recorded:
- one introduction left: "almost at your last introduction, consider renewing or upgrading"
- none left: "you've used all your introductions"
Both go to the member and to their matchmaker. Unlimited tiers never get these.
"""
from django.conf import settings
from django.urls import reverse

from notification.services.mailer import send_templated_email
from notification.services.queue import enqueue


def _url(path):
    return settings.SITE_URL.rstrip("/") + path


# ---------- Called by the pairing service (queue only)

def notify_if_near_limit(client):
    from notification import tasks

    enqueue(tasks.send_introductions_email, client.pk)


# ---------- Delivery (worker)

def deliver_introductions_email(client):
    from domain.matchmaking.services.member_service import introduction_status

    membership = getattr(client, "membership", None)
    status = introduction_status(membership)
    if not status or status["state"] == "ok":
        return

    last = status["state"] == "last"
    used, allowed = status["used"], status["allowed"]

    # Member
    send_templated_email(
        subject=("You have one introduction left" if last else "You've used all your introductions")
        + " | Elyria Matchmaking",
        template="notification/email/introductions_member",
        context={
            "client": client, "last": last, "used": used, "allowed": allowed,
            "tier": membership.tier.name, "end_date": membership.end_date,
        },
        to=[client.user.email],
    )

    # Matchmaker
    heading = (
        f"{client.preferred_name} has one introduction left" if last
        else f"{client.preferred_name} has used all their introductions"
    )
    message = (
        f"{client.full_name} has used {used} of {allowed} introductions on {membership.tier.name}. "
        + ("Their next introduction will be their last. " if last else "")
        + "They've been emailed a reminder to renew or upgrade. You may want to follow up with them."
    )
    send_templated_email(
        subject=heading,
        template="notification/email/pairing_update",
        context={
            "heading": heading, "message": message,
            "link": _url(reverse("matchmaking:member-detail", args=[client.pk])),
        },
        to=[client.matchmaker.email if client.matchmaker and client.matchmaker.email else settings.TEAM_INBOX_EMAIL],
    )