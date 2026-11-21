"""Date feedback: a Serious behaviour flag emails every Admin straight away."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse

from domain.base.models import Groups
from notification.services.mailer import send_templated_email
from notification.services.queue import enqueue


# ---------- Called by the feedback service (queue only)

def notify_admin_serious_flag(feedback):
    from notification import tasks

    enqueue(tasks.send_serious_flag_email, feedback.pk)


# ---------- Delivery (worker)

def deliver_serious_flag(feedback):
    admins = list(
        get_user_model().objects.filter(groups__name=Groups.ADMIN, is_active=True)
        .exclude(email="").values_list("email", flat=True)
    ) or [settings.TEAM_INBOX_EMAIL]
    client = feedback.client
    heading = f"Serious flag after a date: {feedback.introduction_id}"
    message = (
        f"{feedback.recorded_by.full_name if feedback.recorded_by else 'A matchmaker'} recorded a Serious "
        f"behaviour flag in {client.full_name}'s feedback for date {feedback.date_number} "
        f"({feedback.date:%d %b %Y}). Flags: {', '.join(feedback.flag_labels) or 'none ticked'}. "
        f"Open the member's Pairings tab for the details."
    )
    send_templated_email(
        subject=heading,
        template="notification/email/pairing_update",
        context={
            "heading": heading, "message": message,
            "link": settings.SITE_URL.rstrip("/") + reverse("matchmaking:member-detail", args=[client.pk]) + "#pairings",
        },
        to=admins,
    )