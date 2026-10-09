import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

logger = logging.getLogger(__name__)


def set_password_link(user):
    path = reverse("base:set-password", kwargs={
        "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
        "token": default_token_generator.make_token(user),
    })
    return settings.SITE_URL.rstrip("/") + path


def send_member_welcome(client):
    try:
        body = render_to_string(
            "notification/email/member_welcome.txt",
            {"client": client, "membership": client.membership, "link": set_password_link(client.user)},
        )
        send_mail(
            subject="Welcome to Elyria Matchmaking: set up your account",
            message=body,
            from_email=None,
            recipient_list=[client.user.email],
        )
    except Exception:
        logger.exception("Welcome email failed for client %s", client.pk)