"""
Elite Grade emails (Part 1). The documents email carries the current Elite documents from
Settings → Documents as attachments, and replies go to the Elite inbox (info@ by default).
"""
import logging
import mimetypes

from django.conf import settings
from django.urls import reverse

from notification.services.mailer import send_templated_email
from notification.services.queue import enqueue

logger = logging.getLogger(__name__)


def _url(path):
    return settings.SITE_URL.rstrip("/") + path


def reply_to_address():
    return getattr(settings, "ELITE_REPLY_TO_EMAIL", "") or settings.TEAM_INBOX_EMAIL


# ---------- Called by the service (queue only)

def notify_verify(case):
    from notification import tasks
    enqueue(tasks.send_elite_email, case.pk, "verify")


def notify_documents(case):
    from notification import tasks
    enqueue(tasks.send_elite_email, case.pk, "documents")


def notify_team_new_application(case):
    from notification import tasks
    enqueue(tasks.send_elite_email, case.pk, "team_new")


def notify_declined(case):
    from notification import tasks
    enqueue(tasks.send_elite_email, case.pk, "declined")


def notify_more_info(case, message):
    from notification import tasks
    enqueue(tasks.send_elite_email, case.pk, "more_info", message)


def notify_acknowledgement(case):
    from notification import tasks
    enqueue(tasks.send_elite_email, case.pk, "acknowledgement")


def notify_payment_request(case):
    from notification import tasks
    enqueue(tasks.send_elite_email, case.pk, "payment_request")


def notify_new_route_needed(case):
    from notification import tasks
    enqueue(tasks.send_elite_email, case.pk, "new_route")


def notify_not_proceeding_bronze(case):
    from notification import tasks
    enqueue(tasks.send_elite_email, case.pk, "bronze_offer")


def notify_bronze_start(case):
    from notification import tasks
    enqueue(tasks.send_elite_email, case.pk, "bronze_start")


# ---------- Delivery (worker)

def elite_attachments(kinds=None):
    """(filename, bytes, mimetype) for each Elite document Admin has uploaded. Missing ones are skipped."""
    from domain.website.models import SiteDocument

    files = []
    for kind in kinds or SiteDocument.ELITE_EMAIL_KINDS:
        document = SiteDocument.current(kind)
        if document is None:
            logger.warning("Elite email sent without %s: not uploaded in Settings → Documents", kind)
            continue
        with document.file.open("rb") as f:
            content = f.read()
        name = f"Elyria - {document.get_kind_display()}.pdf"
        files.append((name, content, mimetypes.guess_type(name)[0] or "application/pdf"))
    return files


def deliver_elite_email(case, kind, message=""):
    if kind == "verify":
        send_templated_email(
            subject="Confirm your email | Elyria Elite Grade",
            template="notification/email/elite_verify",
            context={"case": case, "link": _url(reverse("elite:confirm", args=[case.verify_token]))},
            to=[case.email],
        )
    elif kind == "documents":
        send_templated_email(
            subject="Elite Grade: your documents | Elyria Matchmaking",
            template="notification/email/elite_documents",
            context={"case": case, "reply_to": reply_to_address()},
            to=[case.email],
            attachments=elite_attachments(),
            reply_to=[reply_to_address()],
        )
    elif kind == "team_new":
        heading = f"New Elite Grade application: {case.reference}"
        send_templated_email(
            subject=heading,
            template="notification/email/pairing_update",
            context={
                "heading": heading,
                "message": f"{case.full_name} confirmed their email and has been sent the Elite Grade documents. "
                           f"When their signed documents arrive, upload them to the case.",
                "link": _url(reverse("elite:case-detail", args=[case.pk])),
            },
            to=[settings.TEAM_INBOX_EMAIL],
        )
    elif kind == "declined":
        send_templated_email(
            subject="Your Elite Grade request | Elyria Matchmaking",
            template="notification/email/elite_declined",
            context={"case": case},
            to=[case.email],
        )
    elif kind == "payment_request":
        from domain.elite.services.elite_service import elite_fee
        from domain.website.models import SiteDocument, SiteSettings

        amount, currency = elite_fee()

        send_templated_email(
            subject="Your Elite Grade request has been approved | Elyria Matchmaking",
            template="notification/email/elite_payment_request",
            context={
                "case": case, "fee": f"{currency} {amount:,.0f}", "reply_to": reply_to_address(),
                "bank_details": getattr(SiteSettings.load(), "bank_details", ""),
            },
            to=[case.email],
            attachments=elite_attachments([SiteDocument.Kind.ELITE_INDEMNITY]),
            reply_to=[reply_to_address()],
        )
    elif kind in ("intro_alerts", "intro_alerts_updated"):
        deliver_intro_alerts(case, updated=kind == "intro_alerts_updated")
    elif kind == "acknowledgement":
        # To the NAMED PERSON. Never names the client: that only happens once this is signed.
        from domain.website.models import SiteDocument

        if not case.person_email:
            logger.warning("Acknowledgement for %s not sent: no email for the person", case.reference)
            return
        send_templated_email(
            subject="Your introduction: one document to sign | Elyria Matchmaking",
            template="notification/email/elite_acknowledgement",
            context={"reply_to": reply_to_address()},
            to=[case.person_email],
            attachments=elite_attachments([SiteDocument.Kind.ELITE_ACKNOWLEDGEMENT]),
            reply_to=[reply_to_address()],
        )
    elif kind == "new_route":
        send_templated_email(
            subject="Your Elite Grade request: another way to reach them | Elyria Matchmaking",
            template="notification/email/elite_new_route",
            context={"case": case, "reply_to": reply_to_address()},
            to=[case.email],
            reply_to=[reply_to_address()],
        )
    elif kind == "bronze_offer":
        send_templated_email(
            subject="Your Elite Grade request | Elyria Matchmaking",
            template="notification/email/elite_bronze_offer",
            context={"case": case, "reply_to": reply_to_address()},
            to=[case.email],
            reply_to=[reply_to_address()],
        )
    elif kind == "bronze_start":
        send_templated_email(
            subject="Welcome to Bronze Membership: your next step | Elyria Matchmaking",
            template="notification/email/elite_bronze_start",
            context={"case": case, "link": _url(reverse("website:consultation-request"))},
            to=[case.email],
        )
    elif kind == "more_info":
        send_templated_email(
            subject="Your Elite Grade request: a question from us | Elyria Matchmaking",
            template="notification/email/elite_more_info",
            context={"case": case, "message": message, "reply_to": reply_to_address()},
            to=[case.email],
            reply_to=[reply_to_address()],
        )


