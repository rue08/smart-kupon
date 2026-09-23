from .dedup import build_dedup_key
from .extraction import extract
from .models import Category, Coupon, CouponCategory, Merchant


def process_message(message):
    """Extract, dedupe, and store a Coupon from a SourceMessage's raw_ref (M3/M4).

    Always clears message.raw_ref when done, whether or not a coupon was
    found -- FR-2.5 minimal retention. Safe to call more than once on the
    same message: once raw_ref is cleared, extract() has nothing left to
    work with and this is a no-op.
    """
    if not message.raw_ref:
        return None

    result = extract(message.raw_ref)
    coupon = _store_coupon(message, result) if result is not None else None

    message.raw_ref = None
    message.save(update_fields=['raw_ref'])
    return coupon


def _store_coupon(message, result):
    merchant = None
    if result.merchant_name:
        merchant, _ = Merchant.objects.get_or_create(name=result.merchant_name)

    dedup_key = build_dedup_key(result.merchant_name, result.coupon_code)

    coupon, created = Coupon.objects.get_or_create(
        user=message.user,
        dedup_key=dedup_key,
        defaults={
            'message': message,
            'merchant': merchant,
            'coupon_code': result.coupon_code,
            'discount_value': result.discount_value,
            'expiry_date': result.expiry_date,
            'is_low_confidence': result.is_low_confidence,
        },
    )

    if created:
        coupon.status = coupon.compute_status()
        coupon.save(update_fields=['status'])
        if result.category_name:
            category, _ = Category.objects.get_or_create(name=result.category_name)
            CouponCategory.objects.get_or_create(coupon=coupon, category=category)
        return coupon

    _merge(coupon, result)
    return coupon


def _merge(coupon, result):
    """FR-4.2 'merge or discard': fill gaps on the existing record, keep the
    original `message` (first-seen wins) and never overwrite populated data.
    """
    changed_fields = []
    if not coupon.expiry_date and result.expiry_date:
        coupon.expiry_date = result.expiry_date
        changed_fields.append('expiry_date')
    if not coupon.discount_value and result.discount_value:
        coupon.discount_value = result.discount_value
        changed_fields.append('discount_value')
    if coupon.is_low_confidence and not result.is_low_confidence:
        coupon.is_low_confidence = False
        changed_fields.append('is_low_confidence')

    if 'expiry_date' in changed_fields:
        coupon.status = coupon.compute_status()
        changed_fields.append('status')

    if changed_fields:
        coupon.save(update_fields=changed_fields)
