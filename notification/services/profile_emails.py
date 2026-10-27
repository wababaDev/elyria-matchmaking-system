from django.conf import settings
from django.urls import reverse

from notification.services.mailer import send_templated_email
from notification.services.queue import enqueue


# ---------- Delivery (run by the worker; errors bubble up so the task retries)

def deliver_profile_completed(client):
    """Tell the member's matchmaker (or the team inbox if nobody is assigned yet)."""
    link = settings.SITE_URL.rstrip("/") + reverse("matchmaking:member-detail", args=[client.pk])
    send_templated_email(
        subject=f"Profile complete: {client.full_name}",
        template="notification/email/profile_completed",
        context={"client": client, "link": link},
        to=[_recipient(client)],
    )


def deliver_profile_updated(client, sections, important=None):
    """A member changed answers after completing their profile. `important`: high-impact changes."""
    link = settings.SITE_URL.rstrip("/") + reverse("matchmaking:member-detail", args=[client.pk])
    prefix = "Important profile change" if important else "Profile updated"
    send_templated_email(
        subject=f"{prefix}: {client.full_name}",
        template="notification/email/profile_updated",
        context={"client": client, "sections": sections, "important": important or [], "link": link},
        to=[_recipient(client)],
    )


def _recipient(client):
    """The member's matchmaker, or the team inbox if nobody is assigned yet."""
    if client.matchmaker and client.matchmaker.email:
        return client.matchmaker.email
    return settings.TEAM_INBOX_EMAIL


# ---------- Called by services (queue only)

def notify_profile_completed(client):
    from notification import tasks

    enqueue(tasks.send_profile_completed_email, client.pk)


def notify_profile_updated(client, sections, important=None):
    from notification import tasks

    enqueue(tasks.send_profile_updated_email, client.pk, list(sections), list(important or []))