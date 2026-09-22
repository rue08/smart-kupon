import uuid

from django.conf import settings as django_settings
from django.db import models

from accounts.models import User


class SourceMessage(models.Model):
    """Raw SMS/Gmail content a coupon was extracted from.

    Kept only as long as needed for processing — raw_ref is cleared once
    extraction completes (FR-2.5 minimal retention).
    """

    class SourceType(models.TextChoices):
        SMS = 'sms', 'SMS'
        GMAIL = 'gmail', 'Gmail'

    message_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='source_messages')
    source_type = models.CharField(max_length=10, choices=SourceType.choices)
    raw_ref = models.TextField(null=True, blank=True)
    collected_at = models.DateTimeField(auto_now_add=True)

    # Gmail message id (or a future channel's native id) — not in the report's
    # logical schema, added so sync can be idempotent at the DB level (NFR
    # Reliability: "re-processing the same message shall not create duplicates").
    external_id = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'source_type', 'external_id'],
                condition=models.Q(external_id__isnull=False),
                name='unique_user_source_external_id',
            ),
        ]

    def __str__(self):
        return f'{self.source_type}:{self.message_id}'


class GmailCredential(models.Model):
    """A user's authorized, encrypted Gmail OAuth tokens (FR-2.1, NFR Security).

    access/refresh tokens are stored via Fernet symmetric encryption
    (sources.crypto) rather than in plaintext, per NFR §2.2.2.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='gmail_credential')
    access_token_encrypted = models.TextField()
    refresh_token_encrypted = models.TextField()
    token_expiry = models.DateTimeField()
    scope = models.CharField(max_length=255, blank=True)

    # Gmail's incremental-sync cursor (users.history.list); cheaper and more
    # precise than re-querying by date on every poll.
    last_history_id = models.CharField(max_length=64, null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    connected_at = models.DateTimeField(auto_now_add=True)

    def to_google_credentials(self):
        from google.oauth2.credentials import Credentials

        from . import crypto

        return Credentials(
            token=crypto.decrypt(self.access_token_encrypted),
            refresh_token=crypto.decrypt(self.refresh_token_encrypted),
            token_uri='https://oauth2.googleapis.com/token',
            client_id=django_settings.GOOGLE_OAUTH_CLIENT_ID,
            client_secret=django_settings.GOOGLE_OAUTH_CLIENT_SECRET,
            scopes=self.scope.split() if self.scope else None,
            expiry=self.token_expiry,
        )

    def update_from_google_credentials(self, creds):
        from . import crypto

        self.access_token_encrypted = crypto.encrypt(creds.token)
        if creds.refresh_token:
            self.refresh_token_encrypted = crypto.encrypt(creds.refresh_token)
        if creds.expiry:
            self.token_expiry = creds.expiry
        self.save(update_fields=['access_token_encrypted', 'refresh_token_encrypted', 'token_expiry'])

    def __str__(self):
        return f'GmailCredential({self.user_id})'
