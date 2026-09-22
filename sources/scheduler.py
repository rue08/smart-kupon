import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from django.conf import settings
from django_apscheduler.jobstores import DjangoJobStore
from django_apscheduler.util import close_old_connections

logger = logging.getLogger(__name__)

_scheduler = None


@close_old_connections  # background-thread DB connections go stale between runs otherwise
def run_gmail_sync_job():
    from .gmail_sync import GmailSyncError, sync_user_gmail
    from .models import GmailCredential

    for credential in GmailCredential.objects.select_related('user').all():
        try:
            created = sync_user_gmail(credential.user)
            logger.info('Gmail sync: user %s, %s new message(s)', credential.user_id, created)
        except GmailSyncError:
            logger.exception('Gmail sync failed for user %s', credential.user_id)


def start():
    """Start the in-process APScheduler, backed by a DB jobstore for persistence.

    Idempotent — calling it twice (e.g. accidentally) just returns the
    existing scheduler rather than starting a second one.
    """
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    scheduler = BackgroundScheduler(timezone=str(settings.TIME_ZONE))
    scheduler.add_jobstore(DjangoJobStore(), 'default')
    scheduler.add_job(
        run_gmail_sync_job,
        trigger=IntervalTrigger(minutes=settings.GMAIL_SYNC_INTERVAL_MINUTES),
        id='gmail_sync',
        max_instances=1,
        replace_existing=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info('APScheduler started — gmail_sync every %s minute(s)', settings.GMAIL_SYNC_INTERVAL_MINUTES)
    return scheduler
