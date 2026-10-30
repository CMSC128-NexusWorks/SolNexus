"""Opaque, query-bound keyset cursors. No offsets that shift after a concurrent insert."""

import base64
import hashlib
import json
from app.errors import ApiError


def scope_key(scope):
    """Bind a continuation token to its filters so it cannot silently change query meaning."""
    return hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()[:24]


def encode_cursor(scope, keys):
    """Serialize stable tie-break values without exposing an offset susceptible to inserts."""
    return base64.urlsafe_b64encode(
        json.dumps([scope_key(scope), keys]).encode()
    ).decode()


def decode_cursor(value, scope, width):
    """Reject malformed, cross-query or wrong-width tokens before constructing bound SQL."""
    if value is None:
        return None
    try:
        if len(value) > 4096:
            raise ValueError()
        signature, keys = json.loads(
            base64.b64decode(value, altchars=b"-_", validate=True)
        )
        if (
            signature != scope_key(scope)
            or not isinstance(keys, list)
            or len(keys) != width
            or not all(isinstance(k, str) for k in keys)
        ):
            raise ValueError()
        return keys
    except (ValueError, TypeError, UnicodeError):
        raise ApiError(422, "invalid_cursor", "Invalid cursor for this query") from None
