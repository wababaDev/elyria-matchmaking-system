"""
Elite Grade, Part 2b: the introduction (kept in the case; neither person becomes a member),
feedback (asked by the Case Handler on a call and typed in), notes, the daily job, and deletion that a person
decides on.
"""
import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from domain.elite.forms import feedback_forms
from domain.elite.models import EliteCase, EliteDocument, EliteFeedback
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
    took_place: the Case Handler then asks both the feedback questions (Forms A and B) and records them.
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
        log_event(case, f"The introduction took place on {on:%d %b %Y}.", by)
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


# ---------------------------------------------------------------- feedback (asked offline, typed in here)

def feedback_forms_for(case):
    """Which of the client's forms apply: A and B after an introduction, C if it closed without one."""
    if case.intro_took_place_on:
        return ["A", "B"]
    if case.outcome or case.closing_outcome == EliteCase.ClosingOutcome.DID_NOT_HAPPEN:
        return ["C"]
    return []


def feedback_cards(case):
    """Everything the Feedback tab needs, one card per form."""
    saved = {f.form: f for f in case.feedback.select_related("recorded_by")}
    return [
        {
            "form": form,
            "title": feedback_forms.TITLES[form],
            "record": saved.get(form),
            "questions": feedback_forms.for_display(form, saved[form].answers if form in saved else {}),
        }
        for form in feedback_forms_for(case)
    ]


@transaction.atomic
def save_feedback(case, *, form, data, by):
    """
    Save (or correct) the answers to one form. Red flags and referral leads go on the timeline so Admin
    sees them. Returns the EliteFeedback.
    """
    case = _lock(case)
    _require_handler(by, case)
    if form not in feedback_forms_for(case):
        raise EliteError("That feedback form doesn't apply to this case yet.")
    answers, errors = feedback_forms.clean_answers(form, data)
    if errors:
        raise EliteError(next(iter(errors.values())))
    if not answers:
        raise EliteError("Nothing to save: answer at least one question.")

    feedback = EliteFeedback.objects.filter(case=case, form=form).first()
    was_flagged, was_lead = (feedback.red_flag, feedback.referral_lead) if feedback else (False, False)
    created = feedback is None
    feedback = feedback or EliteFeedback(case=case, form=form, recorded_by=by)
    feedback.recorded_by = by  # who saved it last; the timeline keeps every save
    feedback.answers = answers
    feedback.red_flag_reasons = feedback_forms.red_flag_reasons(form, answers)
    feedback.red_flag = bool(feedback.red_flag_reasons)
    feedback.referral_lead = feedback_forms.is_referral_lead(form, answers)
    feedback.save()

    log_event(case, f"Form {form} {'recorded' if created else 'updated'} ({len(answers)} answers).", by)
    if feedback.red_flag and not was_flagged:
        log_event(case, f"CONCERN · Red flag on Form {form}: " + "; ".join(feedback.red_flag_reasons) + ".", by)
    if feedback.referral_lead and not was_lead:
        log_event(case, f"Referral lead from Form {form}: rated Elite Grade highly and agreed to be contacted.", by)
    return feedback


# ---------------------------------------------------------------- notes

NOTE_ABOUT = [
    ("feedback_client", "Feedback from the client"),
    ("feedback_person", "Feedback from the named person"),
    ("note", "Note"),
]


@transaction.atomic
def add_note(case, *, about, text, concern=False, by):
    """
    Feedback is gathered by the Case Handler offline (a call or a message); only what matters is written
    down here. The note goes on the append-only timeline. A concern is marked so Admin sees it.
    """
    case = _lock(case)
    _require_handler(by, case)
    if not text.strip():
        raise EliteError("Write the note first.")
    label = dict(NOTE_ABOUT)[about]
    log_event(case, ("CONCERN · " if concern else "") + f"{label}: {text.strip()}", by)
    return case


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
    Run once a day by Celery Beat (domain/elite/tasks.py). Only SENDS reminders: to the Case Handler about
    reply windows, and on Mondays to Admin about anything due for deletion. It never deletes anything.
    """
    today = today or timezone.localdate()
    emails = _emails()
    summary = {"handler": 0, "deletion": 0, "failed": 0}

    def send(func, *args):
        """One failed email mustn't stop the rest; it's simply tried again tomorrow."""
        try:
            func(*args)
            return True
        except Exception:
            logger.exception("Elite daily run: %s%s failed", func.__name__, args)
            summary["failed"] += 1
            return False

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