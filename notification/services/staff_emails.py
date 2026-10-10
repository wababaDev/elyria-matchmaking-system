import logging

from django.core.mail import send_mail
from django.template.loader import render_to_string

from notification.services.member_emails import set_password_link

logger = logging.getLogger(__name__)


def send_staff_invite(user):
    try:
        body = render_to_string(
            "notification/email/staff_invite.txt",
            {"user": user, "link": set_password_link(user)},
        )
        send_mail(
            subject="Your Elyria staff account",
            message=body,
            from_email=None,
            recipient_list=[user.email],
        )
    except Exception:
        logger.exception("Staff invite failed for user %s", user.pk)