from django.conf import settings
from django.core import signing
from google_auth_oauthlib.flow import Flow

GMAIL_READONLY_SCOPE = 'https://www.googleapis.com/auth/gmail.readonly'

# Signed (not encrypted) — only needs tamper-resistance, not secrecy, and lets
# the OAuth callback (a plain browser redirect from Google, no Bearer header)
# recover which user started the flow without a server-side session store.
_STATE_SALT = 'sources.gmail_oauth.state'
_STATE_MAX_AGE_SECONDS = 600  # time allowed to complete Google's consent screen


class GmailNotConfiguredError(Exception):
    """Raised when Google OAuth client credentials aren't set yet."""


def ensure_configured():
    missing = [
        name for name, value in (
            ('GOOGLE_OAUTH_CLIENT_ID', settings.GOOGLE_OAUTH_CLIENT_ID),
            ('GOOGLE_OAUTH_CLIENT_SECRET', settings.GOOGLE_OAUTH_CLIENT_SECRET),
            ('GOOGLE_OAUTH_REDIRECT_URI', settings.GOOGLE_OAUTH_REDIRECT_URI),
        ) if not value
    ]
    if missing:
        raise GmailNotConfiguredError(
            f'Gmail OAuth is not configured yet: missing {", ".join(missing)} in .env.'
        )


def make_state(user_id):
    return signing.dumps({'user_id': str(user_id)}, salt=_STATE_SALT)


def read_state(state):
    try:
        data = signing.loads(state, salt=_STATE_SALT, max_age=_STATE_MAX_AGE_SECONDS)
    except signing.BadSignature:
        raise ValueError('OAuth state is invalid or has expired; please restart the authorization flow.')
    return data['user_id']


def build_flow(state=None):
    client_config = {
        'web': {
            'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
            'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET,
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
            'redirect_uris': [settings.GOOGLE_OAUTH_REDIRECT_URI],
        }
    }
    return Flow.from_client_config(
        client_config,
        scopes=[GMAIL_READONLY_SCOPE],
        redirect_uri=settings.GOOGLE_OAUTH_REDIRECT_URI,
        state=state,
    )
