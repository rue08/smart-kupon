import base64
import html
import logging
import re

from django.utils import timezone
from google.auth.transport.requests import Request as GoogleAuthRequest
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .models import GmailCredential, SourceMessage

logger = logging.getLogger(__name__)

PROMOTIONS_LABEL_ID = 'CATEGORY_PROMOTIONS'
MAX_MESSAGES_PER_SYNC = 50


class GmailSyncError(Exception):
    """Raised when the sync as a whole can't proceed (auth, API-down, bad cursor)."""


def sync_user_gmail(user):
    """Fetch new promotional Gmail messages for `user`, store as SourceMessage rows.

    Uses Gmail's history.list for incremental sync once a cursor exists;
    falls back to a fresh messages.list (+ a new cursor from getProfile) on
    first sync, or if the stored cursor has aged out (Gmail retains history
    for ~7 days -- history.list 404s past that, per Gmail API docs).

    A single message that fails to fetch/decode is logged and skipped, not
    treated as a sync failure (NFR Reliability: one bad message must not
    interrupt the rest of the batch). Coupon extraction (M3) is a separate
    step; this only lands raw text (FR-2.3).
    """
    try:
        credential = user.gmail_credential
    except GmailCredential.DoesNotExist:
        raise GmailSyncError('Gmail is not connected for this user.')

    creds = credential.to_google_credentials()
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleAuthRequest())
        credential.update_from_google_credentials(creds)

    try:
        service = build('gmail', 'v1', credentials=creds, cache_discovery=False)
    except Exception as exc:
        raise GmailSyncError(f'Could not build Gmail client: {exc}')

    message_ids, new_history_id = None, None
    if credential.last_history_id:
        message_ids, new_history_id = _incremental_message_ids(service, credential.last_history_id)
    if message_ids is None:  # no cursor yet, or it expired
        message_ids, new_history_id = _full_message_ids(service)

    created = 0
    for message_id in message_ids:
        was_created = _store_message(service, user, message_id)
        if was_created:
            created += 1

    credential.last_history_id = new_history_id
    credential.last_synced_at = timezone.now()
    credential.save(update_fields=['last_history_id', 'last_synced_at'])
    return created


def _incremental_message_ids(service, start_history_id):
    """Returns (message_ids, new_history_id), or (None, None) if the cursor is stale."""
    message_ids = []
    page_token = None
    response = {}
    try:
        while True:
            response = service.users().history().list(
                userId='me',
                startHistoryId=start_history_id,
                historyTypes=['messageAdded'],
                labelId=PROMOTIONS_LABEL_ID,
                pageToken=page_token,
            ).execute()
            for record in response.get('history', []):
                for added in record.get('messagesAdded', []):
                    message_ids.append(added['message']['id'])
            page_token = response.get('nextPageToken')
            if not page_token:
                break
    except HttpError as exc:
        if exc.resp.status == 404:
            logger.warning('Gmail history cursor expired; falling back to full list')
            return None, None
        raise GmailSyncError(f'Gmail history.list failed: {exc}')

    return message_ids, response.get('historyId', start_history_id)


def _full_message_ids(service):
    try:
        response = service.users().messages().list(
            userId='me', q='category:promotions', maxResults=MAX_MESSAGES_PER_SYNC,
        ).execute()
        profile = service.users().getProfile(userId='me').execute()
    except HttpError as exc:
        raise GmailSyncError(f'Gmail messages.list failed: {exc}')

    message_ids = [m['id'] for m in response.get('messages', [])]
    return message_ids, profile['historyId']


def _store_message(service, user, message_id):
    """Fetch and store one message; returns True if newly created, False if skipped/existing."""
    if SourceMessage.objects.filter(
        user=user, source_type=SourceMessage.SourceType.GMAIL, external_id=message_id,
    ).exists():
        return False

    try:
        full = service.users().messages().get(userId='me', id=message_id, format='full').execute()
    except HttpError as exc:
        logger.warning('Failed to fetch Gmail message %s for user %s: %s', message_id, user.user_id, exc)
        return False

    text = _extract_plain_text(full.get('payload', {}))
    SourceMessage.objects.create(
        user=user,
        source_type=SourceMessage.SourceType.GMAIL,
        raw_ref=text,
        external_id=message_id,
    )
    return True


def _extract_plain_text(payload):
    plain, html_body = _walk_parts(payload)
    if plain:
        return plain
    if html_body:
        return html.unescape(re.sub(r'<[^>]+>', ' ', html_body))
    return ''


def _walk_parts(part):
    """Recursively search a Gmail message payload for text/plain and text/html bodies."""
    plain = html_body = None
    mime_type = part.get('mimeType', '')
    data = part.get('body', {}).get('data')

    if mime_type == 'text/plain' and data:
        plain = _decode_body(data)
    elif mime_type == 'text/html' and data:
        html_body = _decode_body(data)

    for sub_part in part.get('parts', []):
        sub_plain, sub_html = _walk_parts(sub_part)
        plain = plain or sub_plain
        html_body = html_body or sub_html

    return plain, html_body


def _decode_body(data):
    padded = data + '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode('utf-8', errors='replace')
