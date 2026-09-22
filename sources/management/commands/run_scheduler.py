import time

from django.core.management.base import BaseCommand

from sources import scheduler


class Command(BaseCommand):
    """Run the Gmail-sync scheduler as its own foreground process.

    Use this instead of the runserver auto-start (see sources.apps) for a
    real deployment: run it as one long-lived process alongside gunicorn/
    uwsgi, rather than relying on the dev server starting it in-process.
    """

    help = 'Run the APScheduler-based Gmail sync job as a standalone process.'

    def handle(self, *args, **options):
        scheduler.start()
        self.stdout.write(self.style.SUCCESS('Scheduler running. Press Ctrl+C to stop.'))
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            self.stdout.write('Stopping scheduler.')
