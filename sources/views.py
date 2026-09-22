import hashlib

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User

from . import crypto, gmail_oauth, gmail_sync
from .models import GmailCredential, SourceMessage
from .serializers import SMSSyncRequestSerializer


class GmailAuthorizeView(APIView):
    """GET /api/v1/sources/gmail/authorize -- returns the Google consent URL (FR-2.1).

    The Flutter app opens this URL in a browser/webview; the user consents
    on Google's own screen, then Google redirects to GmailCallbackView.
    """

    def get(self, request):
        try:
            gmail_oauth.ensure_configured()
        except gmail_oauth.GmailNotConfiguredError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        state = gmail_oauth.make_state(request.user.user_id)
        flow = gmail_oauth.build_flow(state=state)
        authorization_url, _ = flow.authorization_url(
            access_type='offline',       # needed to get a refresh_token
            include_granted_scopes='true',
            prompt='consent',
        )
        return Response({'authorization_url': authorization_url})


class GmailCallbackView(APIView):
    """GET /api/v1/sources/gmail/callback -- handles Google's OAuth redirect.

    This is a plain browser redirect from Google, not an authenticated API
    call, so it carries no Authorization header -- the user is identified via
    the signed `state` param instead (see gmail_oauth.make_state/read_state).
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        code = request.query_params.get('code')
        state = request.query_params.get('state')
        if not code or not state:
            return Response({'detail': 'Missing code or state.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user_id = gmail_oauth.read_state(state)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            gmail_oauth.ensure_configured()
        except gmail_oauth.GmailNotConfiguredError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        flow = gmail_oauth.build_flow(state=state)
        try:
            flow.fetch_token(code=code)
        except Exception as exc:
            return Response(
                {'detail': f'Failed to exchange authorization code: {exc}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        creds = flow.credentials
        user = get_object_or_404(User, user_id=user_id)

        credential, _ = GmailCredential.objects.update_or_create(
            user=user,
            defaults={
                'access_token_encrypted': crypto.encrypt(creds.token),
                'refresh_token_encrypted': crypto.encrypt(creds.refresh_token),
                'token_expiry': creds.expiry,
                'scope': ' '.join(creds.scopes or []),
            },
        )
        return Response({'detail': 'Gmail connected.'})


class GmailSyncTriggerView(APIView):
    """POST /api/v1/sync/gmail/trigger -- manually run a Gmail sync for the current user (FR-2.3)."""

    def post(self, request):
        try:
            request.user.gmail_credential
        except GmailCredential.DoesNotExist:
            return Response(
                {'detail': 'Gmail is not connected for this account yet.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            created = gmail_sync.sync_user_gmail(request.user)
        except gmail_sync.GmailSyncError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response({'synced_messages': created})


class SMSSyncView(APIView):
    """POST /api/v1/sources/sms/sync -- accept a batch of on-device SMS text (FR-2.2, FR-2.4).

    Android grants SMS read permission to the installed app, not a server
    (§3.1), so reading the device inbox is entirely the Flutter app's job.
    This endpoint just receives what it already read and stores each message
    as a SourceMessage -- the same shape the Gmail path produces, ready for
    the extraction engine (M3).
    """

    def post(self, request):
        serializer = SMSSyncRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        created = 0
        for item in serializer.validated_data['messages']:
            external_id = item['external_id'] or _sms_dedup_key(item['sender'], item['body'])
            raw_text = f"From: {item['sender']}\n{item['body']}" if item['sender'] else item['body']

            _, was_created = SourceMessage.objects.get_or_create(
                user=request.user,
                source_type=SourceMessage.SourceType.SMS,
                external_id=external_id,
                defaults={'raw_ref': raw_text},
            )
            if was_created:
                created += 1

        return Response(
            {'received': len(serializer.validated_data['messages']), 'created': created},
            status=status.HTTP_201_CREATED,
        )


def _sms_dedup_key(sender, body):
    """Fallback idempotency key when the client doesn't supply external_id."""
    return hashlib.sha256(f'{sender}|{body}'.encode()).hexdigest()
