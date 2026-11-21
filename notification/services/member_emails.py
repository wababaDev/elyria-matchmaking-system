from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from notification.services.mailer import send_templated_email
from notification.services.queue import enqueue


def set_password_link(user):
    path = reverse("base:set-password", kwargs={
        "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
        "token": default_token_generator.make_token(user),
    })
    return settings.SITE_URL.rstrip("/") + path


# ---------- Delivery

def deliver_member_welcome(client):
    send_templated_email(
        subject="Welcome to Elyria Matchmaking: set up your account",
        template="notification/email/member_welcome",
        context={"client": client, "membership": client.membership, "link": set_password_link(client.user)},
        to=[client.user.email],
    )


def deliver_sign_in_link(client):
    send_templated_email(
        subject="Your Elyria sign-in link",
        template="notification/email/member_sign_in_link",
        context={"client": client, "link": set_password_link(client.user)},
        to=[client.user.email],
    )


def deliver_sign_in_email_changed(client, old_email):
    send_templated_email(
        subject="Your Elyria sign-in email has changed",
        template="notification/email/sign_in_email_changed",
        context={"client": client, "old_email": old_email, "new_email": client.user.email},
        to=[client.user.email, old_email],
    )

# ---------- Called by services and views (queue only)

def send_member_welcome(client):
    from notification import tasks

    enqueue(tasks.send_member_welcome_email, client.pk)


def send_sign_in_link(client):
    from notification import tasks

    enqueue(tasks.send_sign_in_link_email, client.pk)

def send_sign_in_email_changed(client, old_email):
    from notification import tasks

    enqueue(tasks.send_sign_in_email_changed_email, client.pk, old_email)