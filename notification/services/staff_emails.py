from django.core.mail import send_mail
from django.template.loader import render_to_string

from notification.services.member_emails import set_password_link
from notification.services.queue import enqueue


def deliver_staff_invite(user):
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


def send_staff_invite(user):
    from notification import tasks

    enqueue(tasks.send_staff_invite_email, user.pk)