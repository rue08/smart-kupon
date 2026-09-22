from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from . import firebase
from .models import User

BEARER_KEYWORD = 'Bearer'


def extract_bearer_token(request):
    """Pull the token out of `Authorization: Bearer <token>`, or None if absent."""
    header = request.headers.get('Authorization', '')
    if not header:
        return None

    parts = header.split()
    if len(parts) != 2 or parts[0] != BEARER_KEYWORD:
        raise AuthenticationFailed('Authorization header must be "Bearer <token>".')
    return parts[1]


class FirebaseAuthentication(BaseAuthentication):
    """Verifies a Firebase ID token and resolves it to a local accounts.User.

    Expects `Authorization: Bearer <firebase-id-token>`. Does NOT provision a
    new local user on the fly -- a valid token from a not-yet-provisioned
    Firebase account is rejected, pointing the client at the login endpoint
    (accounts.views.FirebaseLoginView), which is the only place a local User
    row gets created.
    """

    def authenticate(self, request):
        token = extract_bearer_token(request)
        if token is None:
            return None

        try:
            decoded = firebase.verify_id_token(token)
        except firebase.TokenVerificationError as exc:
            raise AuthenticationFailed(str(exc))

        uid = decoded['uid']
        try:
            user = User.objects.get(auth_provider_ref=uid)
        except User.DoesNotExist:
            raise AuthenticationFailed(
                'No SmartKupon account for this Firebase user yet. Call the login endpoint first.'
            )

        return (user, decoded)

    def authenticate_header(self, request):
        # Presence of this makes DRF respond 401 (not 403) when auth is missing/invalid.
        return 'Bearer'
