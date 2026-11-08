"""
Elite Grade.
Part 1: apply → confirm email → documents emailed → Admin records the signed documents → review → decide.
Part 2a: Case Handler → fee + Indemnity Notice → named person → one outreach (14 days) →
         declined / no response / agreed → acknowledgement → identity shared, or Bronze offer → closed.
"""
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from domain.elite import crypto
from domain.elite.models import EliteAccessLog, EliteCase, EliteCaseEvent, EliteDocument, SuppressionEntry
from domain.elite.models.elite_case import ABANDONED_AFTER_DAYS, new_token

REPLY_WINDOW_DAYS = 14
WIPE_AFTER_DAYS = 30

S = EliteCase.Status


class EliteError(Exception):
    pass


def log_event(case, text, by=None):
    EliteCaseEvent.objects.create(case=case, text=text, by=by)


def log_access(case, user, action, detail=""):
    EliteAccessLog.objects.create(case=case, user=user, action=action, detail=detail)


def _lock(case):
    return EliteCase.objects.select_for_update().get(pk=case.pk)


# ---------------------------------------------------------------- who sees what

def is_admin(user):
    return user.has_perm("base.manage_staff")


def cases_visible_to(user):
    """Admin: every case. A Case Handler: only the cases assigned to her. Everyone else: none."""
    if is_admin(user):
        return EliteCase.objects.all()
    return EliteCase.objects.filter(handler=user)


def can_handle(user, case):
    """The Case Handler's actions. Admin can step in on any case."""
    return is_admin(user) or (case.handler_id is not None and case.handler_id == user.pk)


def _require_handler(user, case):
    if not can_handle(user, case):
        raise EliteError("Only this case's Case Handler (or Admin) can do that.")


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
    if not case.is_open or case.status == S.AWAITING_EMAIL:
        raise EliteError("Documents can't be added to this case now.")
    if not (is_admin(by) or can_handle(by, case)):
        raise EliteError("You can't add documents to this case.")
    document = EliteDocument.objects.create(
        case=case, kind=kind, file=file, original_name=getattr(file, "name", "")[:200], uploaded_by=by,
    )
    log_event(case, f"Uploaded {document.get_kind_display()} ({document.original_name}).", by)
    return document


@transaction.atomic
def confirm_documents(case, *, nda, declaration, request_form, by):
    """Admin ticks what came back signed. All three → Under review (shows in her queue)."""
    case = _lock(case)
    if not is_admin(by):
        raise EliteError("Only Admin can do that.")
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
    if not is_admin(by):
        raise EliteError("Only Admin can do that.")
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
    if not is_admin(by):
        raise EliteError("Only Admin can do that.")
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
        case.closed_at = case.decided_at
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


# ---------------------------------------------------------------- E6: Case Handler, fee, Indemnity Notice

def elite_tier():
    """The Elite Grade tier in Settings → Membership tiers (it can be retired; its price still applies)."""
    from domain.matchmaking.models import MembershipTier

    return MembershipTier.objects.filter(name__icontains="elite").order_by("display_order").first()


def elite_fee():
    """(amount, currency) from Settings → Membership tiers. The fee can't be typed in on the case."""
    tier = elite_tier()
    if tier is None or tier.price is None:
        raise EliteError("Set the Elite Grade price in Settings → Membership tiers first.")
    return tier.price, tier.currency


@transaction.atomic
def assign_handler(case, *, handler, by):
    """Admin picks the Case Handler. The first time, the client is asked to pay and sign the Indemnity Notice."""
    case = _lock(case)
    if not is_admin(by):
        raise EliteError("Only Admin can assign the Case Handler.")
    if not case.is_open or case.status in (S.AWAITING_EMAIL, S.AWAITING_DOCUMENTS, S.UNDER_REVIEW):
        raise EliteError("A Case Handler is assigned once the case is approved.")
    first_time = case.handler_id is None
    if first_time:
        elite_fee()  # the payment request needs the price: stop here if it isn't set
    case.handler, case.handler_assigned_at = handler, timezone.now()
    case.save()
    log_event(case, f"Case Handler: {handler.full_name}.", by)
    if first_time and case.status == S.APPROVED:
        log_event(case, "Payment request and Indemnity Notice emailed to the client.")
        transaction.on_commit(lambda: _emails().notify_payment_request(case))
    return case


