"""
Elite Grade, Part 2b: the introduction (kept in the case; neither person becomes a member),
the feedback forms A/B/C, the daily job, and deletion that a person decides on.
"""
import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from domain.elite.forms import feedback_forms
from domain.elite.models import EliteCase, EliteDocument, EliteFeedback, EliteFeedbackNote
from domain.elite.models.elite_case import ABANDONED_AFTER_DAYS
from domain.elite.services.elite_service import (
    WIPE_AFTER_DAYS,
    EliteError,
    _emails,
    _lock,
    _require_handler,
    is_admin,
    log_event,
)

logger = logging.getLogger(__name__)
S = EliteCase.Status
SEND_AFTER_DAYS, REMIND_AFTER_DAYS, CLOSE_AFTER_DAYS = 3, 7, 14
REPLY_REMINDER_DAYS_BEFORE = 3
PREP_FIELDS = [
    ("coached_client", "Client coached on dating etiquette"),
    ("guidelines_client", "Guidelines read to the client"),
    ("coached_person", "Named person coached on dating etiquette"),
    ("guidelines_person", "Guidelines read to the named person"),
]


# ---------------------------------------------------------------- the introduction

@transaction.atomic
def schedule_introduction(case, *, intro_at, venue, video_link="", by):
    """Set (or change) the date, time and place. Both people are emailed the details each time."""
    case = _lock(case)
    _require_handler(by, case)
    if case.status != S.INTRODUCTION:
        raise EliteError("The introduction is set once the acknowledgement is signed.")
    if not venue.strip() and not video_link.strip():
        raise EliteError("Add a venue or a video link.")
    changed = case.intro_at is not None
    case.intro_at, case.intro_venue, case.intro_video_link = intro_at, venue.strip(), video_link.strip()
    case.intro_result = ""
    case.intro_alerts_sent_at = timezone.now()
    case.save()
    when = timezone.localtime(intro_at).strftime("%d %b %Y, %H:%M")
    log_event(case, f"Introduction {'moved to' if changed else 'set for'} {when}. Alerts emailed to both.", by)
    if not case.person_email:
        log_event(case, "No email for the named person: tell them the details another way.", by)
    transaction.on_commit(lambda: _emails().notify_intro_alerts(case, updated=changed))
    return case


@transaction.atomic
def save_preparation(case, *, ticks, by):
    case = _lock(case)
    _require_handler(by, case)
    if case.status not in (S.INTRODUCTION, S.INTRODUCED):
        raise EliteError("Preparation is recorded around the introduction.")
    done = []
    for field, label in PREP_FIELDS:
        value = bool(ticks.get(field))
        if value and not getattr(case, field):
            done.append(label)
        setattr(case, field, value)
    case.save()
    if done:
        log_event(case, "Preparation: " + "; ".join(done) + ".", by)
    return case


@transaction.atomic
def record_intro_result(case, *, result, on, who="", why="", by):
    """
    took_place: feedback forms A (client) and B (named person) are scheduled for 3 days later.
    cancelled / no_show: who and why are recorded; set a new date, or close the case.
    """
    case = _lock(case)
    _require_handler(by, case)
    if case.status != S.INTRODUCTION or case.intro_at is None:
        raise EliteError("Set the introduction first.")
    if on > timezone.localdate():
        raise EliteError("That date is in the future.")
    case.intro_result = result
    if result == EliteCase.IntroResult.TOOK_PLACE:
        case.intro_took_place_on = on
        case.status = S.INTRODUCED
        case.save()
        log_event(case, f"The introduction took place on {on:%d %b %Y}. Feedback forms go out on "
                        f"{on + timedelta(days=SEND_AFTER_DAYS):%d %b %Y}.", by)
        create_feedback(case, "A", on)
        if case.person_email:
            create_feedback(case, "B", on)
        else:
            log_event(case, "No email for the named person, so Form B can't be sent.", by)
    else:
        case.save()
        label = EliteCase.IntroResult(result).label
        log_event(case, f"Introduction {label.lower()} ({on:%d %b %Y}). Who: {who or 'not given'}. Why: {why or 'not given'}.", by)
    return case


@transaction.atomic
def close_case(case, *, outcome, note="", by):
    case = _lock(case)
    _require_handler(by, case)
    if case.status not in (S.INTRODUCTION, S.INTRODUCED):
        raise EliteError("This case can't be closed from here.")
    if case.status == S.INTRODUCTION and outcome != EliteCase.ClosingOutcome.DID_NOT_HAPPEN:
        raise EliteError("The introduction hasn't taken place, so close it as 'Introduction didn't happen'.")
    case.closing_outcome = outcome
    case.status = S.CLOSED
    case.closed_at = timezone.now()
    case.save()
    log_event(case, f"Case closed: {EliteCase.ClosingOutcome(outcome).label}." + (f" {note.strip()}" if note.strip() else ""), by)
    return case


