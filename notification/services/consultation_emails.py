from django.conf import settings
from django.urls import reverse

from notification.services.mailer import send_templated_email
from notification.services.queue import enqueue

# ---------- Delivery (run by the worker; errors bubble up so the task retries)

def deliver_payment_instructions(consultation):
    send_templated_email(
        subject="Your private consultation with Elyria Matchmaking",
        template="notification/email/consultation_payment_instructions",
        context={"consultation": consultation},
        to=[consultation.email],
    )


def deliver_team_alert(consultation):
    link = settings.SITE_URL.rstrip("/") + reverse(
        "matchmaking:consultation-request-detail", args=[consultation.pk]
    )
    send_templated_email(
        subject=f"New consultation request: {consultation.full_name}",
        template="notification/email/consultation_team_alert",
        context={"consultation": consultation, "link": link},
        to=[settings.TEAM_INBOX_EMAIL],
    )


def deliver_consultation_booked(consultation, rebooked=False):
    applicant = consultation.request
    subject = "Your consultation has been rescheduled" if rebooked else "Your private consultation is booked"
    send_templated_email(
        subject=f"{subject} | Elyria Matchmaking",
        template="notification/email/consultation_booked",
        context={"consultation": consultation, "applicant": applicant, "rebooked": rebooked},
        to=[applicant.email],
    )


# ---------- Called by services (queue only)

def notify_new_consultation_request(consultation):
    from notification import tasks

    enqueue(tasks.send_payment_instructions_email, consultation.pk)
    enqueue(tasks.send_team_alert_email, consultation.pk)


def notify_consultation_booked(consultation, *, rebooked=False):
    from notification import tasks

    enqueue(tasks.send_consultation_booked_email, consultation.pk, rebooked)


def resend_payment_instructions(consultation):
    from notification import tasks

    enqueue(tasks.send_payment_instructions_email, consultation.pk)