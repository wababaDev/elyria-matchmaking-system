from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from domain.matchmaking.models import Enquiry
from domain.matchmaking.services.consultation_request_service import InvalidTransitionError
from notification.services.enquiry_emails import notify_new_enquiry

ENQUIRY_FILTERS = [("open", "Open"), ("answered", "Answered"), ("all", "All")]


def submit_enquiry(enquiry):
    enquiry.status = Enquiry.Status.OPEN
    enquiry.save()
    transaction.on_commit(lambda: notify_new_enquiry(enquiry))
    return enquiry


def filter_enquiries(status="open", query=""):
    qs = Enquiry.objects.select_related("tier", "answered_by")
    if status in Enquiry.Status.values:
        qs = qs.filter(status=status)
    query = query.strip()
    if query:
        qs = qs.filter(Q(first_name__icontains=query) | Q(contact__icontains=query) | Q(question__icontains=query))
    return qs


@transaction.atomic
def mark_answered(enquiry, *, note, by):
    enquiry = Enquiry.objects.select_for_update().get(pk=enquiry.pk)
    if enquiry.status == Enquiry.Status.ANSWERED:
        raise InvalidTransitionError("This enquiry is already marked as answered.")
    enquiry.status = Enquiry.Status.ANSWERED
    enquiry.answered_at = timezone.now()
    enquiry.answered_by = by
    enquiry.response_note = note.strip()
    enquiry.save(update_fields=["status", "answered_at", "answered_by", "response_note", "updated_at"])
    return enquiry