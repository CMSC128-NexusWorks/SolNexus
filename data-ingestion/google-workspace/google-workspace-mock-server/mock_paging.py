"""Opaque tokens (page tokens, sync tokens) and page slicing for list endpoints.

Google's `pageToken`, `nextPageToken` and `syncToken` are opaque strings: clients must store and send them back, never
build or parse them. The mock encodes a small JSON payload in base64url, tagged with a `kind`, so it stays stateless
between requests and can tell its own tokens apart. A token it did not issue (or of the wrong kind) is rejected.

Known simplification for Gmail: its page tokens hold only an offset into a list computed per request, so if the data
changes between two page requests an item can shift across a page boundary. Google's real paging is consistent; the
master never relies on cross-page consistency (it dedups and replays safely), so this does not hide bugs that matter.
The Calendar route avoids the issue by pinning every page to a snapshot position (routes_calendar).
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Sequence

from google_errors import GoogleApiError

GMAIL_PAGE_TOKEN_KIND = "page"


def encode_opaque_token(kind: str, payload: dict[str, int]) -> str:
    """base64url(JSON) without padding, e.g. a page token {"kind": "page", "offset": 100}."""
    text = json.dumps({"kind": kind, **payload}, separators=(",", ":"), sort_keys=True)
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def decode_opaque_token(token: str, kind: str) -> dict[str, int] | None:
    """The payload of a token this mock issued with this kind, or None for anything else (garbage, other kind)."""
    try:
        data = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode())
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    if not isinstance(data, dict) or data.pop("kind", None) != kind:
        return None
    if not all(isinstance(value, int) for value in data.values()):
        return None
    return data


def encode_page_token(offset: int) -> str:
    return encode_opaque_token(GMAIL_PAGE_TOKEN_KIND, {"offset": offset})


def decode_page_token(token: str | None) -> int:
    """The offset a Gmail page token points at; 0 for no token. Anything the mock did not issue is a 400."""
    if not token:
        return 0
    payload = decode_opaque_token(token, GMAIL_PAGE_TOKEN_KIND)
    if payload is None or payload.get("offset", -1) < 0:
        raise GoogleApiError(400, "invalid", "Invalid pageToken value.")
    return payload["offset"]


def slice_page[T](items: Sequence[T], page_token: str | None, page_size: int) -> tuple[list[T], str | None]:
    """One page of items and the token for the next page (None on the last page, so clients know to stop)."""
    start = decode_page_token(page_token)
    page = list(items[start : start + page_size])
    end = start + page_size
    return page, (encode_page_token(end) if end < len(items) else None)
