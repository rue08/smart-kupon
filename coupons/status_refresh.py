from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import Coupon


def refresh_statuses():
    """Bulk-align stored `status` with each coupon's expiry_date (FR-6.1).

    Three UPDATE statements regardless of table size -- lets the list/filter
    endpoints (coupons.views) query `status` directly in SQL instead of
    computing it per-row on every request. Mirrors the thresholds in
    Coupon.compute_status(); keep both in sync if either changes. Never
    touches `used` coupons (a persisted manual state, not date-derived).

    Run on a schedule via sources.scheduler (COUPON_STATUS_REFRESH_MINUTES).
    A single coupon's status is also self-healed on direct read (see
    coupons.views' detail view), so this job's interval only bounds
    staleness for list-level filtering, not single-coupon lookups.
    """
    today = timezone.localdate()
    window_end = today + timedelta(days=settings.COUPON_EXPIRING_SOON_DAYS)
    base = Coupon.objects.exclude(status=Coupon.Status.USED)

    base.filter(expiry_date__lt=today).exclude(
        status=Coupon.Status.EXPIRED
    ).update(status=Coupon.Status.EXPIRED)

    base.filter(expiry_date__gte=today, expiry_date__lte=window_end).exclude(
        status=Coupon.Status.EXPIRING_SOON
    ).update(status=Coupon.Status.EXPIRING_SOON)

    base.filter(Q(expiry_date__gt=window_end) | Q(expiry_date__isnull=True)).exclude(
        status=Coupon.Status.ACTIVE
    ).update(status=Coupon.Status.ACTIVE)
