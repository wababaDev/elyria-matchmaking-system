import logging
from smtplib import SMTPException

from celery import shared_task
from django.contrib.auth import get_user_model

from domain.matchmaking.models import Client, Consultation, ConsultationRequest, Enquiry
from notification.services import consultation_emails, enquiry_emails, member_emails, profile_emails ,staff_emails

logger = logging.getLogger(__name__)

# Network/SMTP problems retry after ~1, 2, 4, 8, 16, 32 minutes (capped at 1h), then give up
EMAIL_RETRY = {
    "autoretry_for": (SMTPException, OSError),
    "retry_backoff": 60,
    "retry_backoff_max": 60 * 60,
    "retry_jitter": True,
    "max_retries": 6,
}


def _get(model, pk):
    obj = model.objects.filter(pk=pk).first()
    if obj is None:
        logger.warning("%s %s no longer exists; email skipped", model.__name__, pk)
    return obj


@shared_task(**EMAIL_RETRY)
def send_payment_instructions_email(consultation_request_id):
    if obj := _get(ConsultationRequest, consultation_request_id):
        consultation_emails.deliver_payment_instructions(obj)


@shared_task(**EMAIL_RETRY)
def send_team_alert_email(consultation_request_id):
    if obj := _get(ConsultationRequest, consultation_request_id):
        consultation_emails.deliver_team_alert(obj)


@shared_task(**EMAIL_RETRY)
def send_consultation_booked_email(consultation_id, rebooked=False):
    if obj := _get(Consultation, consultation_id):
        consultation_emails.deliver_consultation_booked(obj, rebooked)


@shared_task(**EMAIL_RETRY)
def send_member_welcome_email(client_id):
    if obj := _get(Client, client_id):
        member_emails.deliver_member_welcome(obj)


@shared_task(**EMAIL_RETRY)
def send_sign_in_link_email(client_id):
    if obj := _get(Client, client_id):
        member_emails.deliver_sign_in_link(obj)


@shared_task(**EMAIL_RETRY)
def send_staff_invite_email(user_id):
    if obj := _get(get_user_model(), user_id):
        staff_emails.deliver_staff_invite(obj)


@shared_task(**EMAIL_RETRY)
def send_enquiry_alert_email(enquiry_id):
    if obj := _get(Enquiry, enquiry_id):
        enquiry_emails.deliver_enquiry_alert(obj)

@shared_task(**EMAIL_RETRY)
def send_profile_completed_email(client_id):
    if obj := _get(Client, client_id):
        profile_emails.deliver_profile_completed(obj)


@shared_task(**EMAIL_RETRY)
def send_profile_updated_email(client_id, sections):
    if obj := _get(Client, client_id):
        profile_emails.deliver_profile_updated(obj, sections)

@shared_task(**EMAIL_RETRY)
def send_sign_in_email_changed_email(client_id, old_email):
    if obj := _get(Client, client_id):
        member_emails.deliver_sign_in_email_changed(obj, old_email)