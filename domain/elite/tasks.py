import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def elite_daily():
    """
    Once a day (Celery Beat, see CELERY_BEAT_SCHEDULE): remind Case Handlers about reply windows, and on Mondays remind Admin about deletions. Never deletes.
    """
    from domain.elite.services.introduction_service import daily_run

    summary = daily_run()
    logger.info("Elite daily run: %s", summary)
    return summary