@transaction.atomic
def extend_reply_window(case, *, days, reason, by):
    """For emergencies: travel, bereavement and so on. The reason goes on the timeline."""
    case = _lock(case)
    _require_handler(by, case)
    if case.status != S.OUTREACH_SENT:
        raise EliteError("There's no reply window to extend.")
    if not reason.strip():
        raise EliteError("Give a reason for the extension.")
    base = max(case.reply_due_on, timezone.localdate())
    case.reply_due_on = base + timedelta(days=days)
    case.reply_reminder_sent = case.reply_ended_notice_sent = False
    case.save()
    log_event(case, f"Reply window extended by {days} days, to {case.reply_due_on:%d %b %Y}. Reason: {reason.strip()}", by)
    return case


# ---------------------------------------------------------------- feedback forms

def create_feedback(case, form, base_date):
    """Schedule a form: sent on day 3, reminded on day 7, closes on day 14 (from base_date)."""
    feedback, created = EliteFeedback.objects.get_or_create(
        case=case, form=form,
        defaults={
            "send_on": base_date + timedelta(days=SEND_AFTER_DAYS),
            "remind_on": base_date + timedelta(days=REMIND_AFTER_DAYS),
            "closes_on": base_date + timedelta(days=CLOSE_AFTER_DAYS),
        },
    )
    if created:
        log_event(case, f"Form {form} scheduled for {feedback.send_on:%d %b %Y}.")
    return feedback


@transaction.atomic
def extend_feedback(feedback, *, days, by):
    """Reopen or extend a feedback link. If it was never sent, it goes out with the next daily run."""
    feedback = EliteFeedback.objects.select_for_update().select_related("case").get(pk=feedback.pk)
    _require_handler(by, feedback.case)
    if feedback.completed_at:
        raise EliteError("This form has already been completed.")
    feedback.closes_on = max(feedback.closes_on, timezone.localdate()) + timedelta(days=days)
    feedback.save(update_fields=["closes_on"])
    log_event(feedback.case, f"Form {feedback.form} link extended to {feedback.closes_on:%d %b %Y}.", by)
    return feedback


@transaction.atomic
def add_feedback_note(feedback, *, text, by):
    if not is_admin(by):
        raise EliteError("Only Admin can add notes to feedback.")
    if not text.strip():
        raise EliteError("Write the note first.")
    return EliteFeedbackNote.objects.create(feedback=feedback, by=by, text=text.strip())


def feedback_for_token(token):
    return EliteFeedback.objects.select_related("case").filter(token=token).first()


@transaction.atomic
def submit_feedback(token, data):
    """
    The person's answers, saved once and never edited. Red flags and referral leads email Admin.
    Returns (feedback, errors). errors is empty on success.
    """
    feedback = EliteFeedback.objects.select_for_update().select_related("case").filter(token=token).first()
    if feedback is None or not feedback.sent_at:
        raise EliteError("This link isn't valid.")
    if feedback.completed_at:
        raise EliteError("Thank you, this form has already been completed.")
    if timezone.localdate() > feedback.closes_on:
        raise EliteError("This form has closed. If you'd still like to share feedback, simply reply to our email.")

    answers, errors = feedback_forms.clean_answers(feedback.form, data)
    if errors:
        return feedback, errors

    feedback.answers = answers
    feedback.completed_at = timezone.now()
    feedback.completed_by = "named person" if feedback.form == "B" else "client"
    feedback.red_flag_reasons = feedback_forms.red_flag_reasons(feedback.form, answers)
    feedback.red_flag = bool(feedback.red_flag_reasons)
    feedback.referral_lead = feedback_forms.is_referral_lead(feedback.form, answers)
    feedback.save()

    log_event(feedback.case, f"Form {feedback.form} completed by the {feedback.completed_by}.")
    if feedback.red_flag:
        log_event(feedback.case, f"RED FLAG on Form {feedback.form}: " + "; ".join(feedback.red_flag_reasons) + ". Admin notified.")
        transaction.on_commit(lambda: _emails().notify_feedback_alert(feedback, "red_flag"))
    if feedback.referral_lead:
        log_event(feedback.case, f"Referral lead from Form {feedback.form}. Admin notified.")
        transaction.on_commit(lambda: _emails().notify_feedback_alert(feedback, "lead"))
    return feedback, {}


# ---------------------------------------------------------------- deletion (a person decides)

