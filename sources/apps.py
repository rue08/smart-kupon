import os
import sys

from django.apps import AppConfig
from django.conf import settings


class SourcesConfig(AppConfig):
    name = 'sources'

    def ready(self):
        # Only auto-start under `manage.py runserver` — not under migrate/
        # makemigrations/test/shell/etc, and not twice under the dev-server
        # autoreloader (RUN_MAIN is only set in the reloaded child process).
        # For a real deployment (gunicorn/uwsgi), run the scheduler as its
        # own process instead: `manage.py run_scheduler`.
        if not settings.RUN_SCHEDULER_ON_RUNSERVER:
            return
        if 'runserver' not in sys.argv:
            return
        if os.environ.get('RUN_MAIN') != 'true':
            return

        from . import scheduler
        scheduler.start()
