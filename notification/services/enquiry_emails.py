from django.conf import settings
from django.urls import reverse

from domain.website.models import SiteSettings
from notification.services.mailer import send_templated_email
from notification.services.queue import enqueue


def deliver_enquiry_alert(enquiry):
    inbox = SiteSettings.load().contact_email or settings.TEAM_INBOX_EMAIL
    link = settings.SITE_URL.rstrip("/") + reverse("matchmaking:enquiry-detail", args=[enquiry.pk])
    tier = enquiry.tier.name if enquiry.tier else "General"
    send_templated_email(
        subject=f"New enquiry ({tier}): {enquiry.first_name}",
        template="notification/email/enquiry_team_alert",
        context={"enquiry": enquiry, "link": link},
        to=[inbox],
    )


def notify_new_enquiry(enquiry):
    from notification import tasks

    enqueue(tasks.send_enquiry_alert_email, enquiry.pk)