# ---------------------------------------------------------------- Part 2b: introduction, reminders

def admin_emails():
    from django.contrib.auth import get_user_model

    from domain.base.models import Groups

    found = list(
        get_user_model().objects.filter(groups__name=Groups.ADMIN, is_active=True)
        .exclude(email="").values_list("email", flat=True).distinct()
    )
    return found or [settings.TEAM_INBOX_EMAIL]


def notify_intro_alerts(case, updated=False):
    from notification import tasks
    enqueue(tasks.send_elite_email, case.pk, "intro_alerts_updated" if updated else "intro_alerts")


def deliver_intro_alerts(case, updated=False):
    """Both people get the date, time and place. No names: just 'your introduction'."""
    from django.utils import timezone

    context = {
        "when": timezone.localtime(case.intro_at),
        "venue": case.intro_venue,
        "video_link": case.intro_video_link,
        "updated": updated,
        "reply_to": reply_to_address(),
    }
    subject = ("Updated: your introduction" if updated else "Your introduction") + " | Elyria Matchmaking"
    recipients = [case.email] + ([case.person_email] if case.person_email else [])
    for address in recipients:
        send_templated_email(
            subject=subject, template="notification/email/elite_intro_alert",
            context=context, to=[address], reply_to=[reply_to_address()],
        )



def deliver_handler_reminder(case, kind):
    if not case.handler or not case.handler.email:
        return
    if kind == "reply_soon":
        heading = f"{case.reference}: reply window ends {case.reply_due_on:%d %b %Y}"
        message = ("The 14-day window for the named person's reply ends soon. If they've answered, record it on "
                   "the case; if there's a good reason, you can extend the window.")
    else:
        heading = f"{case.reference}: the reply window has ended"
        message = (f"The window ended on {case.reply_due_on:%d %b %Y}. Record 'No response' on the case, "
                   "or extend the window if there's a good reason.")
    send_templated_email(
        subject=heading, template="notification/email/pairing_update",
        context={"heading": heading, "message": message, "link": _url(reverse("elite:case-detail", args=[case.pk]))},
        to=[case.handler.email],
    )


def deliver_deletion_reminder(count):
    heading = f"Elite Grade: {count} record{'s' if count != 1 else ''} due for deletion"
    message = ("Some Elite applications or closed cases are past their 30 days. Elyria has promised to delete "
               "the named person's details when a case ends. Open 'Due for deletion' and delete them.")
    send_templated_email(
        subject=heading, template="notification/email/pairing_update",
        context={"heading": heading, "message": message, "link": _url(reverse("elite:cases") + "?show=deletion")},
        to=admin_emails(),
    )