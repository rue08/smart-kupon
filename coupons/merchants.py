import re

# Canonical name -> default browsing category (FR-4.3 auto-assignment).
# Keys are lowercase-alpha only, matched as substrings against alpha-only
# tokens pulled from the raw text -- tolerant of DLT SMS sender-ID noise
# ("AD-AMAZNIN") and email domains ("noreply@amazon.in") alike.
KNOWN_MERCHANTS = {
    'amazon': ('Amazon', 'Shopping'),
    'flipkart': ('Flipkart', 'Shopping'),
    'myntra': ('Myntra', 'Fashion'),
    'ajio': ('Ajio', 'Fashion'),
    'nykaa': ('Nykaa', 'Beauty'),
    'swiggy': ('Swiggy', 'Food'),
    'zomato': ('Zomato', 'Food'),
    'bigbasket': ('BigBasket', 'Grocery'),
    'zepto': ('Zepto', 'Grocery'),
    'blinkit': ('Blinkit', 'Grocery'),
}

_FROM_LINE = re.compile(r'^From:\s*(.+)$', re.MULTILINE)
_ALPHA_RUN = re.compile(r'[a-z]+')


def resolve_merchant(raw_text):
    """Returns (canonical_name, category_name) or (None, None).

    Tries the "From:" line first -- the SMS sender ID / Gmail From header,
    prepended to raw_ref by sources.views/gmail_sync -- then falls back to
    scanning the whole message body, both against KNOWN_MERCHANTS.
    """
    header_match = _FROM_LINE.search(raw_text)
    if header_match:
        found = _match_known(header_match.group(1))
        if found:
            return found

    return _match_known(raw_text) or (None, None)


def _match_known(text):
    tokens = _ALPHA_RUN.findall(text.lower())
    for alias, (canonical, category) in KNOWN_MERCHANTS.items():
        if any(alias in token for token in tokens):
            return canonical, category
    return None
