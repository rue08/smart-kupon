import uuid

from django.db import models


class User(models.Model):
    """A registered SmartKupon account, identified by its Firebase auth reference.

    Firebase owns authentication (FR-1.1-FR-1.2); this row is the local profile
    the backend attaches coupons and source messages to. Not Django's auth User —
    request.user is populated by a custom Firebase-token authentication class.
    """

    user_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    auth_provider_ref = models.CharField(max_length=255, unique=True)  # Firebase UID
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_authenticated(self):
        return True

    def __str__(self):
        return self.email
