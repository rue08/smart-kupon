import re

_NON_ALNUM = re.compile(r'[^a-z0-9]+')


def normalize(value):
    """Lowercase, strip non-alphanumerics, collapse whitespace/punctuation.

    Used for both merchant name and coupon code so "Amazon" / "amazon.in" /
    "AMAZON" and "SAVE20" / "save-20" converge to the same dedup key.
    """
    if not value:
        return ''
    return _NON_ALNUM.sub('', value.lower())


def build_dedup_key(merchant_name, coupon_code):
    """(user, dedup_key) is uniquely constrained on Coupon -- see models.py."""
    return f'{normalize(merchant_name)}:{normalize(coupon_code)}'
