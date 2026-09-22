import firebase_admin
from django.conf import settings
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials

_app = None


class TokenVerificationError(Exception):
    """Raised with a human-readable, client-safe reason when a token can't be verified."""


def get_firebase_app():
    """Lazily initialize and return the Firebase Admin app.

    Deferred until first use (rather than at Django startup) so `manage.py
    check`/`runserver` still work before FIREBASE_SERVICE_ACCOUNT_KEY_PATH is
    configured — only requests that actually need token verification fail,
    and they fail with TokenVerificationError rather than an unhandled 500.
    """
    global _app
    if _app is not None:
        return _app

    key_path = settings.FIREBASE_SERVICE_ACCOUNT_KEY_PATH
    if not key_path:
        raise TokenVerificationError(
            'Firebase is not configured on this server yet (FIREBASE_SERVICE_ACCOUNT_KEY_PATH unset).'
        )

    try:
        cred = credentials.Certificate(key_path)
        _app = firebase_admin.initialize_app(cred)
    except FileNotFoundError:
        raise TokenVerificationError(
            f'Firebase service-account file not found at "{key_path}".'
        )
    except ValueError as exc:
        raise TokenVerificationError(f'Firebase service-account file is invalid: {exc}')

    return _app


def verify_id_token(token):
    """Verify a Firebase ID token and return its decoded claims.

    Raises TokenVerificationError with a specific, client-safe message on any
    failure (server not configured, expired, invalid signature, wrong
    project, cert fetch failure, malformed token).
    """
    app = get_firebase_app()  # raises TokenVerificationError if unconfigured
    try:
        return firebase_auth.verify_id_token(token, app=app)
    except firebase_auth.ExpiredIdTokenError:
        raise TokenVerificationError('Firebase ID token has expired.')
    except firebase_auth.InvalidIdTokenError:
        raise TokenVerificationError('Firebase ID token is invalid.')
    except firebase_auth.CertificateFetchError:
        raise TokenVerificationError('Could not verify token (certificate fetch failed).')
    except ValueError:
        raise TokenVerificationError('Firebase ID token is malformed.')
