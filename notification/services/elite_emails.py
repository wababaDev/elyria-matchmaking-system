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