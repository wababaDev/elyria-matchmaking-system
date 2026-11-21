from notification.services.mailer import send_templated_email
from notification.services.member_emails import set_password_link
from notification.services.queue import enqueue


def deliver_staff_invite(user):
    send_templated_email(
        subject="Your Elyria staff account",
        template="notification/email/staff_invite",
        context={"user": user, "link": set_password_link(user)},
        to=[user.email],
    )


def send_staff_invite(user):
    from notification import tasks

    enqueue(tasks.send_staff_invite_email, user.pk)