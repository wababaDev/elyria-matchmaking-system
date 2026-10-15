from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse

from domain.website.models import SiteSettings
from notification.services.queue import enqueue


def deliver_enquiry_alert(enquiry):
    inbox = SiteSettings.load().contact_email or settings.TEAM_INBOX_EMAIL
    link = settings.SITE_URL.rstrip("/") + reverse("matchmaking:enquiry-detail", args=[enquiry.pk])
    body = render_to_string("notification/email/enquiry_team_alert.txt", {"enquiry": enquiry, "link": link})
    tier = enquiry.tier.name if enquiry.tier else "General"
    send_mail(
        subject=f"New enquiry ({tier}): {enquiry.first_name}",
        message=body,
        from_email=None,
        recipient_list=[inbox],
    )


def notify_new_enquiry(enquiry):
    from notification import tasks

    enqueue(tasks.send_enquiry_alert_email, enquiry.pk)