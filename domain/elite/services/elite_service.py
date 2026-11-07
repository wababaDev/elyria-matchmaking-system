"""
Elite Grade, Part 1: apply → confirm email → documents emailed → Admin records the signed
documents → review → approve or decline.
"""
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from domain.elite.models import EliteAccessLog, EliteCase, EliteCaseEvent, EliteDocument
from domain.elite.models.elite_case import ABANDONED_AFTER_DAYS, new_token

S = EliteCase.Status


class EliteError(Exception):
    pass


def log_event(case, text, by=None):
    EliteCaseEvent.objects.create(case=case, text=text, by=by)


def log_access(case, user, action, detail=""):
    EliteAccessLog.objects.create(case=case, user=user, action=action, detail=detail)


def _lock(case):
    return EliteCase.objects.select_for_update().get(pk=case.pk)


def _emails():
    from notification.services import elite_emails

    return elite_emails


# ---------------------------------------------------------------- E1: apply and confirm email

@transaction.atomic
def apply(*, full_name, email, phone=""):
    """
    Start an application. If this email already has one waiting for confirmation, send a fresh link
    instead of creating a second case.
    """
    email = email.strip().lower()
    case = EliteCase.objects.filter(email=email, status=S.AWAITING_EMAIL).first()
    if case:
        case.full_name, case.phone = full_name.strip(), phone.strip()
        case.verify_token = new_token()
        case.verify_sent_at = timezone.now()  # restarts the 48-hour link
        case.save()
        log_event(case, "Applied again: a new confirmation link was sent.")
    else:
        case = EliteCase.objects.create(full_name=full_name.strip(), email=email, phone=phone.strip())
        log_event(case, "Applied for consideration on the website.")
    transaction.on_commit(lambda: _emails().notify_verify(case))
    return case


@transaction.atomic
def confirm_email(token):
    """E1 done: the case moves to Awaiting documents and the Elite email with the documents goes out."""
    case = EliteCase.objects.select_for_update().filter(verify_token=token).first()
    if case is None:
        raise EliteError("This link isn't valid.")
    if case.status != S.AWAITING_EMAIL:
        return case  # already confirmed: clicking the link twice is fine
    if case.verify_link_expired:
        raise EliteError("This link has expired. Please apply again to get a new one.")

    case.email_verified_at = timezone.now()
    case.status = S.AWAITING_DOCUMENTS
    case.save(update_fields=["email_verified_at", "status", "updated_at"])
    log_event(case, "Email confirmed. Elite Grade documents emailed.")
    transaction.on_commit(lambda: _emails().notify_documents(case))
    transaction.on_commit(lambda: _emails().notify_team_new_application(case))
    return case


# ---------------------------------------------------------------- E2/E3: documents received by email

@transaction.atomic
def add_document(case, *, kind, file, by):
    case = _lock(case)
    if case.status not in (S.AWAITING_DOCUMENTS, S.UNDER_REVIEW):
        raise EliteError("Documents can only be added before a decision.")
    document = EliteDocument.objects.create(
        case=case, kind=kind, file=file, original_name=getattr(file, "name", "")[:200], uploaded_by=by,
    )
    log_event(case, f"Uploaded {document.get_kind_display()} ({document.original_name}).", by)
    return document


@transaction.atomic
def confirm_documents(case, *, nda, declaration, request_form, by):
    """Admin ticks what came back signed. All three → Under review (shows in her queue)."""
    case = _lock(case)
    if case.status != S.AWAITING_DOCUMENTS:
        raise EliteError("This case isn't waiting for documents.")
    if not case.documents.exists():
        raise EliteError("Upload the documents you received before ticking them.")

    case.nda_received, case.declaration_received, case.request_form_received = nda, declaration, request_form
    received = [label for label, ok in [("NDA", nda), ("Declaration", declaration), ("Request form", request_form)] if ok]
    if case.all_documents_received:
        case.status = S.UNDER_REVIEW
        case.documents_confirmed_at, case.documents_confirmed_by = timezone.now(), by
        log_event(case, "All documents received (NDA, Declaration, Request form). Now under review.", by)
    else:
        log_event(case, f"Documents received so far: {', '.join(received) or 'none'}.", by)
    case.save()
    return case


# ---------------------------------------------------------------- E4/E5: review and decision

CHECKS = [
    ("check_known_to_client", "Known to the client"),
    ("check_no_prior_rejection", "No prior rejection"),
    ("check_no_power_imbalance", "No power imbalance"),
    ("check_identity_verified", "Identity verified"),
    ("check_suitability", "Suitability assessment complete"),
]


@transaction.atomic
def save_checks(case, *, checks, by):
    case = _lock(case)
    if case.status != S.UNDER_REVIEW:
        raise EliteError("Checks can only be changed while the case is under review.")
    changed = []
    for field, label in CHECKS:
        value = bool(checks.get(field))
        if getattr(case, field) != value:
            setattr(case, field, value)
            changed.append(f"{label}: {'yes' if value else 'no'}")
    case.save()
    if changed:
        log_event(case, "Checks updated. " + "; ".join(changed) + ".", by)
    return case


@transaction.atomic
def decide(case, *, decision, note="", by):
    """
    approve: all checks must be ticked; no fee yet (payment is the next step).
    decline: the client gets an automatic message with no reason. No fee, no Bronze offer. Closed.
    more_info: stays under review; the message is emailed to the client.
    """
    case = _lock(case)
    if case.status != S.UNDER_REVIEW:
        raise EliteError("Only cases under review can be decided.")

    if decision == "approve":
        if not case.all_checks_done:
            raise EliteError("Tick all the checks before approving.")
        case.status = S.APPROVED
        case.decided_at, case.decided_by = timezone.now(), by
        case.save()
        log_event(case, "Approved." + (f" Note: {note}" if note else ""), by)
    elif decision == "decline":
        case.status = S.DECLINED
        case.decided_at, case.decided_by = timezone.now(), by
        case.save()
        log_event(case, "Declined. Client sent the standard 'not proceeding' message." + (f" Note: {note}" if note else ""), by)
        transaction.on_commit(lambda: _emails().notify_declined(case))
    elif decision == "more_info":
        if not note.strip():
            raise EliteError("Write the message to send to the client.")
        log_event(case, f"More information requested from the client: {note.strip()}", by)
        transaction.on_commit(lambda: _emails().notify_more_info(case, note.strip()))
    else:
        raise EliteError("Unknown decision.")
    return case


# ---------------------------------------------------------------- clean-up

def abandoned_cases(now=None):
    """
    Never confirmed within 30 days of applying, or confirmed but no signed documents recorded
    within 30 days of confirming.
    """
    cutoff = (now or timezone.now()) - timedelta(days=ABANDONED_AFTER_DAYS)
    return EliteCase.objects.filter(
        Q(status=S.AWAITING_EMAIL, verify_sent_at__lt=cutoff)
        | Q(status=S.AWAITING_DOCUMENTS, email_verified_at__lt=cutoff)
    )


def delete_abandoned(now=None):
    """Delete abandoned applications, including their files. Returns how many were deleted."""
    count = 0
    for case in abandoned_cases(now):
        for document in case.documents.all():
            document.file.delete(save=False)
        case.delete()  # its timeline and access log go with it (bulk delete, not entry by entry)
        count += 1
    return count