import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from dateutil import parser as dateutil_parser
from django.utils import timezone

from . import merchants

WEEKDAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

# "code SAVE20", "use code: SAVE20", "coupon code SAVE20" -- the reliable case.
_CODE_KEYWORD = re.compile(
    r'\bcoupon\s+code[:\s]+([A-Z0-9]{4,15})\b|\b(?:use\s+)?code[:\s]+([A-Z0-9]{4,15})\b',
    re.IGNORECASE,
)
# Fallback: a bare alphanumeric token that mixes letters and digits, e.g. "SAVE20".
_CODE_STANDALONE = re.compile(r'(?=[A-Za-z0-9]{4,15}\b)(?=[A-Za-z0-9]*[A-Za-z])(?=[A-Za-z0-9]*[0-9])[A-Za-z0-9]{4,15}\b')

_DISCOUNT = re.compile(
    r'\bflat\s+(?:rs\.?\s*)?\d+\s*%?\s*(?:off)?\b'
    r'|\bupto\s+(?:rs\.?\s*)?\d+\s*%?\s*off\b'
    r'|\b\d+\s*%\s*(?:off|discount)?\b',
    re.IGNORECASE,
)

_RELATIVE_WEEKDAY = re.compile(
    r'\b(?:valid\s+)?(?:till|until|through)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
    re.IGNORECASE,
)
_RELATIVE_DAYS = re.compile(r'\bexpires?\s+in\s+(\d+)\s+days?\b', re.IGNORECASE)
_RELATIVE_TOMORROW = re.compile(r'\b(?:till|until)\s+tomorrow\b', re.IGNORECASE)
_ABSOLUTE_DATE_HINT = re.compile(
    r'\b(?:valid\s+(?:till|until|through)|expires?(?:\s+on)?|till|until)\s+'
    r'([0-9]{1,2}[/-][0-9]{1,2}(?:[/-][0-9]{2,4})?|[0-9]{1,2}(?:st|nd|rd|th)?\s+\w+(?:\s+[0-9]{4})?|\w+\s+[0-9]{1,2}(?:,?\s+[0-9]{4})?)',
    re.IGNORECASE,
)


@dataclass
class ExtractionResult:
    coupon_code: str
    discount_value: str
    expiry_date: date | None
    merchant_name: str | None
    category_name: str | None
    is_low_confidence: bool


def extract(raw_text):
    """Regex-first extraction (FR-3.1/3.2/3.4).

    Returns None when no coupon code is found at all -- the message isn't a
    coupon, so the caller (coupons.pipeline) discards it per FR-2.5 rather
    than storing an empty record. NLP fallback (FR-3.3) is deferred -- Low
    priority/optional per the SRS; is_low_confidence already surfaces what
    regex alone can't resolve, for the user to confirm or discard.
    """
    if not raw_text:
        return None

    code = _extract_code(raw_text)
    if not code:
        return None

    discount = _extract_discount(raw_text)
    expiry = _extract_expiry(raw_text)
    merchant_name, category_name = merchants.resolve_merchant(raw_text)

    return ExtractionResult(
        coupon_code=code,
        discount_value=discount or '',
        expiry_date=expiry,
        merchant_name=merchant_name,
        category_name=category_name,
        is_low_confidence=not merchant_name or expiry is None,
    )


def _extract_code(text):
    match = _CODE_KEYWORD.search(text)
    if match:
        return (match.group(1) or match.group(2)).upper()
    match = _CODE_STANDALONE.search(text)
    return match.group(0).upper() if match else None


def _extract_discount(text):
    match = _DISCOUNT.search(text)
    return match.group(0).strip() if match else None


def _extract_expiry(text):
    match = _RELATIVE_WEEKDAY.search(text)
    if match:
        return _next_weekday(WEEKDAYS.index(match.group(1).lower()))

    match = _RELATIVE_DAYS.search(text)
    if match:
        return timezone.localdate() + timedelta(days=int(match.group(1)))

    if _RELATIVE_TOMORROW.search(text):
        return timezone.localdate() + timedelta(days=1)

    match = _ABSOLUTE_DATE_HINT.search(text)
    if match:
        return _parse_absolute_date(match.group(1))

    return None


def _next_weekday(target_weekday):
    """Next occurrence of target_weekday, always in the future (never today)."""
    today = timezone.localdate()
    days_ahead = (target_weekday - today.weekday()) % 7 or 7
    return today + timedelta(days=days_ahead)


def _parse_absolute_date(text):
    today = timezone.localdate()
    try:
        parsed = dateutil_parser.parse(text, dayfirst=True, fuzzy=True, default=datetime(today.year, today.month, today.day))
    except (ValueError, OverflowError):
        return None
    return parsed.date()
