from django.conf import settings
from django.urls import reverse

from notification.services.mailer import send_templated_email


def deliver_renewal_reminder(membership, *, days):
    """One email to the member, one to their matchmaker. No other member's details, as always."""
    client = membership.client
    context = {"membership": membership, "client": client, "days": days}

    send_templated_email(
        subject=f"Your Elyria membership ends on {membership.end_date:%d %B %Y}",
        template="notification/email/renewal_reminder_member",
        context=context,
        to=[client.user.email],
    )
    if client.matchmaker and client.matchmaker.email:
        link = settings.SITE_URL.rstrip("/") + reverse("matchmaking:member-detail", args=[client.pk])
        send_templated_email(
            subject=f"Renewal due in {days} days: {client.full_name}",
            template="notification/email/renewal_reminder_team",
            context={**context, "link": link, "button_label": "Open the member"},
            to=[client.matchmaker.email],
        )