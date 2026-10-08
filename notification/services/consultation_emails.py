import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse

logger = logging.getLogger(__name__)


def send_payment_instructions(consultation):
    body = render_to_string(
        "notification/email/consultation_payment_instructions.txt",
        {"consultation": consultation},
    )
    send_mail(
        subject="Your private consultation with Elyria Matchmaking",
        message=body,
        from_email=None,  # uses DEFAULT_FROM_EMAIL
        recipient_list=[consultation.email],
    )


def send_team_alert(consultation):
    # TODO: link to the request's own page once the staff request list is built
    link = settings.SITE_URL.rstrip("/") + reverse("matchmaking:dashboard")
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


def notify_new_consultation_request(consultation):
    # One failing email must not stop the other, or crash the applicant's page.
    for send in (send_payment_instructions, send_team_alert):
        try:
            send(consultation)
        except Exception:
            logger.exception("%s failed for consultation request %s", send.__name__, consultation.pk)

def notify_consultation_booked(consultation, *, rebooked=False):
    applicant = consultation.request
    try:
        body = render_to_string(
            "notification/email/consultation_booked.txt",
            {"consultation": consultation, "applicant": applicant, "rebooked": rebooked},
        )
        subject = (
            "Your consultation has been rescheduled" if rebooked else "Your private consultation is booked"
        )
        send_mail(
            subject=f"{subject} | Elyria Matchmaking",
            message=body,
            from_email=None,
            recipient_list=[applicant.email],
        )
    except Exception:
        logger.exception("Booking email failed for consultation %s", consultation.pk)