@transaction.atomic
def record_fee(case, *, method, reference, paid_on, by):
    """The amount always comes from the Elite Grade tier's price in Settings."""
    case = _lock(case)
    _require_handler(by, case)
    if case.status != S.APPROVED:
        raise EliteError("The fee is recorded once the case is approved and before outreach.")
    if case.fee_recorded:
        raise EliteError("The fee has already been recorded.")
    if paid_on > timezone.localdate():
        raise EliteError("The payment date can't be in the future.")
    amount, currency = elite_fee()
    case.fee_amount, case.fee_currency = amount, currency
    case.fee_method, case.fee_reference, case.fee_paid_on, case.fee_recorded_by = method, reference.strip(), paid_on, by
    case.save()
    note = " (recorded by the Case Handler)" if case.handler_id == by.pk else ""
    log_event(case, f"Elite Grade fee recorded: {currency} {amount:,.2f}, paid {paid_on:%d %b %Y}{note}. Non-refundable.", by)
    _maybe_ready_for_outreach(case, by)
    return case


@transaction.atomic
def confirm_indemnity(case, *, by):
    case = _lock(case)
    _require_handler(by, case)
    if case.status != S.APPROVED:
        raise EliteError("The Indemnity Notice is recorded before outreach.")
    if not case.documents.filter(kind=EliteDocument.Kind.INDEMNITY).exists():
        raise EliteError("Upload the signed Indemnity Notice first.")
    case.indemnity_received = True
    case.save()
    log_event(case, "Signed Indemnity Notice received.", by)
    _maybe_ready_for_outreach(case, by)
    return case


def _maybe_ready_for_outreach(case, by):
    if case.fee_recorded and case.indemnity_received and case.status == S.APPROVED:
        case.status = S.PAID
        case.save(update_fields=["status", "updated_at"])
        log_event(case, "Fee and Indemnity Notice in. Ready for outreach.", by)


# ---------------------------------------------------------------- E7: the named person and outreach

def suppression_matches(name, contact):
    """('contact' | 'name' | None): has this person been recorded as 'do not approach'?"""
    contact_fp = crypto.fingerprint(crypto.normalise_contact(contact)) if contact else ""
    if contact_fp and SuppressionEntry.objects.filter(contact_fingerprint=contact_fp).exists():
        return "contact"
    if SuppressionEntry.objects.filter(name_fingerprint=crypto.fingerprint(crypto.normalise_name(name))).exists():
        return "name"
    return None


@transaction.atomic
def record_person(case, *, name, contact_type, contact, by):
    """The person the client named, and the contact route the client gave. Elyria never searches for them."""
    case = _lock(case)
    _require_handler(by, case)
    if case.status not in (S.APPROVED, S.PAID):
        raise EliteError("The person's details are recorded before outreach.")
    match = suppression_matches(name, contact)
    if match == "contact":
        raise EliteError(
            "This person is on the 'do not approach' list (same contact). They can't be approached. "
            "Speak to Admin about closing this case."
        )
    first = not case.has_person
    case.person_name_enc = crypto.encrypt(name.strip())
    case.person_contact_type = contact_type
    case.person_contact_enc = crypto.encrypt(contact.strip())
    case.save()
    log_event(case, "Named person's details recorded." if first else "Named person's contact route updated.", by)
    if match == "name":
        log_event(case, "Warning: someone with the same name is on the 'do not approach' list. Check before outreach.", by)
    return case, match


@transaction.atomic
def record_outreach(case, *, delivered, sent_on, by):
    """
    One discreet message without naming the client. A bounced message isn't an attempt: the client is
    asked for another route. Delivered: the 14-day reply window starts.
    """
    case = _lock(case)
    _require_handler(by, case)
    if case.status != S.PAID:
        raise EliteError("Outreach happens once the fee and Indemnity Notice are in.")
    if not case.has_person:
        raise EliteError("Record the person's details first.")
    if not delivered:
        case.outreach_bounces += 1
        case.save()
        log_event(case, f"Outreach bounced ({sent_on:%d %b %Y}). Not counted as an attempt. Client asked for another route.", by)
        transaction.on_commit(lambda: _emails().notify_new_route_needed(case))
        return case
    case.status = S.OUTREACH_SENT
    case.outreach_delivered_on = sent_on
    case.reply_due_on = sent_on + timedelta(days=REPLY_WINDOW_DAYS)
    case.save()
    log_event(case, f"Outreach delivered {sent_on:%d %b %Y}. Reply due by {case.reply_due_on:%d %b %Y}.", by)
    return case


# ---------------------------------------------------------------- E8/E9: the answer

@transaction.atomic
def record_answer(case, *, answer, person_email="", by):
    """
    answer: 'agreed' | 'declined' | 'no_response'. No response only once the 14 days have passed.
    Agreed: if they gave an email, the Introduction Acknowledgement is emailed to them straight away.
    """
    case = _lock(case)
    _require_handler(by, case)
    if case.status != S.OUTREACH_SENT:
        raise EliteError("There's no outreach waiting for an answer.")
    if answer == "agreed":
        case.status = S.AGREED
        case.save()
        log_event(case, "The person agreed to hear more.", by)
        if person_email.strip():
            _send_acknowledgement(case, person_email, by)
        else:
            log_event(case, "No email given: the handler sends the Introduction Acknowledgement another way.", by)
        return case
    if answer == "no_response" and timezone.localdate() <= case.reply_due_on:
        raise EliteError(f"The reply window runs until {case.reply_due_on:%d %b %Y}.")
    if answer not in ("declined", "no_response"):
        raise EliteError("Unknown answer.")
    return _close_without_introduction(case, outcome=answer, by=by)