def due_for_deletion(now=None):
    """
    What Admin should delete now:
    - abandoned applications (never confirmed, or no documents recorded, for 30 days)
    - closed or declined cases 30+ days old whose named-person details are still stored
    """
    now = now or timezone.now()
    cutoff = now - timedelta(days=ABANDONED_AFTER_DAYS)
    abandoned = EliteCase.objects.filter(
        Q(status=S.AWAITING_EMAIL, verify_sent_at__lt=cutoff)
        | Q(status=S.AWAITING_DOCUMENTS, email_verified_at__lt=cutoff)
    )
    closed = EliteCase.objects.filter(
        closed_at__lt=now - timedelta(days=WIPE_AFTER_DAYS), person_details_wiped_at__isnull=True,
    ).filter(Q(person_name_enc__gt="") | Q(documents__kind__in=EliteDocument.NAMED_PERSON_KINDS)).distinct()
    return abandoned, closed


@transaction.atomic
def delete_now(case, *, by):
    """Admin's 'Delete now'. Abandoned application: removed entirely. Closed case: named-person details wiped."""
    if not is_admin(by):
        raise EliteError("Only Admin can delete Elite records.")
    abandoned, closed = due_for_deletion()
    if abandoned.filter(pk=case.pk).exists():
        reference = case.reference
        for document in case.documents.all():
            document.file.delete(save=False)
        case.delete()
        return f"Application {reference} deleted."
    if closed.filter(pk=case.pk).exists():
        case = _lock(case)
        for document in case.documents.filter(kind__in=EliteDocument.NAMED_PERSON_KINDS):
            document.file.delete(save=False)
            document.delete()
        case.person_name_enc = case.person_contact_enc = case.person_email_enc = ""
        case.person_details_wiped_at = timezone.now()
        case.save()
        log_event(case, "Named person's details and related documents deleted.", by)
        return f"Named person's details deleted from {case.reference}."
    raise EliteError("This case isn't due for deletion yet.")


# ---------------------------------------------------------------- the daily job

def daily_run(today=None):
    """
    Run once a day by Celery Beat (domain/elite/tasks.py). Only SENDS things: feedback forms on day 3,
    reminders on day 7, reminders to the Case Handler about reply windows, and on Mondays a reminder to
    Admin about anything due for deletion. It never deletes anything.
    """
    today = today or timezone.localdate()
    emails = _emails()
    summary = {"sent": 0, "reminded": 0, "handler": 0, "deletion": 0, "failed": 0}

    def send(func, *args):
        """One failed email mustn't stop the rest; it's simply tried again tomorrow."""
        try:
            func(*args)
            return True
        except Exception:
            logger.exception("Elite daily run: %s%s failed", func.__name__, args)
            summary["failed"] += 1
            return False

    for feedback in EliteFeedback.objects.filter(sent_at__isnull=True, send_on__lte=today, closes_on__gte=today):
        if not send(emails.deliver_feedback_email, feedback, "invite"):
            continue
        feedback.sent_at = timezone.now()
        feedback.save(update_fields=["sent_at"])
        log_event(feedback.case, f"Form {feedback.form} emailed.")
        summary["sent"] += 1

    for feedback in EliteFeedback.objects.filter(
        sent_at__isnull=False, reminded_at__isnull=True, completed_at__isnull=True,
        remind_on__lte=today, closes_on__gte=today,
    ):
        if not send(emails.deliver_feedback_email, feedback, "reminder"):
            continue
        feedback.reminded_at = timezone.now()
        feedback.save(update_fields=["reminded_at"])
        log_event(feedback.case, f"Form {feedback.form} reminder emailed.")
        summary["reminded"] += 1

    open_outreach = EliteCase.objects.filter(status=S.OUTREACH_SENT, handler__isnull=False)
    for case in open_outreach.filter(reply_reminder_sent=False, reply_due_on__lte=today + timedelta(days=REPLY_REMINDER_DAYS_BEFORE),
                                     reply_due_on__gte=today):
        if not send(emails.deliver_handler_reminder, case, "reply_soon"):
            continue
        case.reply_reminder_sent = True
        case.save(update_fields=["reply_reminder_sent"])
        summary["handler"] += 1
    for case in open_outreach.filter(reply_ended_notice_sent=False, reply_due_on__lt=today):
        if not send(emails.deliver_handler_reminder, case, "reply_ended"):
            continue
        case.reply_ended_notice_sent = True
        case.save(update_fields=["reply_ended_notice_sent"])
        summary["handler"] += 1

    if today.weekday() == 0:  # Mondays
        abandoned, closed = due_for_deletion()
        count = abandoned.count() + closed.count()
        if count and send(emails.deliver_deletion_reminder, count):
            summary["deletion"] = count
    return summary