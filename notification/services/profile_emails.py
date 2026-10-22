from django.conf import settings
from django.urls import reverse

from notification.services.mailer import send_templated_email
from notification.services.queue import enqueue


# ---------- Delivery (run by the worker; errors bubble up so the task retries)

def deliver_profile_completed(client):
    """Tell the member's matchmaker (or the team inbox if nobody is assigned yet)."""
    link = settings.SITE_URL.rstrip("/") + reverse("matchmaking:member-detail", args=[client.pk])
    to = client.matchmaker.email if client.matchmaker and client.matchmaker.email else settings.TEAM_INBOX_EMAIL
    send_templated_email(
        subject=f"Profile complete: {client.full_name}",
        template="notification/email/profile_completed",
        context={"client": client, "link": link},
        to=[to],
    )


# ---------- Called by services (queue only)

def notify_profile_completed(client):
    from notification import tasks

    enqueue(tasks.send_profile_completed_email, client.pk)