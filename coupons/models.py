import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from accounts.models import User
from sources.models import SourceMessage


class Merchant(models.Model):
    """A normalized merchant name, referenced by many coupons.

    Extraction resolves variants ("Amazon", "amazon.in", "AMAZON") to one
    canonical row so merchant-based search/filter (FR-5.2, FR-5.3) is complete.
    """

    merchant_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name


class Category(models.Model):
    """A user-facing grouping label, related to coupons many-to-many."""

    category_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name


class Coupon(models.Model):
    """A structured, deduplicated coupon record — the system's central entity."""

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        EXPIRING_SOON = 'expiring_soon', 'Expiring soon'
        EXPIRED = 'expired', 'Expired'
        USED = 'used', 'Used'

    coupon_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='coupons')
    # Nullable: a coupon may be added manually rather than extracted from a message.
    message = models.ForeignKey(
        SourceMessage, on_delete=models.SET_NULL, null=True, blank=True, related_name='coupons'
    )
    merchant = models.ForeignKey(
        Merchant, on_delete=models.SET_NULL, null=True, blank=True, related_name='coupons'
    )
    categories = models.ManyToManyField(Category, through='CouponCategory', related_name='coupons')

    coupon_code = models.CharField(max_length=100)
    discount_value = models.CharField(max_length=100, blank=True)  # as extracted, e.g. "20%", "FLAT 50"
    expiry_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    # Set by the extraction engine when a coupon code was found but merchant
    # and/or expiry couldn't be resolved confidently (FR-3.4) — surfaced to
    # the user to confirm or discard rather than silently trusted.
    is_low_confidence = models.BooleanField(default=False)

    # normalize(merchant) + normalize(code); (user, dedup_key) enforces FR-4.2.
    dedup_key = models.CharField(max_length=255)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'dedup_key'], name='unique_user_dedup_key'),
        ]
        indexes = [
            models.Index(fields=['user', 'dedup_key']),
        ]

    def compute_status(self):
        """The status this coupon should have right now, per FR-6.1.

        `used` is a persisted manual fact and always wins. The other three
        states are derived from expiry_date -- the single definition callers
        (coupons.pipeline, coupons.views detail self-heal,
        coupons.status_refresh's bulk job) all rely on to stay consistent.
        """
        if self.status == self.Status.USED:
            return self.Status.USED
        if self.expiry_date is None:
            return self.Status.ACTIVE
        today = timezone.localdate()
        if self.expiry_date < today:
            return self.Status.EXPIRED
        if self.expiry_date <= today + timedelta(days=settings.COUPON_EXPIRING_SOON_DAYS):
            return self.Status.EXPIRING_SOON
        return self.Status.ACTIVE

    def __str__(self):
        return f'{self.coupon_code} ({self.merchant})'


class CouponCategory(models.Model):
    """Junction table for the Coupon <-> Category many-to-many relationship."""

    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['coupon', 'category'], name='unique_coupon_category'),
        ]
