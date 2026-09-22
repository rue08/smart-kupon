import json
import urllib.error
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

IDENTITY_TOOLKIT_URL = 'https://identitytoolkit.googleapis.com/v1/accounts:{op}?key={key}'


class Command(BaseCommand):
    """Mint a real Firebase ID token for local testing, without a Flutter app.

    Calls the same public Identity Toolkit REST API the Firebase client SDKs
    use under the hood -- accounts:signUp to create a test user (once), then
    accounts:signInWithPassword to sign in and get back a real, verifiable
    ID token you can pass to /api/v1/auth/firebase/login or any other
    endpoint via `Authorization: Bearer <token>`.

    Usage:
        manage.py get_test_token test@example.com somepassword
        manage.py get_test_token test@example.com somepassword --create
    """

    help = 'Sign in (optionally sign up) a Firebase test user and print a real ID token.'

    def add_arguments(self, parser):
        parser.add_argument('email')
        parser.add_argument('password')
        parser.add_argument(
            '--create', action='store_true',
            help='Create the test user first via accounts:signUp before signing in.',
        )

    def handle(self, *args, **options):
        api_key = settings.FIREBASE_WEB_API_KEY
        if not api_key:
            raise CommandError('FIREBASE_WEB_API_KEY is not set in .env.')

        email, password = options['email'], options['password']

        if options['create']:
            self._call(api_key, 'signUp', email, password)
            self.stdout.write(self.style.SUCCESS(f'Created Firebase test user {email}'))

        result = self._call(api_key, 'signInWithPassword', email, password)
        self.stdout.write(self.style.SUCCESS('ID token:'))
        self.stdout.write(result['idToken'])

    def _call(self, api_key, op, email, password):
        url = IDENTITY_TOOLKIT_URL.format(op=op, key=api_key)
        body = json.dumps({
            'email': email,
            'password': password,
            'returnSecureToken': True,
        }).encode()
        request = urllib.request.Request(
            url, data=body, headers={'Content-Type': 'application/json'}
        )
        try:
            with urllib.request.urlopen(request) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = json.loads(exc.read()).get('error', {}).get('message', str(exc))
            raise CommandError(f'Firebase {op} failed: {detail}')
