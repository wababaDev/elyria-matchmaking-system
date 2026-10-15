from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse

from domain.website.models import SiteSettings
from notification.services.queue import enqueue

# ---------- Delivery (run by the worker; errors bubble up so the task retries)

def deliver_payment_instructions(consultation):
    body = render_to_string(
        "notification/email/consultation_payment_instructions.txt",
        {"consultation": consultation, "site": SiteSettings.load()},
    )
    send_mail(
        subject="Your private consultation with Elyria Matchmaking",
        message=body,
        from_email=None,
        recipient_list=[consultation.email],
    )


def deliver_team_alert(consultation):
    link = settings.SITE_URL.rstrip("/") + reverse(
        "matchmaking:consultation-request-detail", args=[consultation.pk]
    )
    body = render_to_string(
        "notification/email/consultation_team_alert.txt",
        {"consultation": consultation, "link": link},
    )
    send_mail(
        subject=f"New consultation request: {consultation.full_name}",
        message=body,
        from_email=None,
        recipient_list=[settings.TEAM_INBOX_EMAIL],
    )


def deliver_consultation_booked(consultation, rebooked=False):
    applicant = consultation.request
    body = render_to_string(
        "notification/email/consultation_booked.txt",
        {"consultation": consultation, "applicant": applicant, "rebooked": rebooked},
    )
    subject = "Your consultation has been rescheduled" if rebooked else "Your private consultation is booked"
    send_mail(
        subject=f"{subject} | Elyria Matchmaking",
        message=body,
        from_email=None,
        recipient_list=[applicant.email],
    )


# ---------- Called by services (queue only)

def notify_new_consultation_request(consultation):
    from notification import tasks

    enqueue(tasks.send_payment_instructions_email, consultation.pk)
    enqueue(tasks.send_team_alert_email, consultation.pk)


def notify_consultation_booked(consultation, *, rebooked=False):
    from notification import tasks

    enqueue(tasks.send_consultation_booked_email, consultation.pk, rebooked)