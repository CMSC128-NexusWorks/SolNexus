"""Opaque page tokens and page slicing for list endpoints, as Google's `pageToken` / `nextPageToken`.

A token encodes the offset of the next page in base64url, so clients treat it as opaque (as they must with Google)
while the mock stays stateless between requests. A token the mock did not issue is a 400, as with Google.

Known simplification: offsets are positions in a list computed per request, so if the data changes between two page
requests an item can shift across a page boundary. Google's real paging is consistent; the master never relies on
cross-page consistency (it dedups and replays safely), so this does not hide bugs that matter here.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Sequence

from google_errors import GoogleApiError

TOKEN_PREFIX = "offset:"


def encode_page_token(offset: int) -> str:
    return base64.urlsafe_b64encode(f"{TOKEN_PREFIX}{offset}".encode()).decode().rstrip("=")


def decode_page_token(token: str | None) -> int:
    """The offset a page token points at; 0 for no token. Anything not issued by encode_page_token is a 400."""
    if not token:
        return 0
    try:
        text = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode()
        if text.startswith(TOKEN_PREFIX):
            offset = int(text.removeprefix(TOKEN_PREFIX))
            if offset >= 0:
                return offset
    except (binascii.Error, UnicodeDecodeError, ValueError):
        pass
    raise GoogleApiError(400, "invalid", "Invalid pageToken value.")


def slice_page[T](items: Sequence[T], page_token: str | None, page_size: int) -> tuple[list[T], str | None]:
    """One page of items and the token for the next page (None on the last page, so clients know to stop)."""
    start = decode_page_token(page_token)
    page = list(items[start : start + page_size])
    end = start + page_size
    return page, (encode_page_token(end) if end < len(items) else None)
