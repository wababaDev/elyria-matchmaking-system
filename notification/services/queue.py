import logging

logger = logging.getLogger(__name__)


def enqueue(task, *args):
    """Queue a task. If Redis is unreachable, log it rather than break the request."""
    try:
        task.delay(*args)
    except Exception:
        logger.exception("Could not queue %s%s", task.name, args)