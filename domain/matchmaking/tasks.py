from celery import shared_task

from domain.matchmaking.services.renewal_reminder_service import send_renewal_reminders


@shared_task
def membership_daily():
    """Once a day (Celery Beat): renewal reminders 60, 30 and 14 days before a membership ends."""
    return send_renewal_reminders()