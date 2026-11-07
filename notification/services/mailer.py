from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from domain.website.models import SiteSettings


def send_templated_email(*, subject, template, context, to, attachments=None, reply_to=None):
    """
    Render <template>.txt and <template>.html with the same context and send both.

    The plain-text version stays as the fallback (and helps spam scores);
    email apps that show HTML use the styled version.
    attachments: optional list of (filename, bytes, mimetype).
    """
    ctx = {
        "site": SiteSettings.load(),
        "site_url": settings.SITE_URL.rstrip("/"),
        **context,
    }
    message = EmailMultiAlternatives(
        subject=subject,
        body=render_to_string(f"{template}.txt", ctx),
        to=to,
        reply_to=reply_to,
    )
    message.attach_alternative(render_to_string(f"{template}.html", ctx), "text/html")
    for filename, content, mimetype in attachments or []:
        message.attach(filename, content, mimetype)
    message.send()