def _send_acknowledgement(case, person_email, by):
    case.person_email_enc = crypto.encrypt(person_email.strip().lower())
    case.save(update_fields=["person_email_enc", "updated_at"])
    log_event(case, "Introduction Acknowledgement emailed to the person (replies go to info@).", by)
    transaction.on_commit(lambda: _emails().notify_acknowledgement(case))


@transaction.atomic
def send_acknowledgement(case, *, person_email, by):
    """Email (or re-send) the Introduction Acknowledgement to the person, e.g. if they gave an email later."""
    case = _lock(case)
    _require_handler(by, case)
    if case.status != S.AGREED:
        raise EliteError("The acknowledgement is sent once the person agrees to hear more.")
    _send_acknowledgement(case, person_email, by)
    return case


@transaction.atomic
def record_acknowledgement(case, *, signed, person_email="", by):
    """Signed: only now is the client's identity shared. Not signed: treated as no response."""
    case = _lock(case)
    _require_handler(by, case)
    if case.status != S.AGREED:
        raise EliteError("The case isn't waiting for the acknowledgement.")
    if not signed:
        return _close_without_introduction(case, outcome=EliteCase.Outcome.NOT_SIGNED, by=by)
    if not case.documents.filter(kind=EliteDocument.Kind.ACKNOWLEDGEMENT).exists():
        raise EliteError("Upload the signed Introduction Acknowledgement first.")
    case.acknowledgement_received = True
    if person_email.strip():
        case.person_email_enc = crypto.encrypt(person_email.strip().lower())
    case.status = S.INTRODUCTION
    case.save()
    log_event(case, "Introduction Acknowledgement signed. The client's identity can now be shared. Next: the introduction.", by)
    return case


def _close_without_introduction(case, *, outcome, by):
    """Do-not-approach entry, then the Bronze offer (the fee was paid and outreach happened)."""
    SuppressionEntry.objects.create(
        name_fingerprint=crypto.fingerprint(crypto.normalise_name(case.person_name)),
        contact_fingerprint=crypto.fingerprint(crypto.normalise_contact(case.person_contact)),
        reason=outcome, case_reference=case.reference,
    )
    case.outcome = outcome
    case.status = S.BRONZE_OFFERED
    case.bronze_offered_at = timezone.now()
    case.save()
    log_event(case, f"{EliteCase.Outcome(outcome).label}. Added to the 'do not approach' list. "
                    f"Client told it isn't proceeding and offered Bronze Membership.", by)
    transaction.on_commit(lambda: _emails().notify_not_proceeding_bronze(case))
    return case


# ---------------------------------------------------------------- E11: Bronze answer and closing

@transaction.atomic
def record_bronze_answer(case, *, accepted, by):
    case = _lock(case)
    _require_handler(by, case)
    if case.status != S.BRONZE_OFFERED:
        raise EliteError("No Bronze offer is waiting for an answer.")
    case.bronze_accepted = accepted
    case.status = S.CLOSED
    case.closed_at = timezone.now()
    case.save()
    if accepted:
        log_event(case, "Client accepted the Bronze offer and was sent the link to start the standard journey. Case closed.", by)
        transaction.on_commit(lambda: _emails().notify_bronze_start(case))
    else:
        log_event(case, "Client declined the Bronze offer. Case closed.", by)
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


def cases_to_wipe(now=None):
    """Closed (or declined) for 30 days, named person's details not yet wiped."""
    cutoff = (now or timezone.now()) - timedelta(days=WIPE_AFTER_DAYS)
    return EliteCase.objects.filter(closed_at__lt=cutoff, person_details_wiped_at__isnull=True)


def wipe_named_person(now=None):
    """
    Delete the named person's details and the documents that contain them (request form, acknowledgement,
    other). The NDA, Declaration and Indemnity Notice stay; the 'do not approach' fingerprint stays.
    """
    count = 0
    for case in cases_to_wipe(now):
        for document in case.documents.filter(kind__in=EliteDocument.NAMED_PERSON_KINDS):
            document.file.delete(save=False)
            document.delete()
        case.person_name_enc = case.person_contact_enc = case.person_email_enc = ""
        case.person_details_wiped_at = timezone.now()
        case.save()
        log_event(case, "Named person's details and related documents deleted (30 days after closing).")
        count += 1
    return count