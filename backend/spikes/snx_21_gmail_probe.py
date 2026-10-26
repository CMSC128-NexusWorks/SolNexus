"""Prove OAuth and inspect one synthetic Gmail thread without exposing its contents.

Run through the Compose gmail-spike service; see this directory's README.
"""

import argparse
import base64
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


# Message bodies are needed for this spike; metadata-only access cannot provide them.
SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
# Docker mounts only this ignored directory into the probe container. These paths
# are environment-driven so the image never contains credentials or user tokens.
SECRET_DIR = Path(os.environ.get("SNX_21_SECRET_DIR", "/run/snx-21-secrets"))
CLIENT_FILE = SECRET_DIR / "gmail-oauth-client.json"
TOKEN_FILE = SECRET_DIR / "gmail-token.json"


def credentials(force_refresh=False):
    """Authorize the test mailbox and optionally prove the refresh-token exchange."""
    if not CLIENT_FILE.is_file():
        raise RuntimeError("OAuth client JSON is missing from the mounted secrets directory")
    # A saved token avoids prompting the mailbox owner again on ordinary reruns.
    creds = (
        Credentials.from_authorized_user_file(str(TOKEN_FILE), [SCOPE])
        if TOKEN_FILE.is_file()
        else None
    )
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        # Desktop OAuth uses a temporary local callback; the human grants consent in a browser.
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), [SCOPE])
        # The container listens on all interfaces, while the browser redirects to
        # localhost on the host's published port. Compose binds that port to loopback.
        creds = flow.run_local_server(
            host="localhost", bind_addr="0.0.0.0", port=8765, open_browser=False
        )
    if not creds.refresh_token:
        raise RuntimeError("No refresh token was issued; consent must request offline access")
    if force_refresh:
        # Refresh immediately so the spike proves more than a one-time access token.
        creds.refresh(Request())
        print("refresh_succeeded: true")
    # Create the token file with owner-only permissions before any token bytes are written.
    TOKEN_FILE.touch(mode=0o600, exist_ok=True)
    TOKEN_FILE.chmod(0o600)
    TOKEN_FILE.write_text(creds.to_json())
    return creds


def has_text(part):
    """Check nested MIME parts for nonempty plain text without displaying the body."""
    if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
        data = part["body"]["data"]
        # Gmail sends body bytes as URL-safe base64, sometimes without padding.
        return bool(base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).strip())
    return any(has_text(child) for child in part.get("parts", []))


def fingerprint(value):
    """Expose a stable comparison value without printing Google's raw identifier."""
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def main():
    """Read one matching thread and print only redacted evidence for the spike."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True, help="Gmail search query for one synthetic thread")
    parser.add_argument("--verify-refresh", action="store_true", help="Force a refresh-token exchange")
    args = parser.parse_args()

    service = build("gmail", "v1", credentials=credentials(args.verify_refresh), cache_discovery=False)
    # Bound the search so an ambiguous query cannot silently select the wrong thread.
    result = service.users().threads().list(userId="me", q=args.query, maxResults=2).execute()
    threads = result.get("threads", [])
    if len(threads) != 1 or result.get("nextPageToken"):
        raise RuntimeError(f"Expected exactly one matching thread; found {len(threads)} or more")

    thread = service.users().threads().get(
        userId="me", id=threads[0]["id"], format="full"
    ).execute()
    messages = thread.get("messages", [])
    print("thread_fingerprint:", fingerprint(thread["id"]))
    print("message_count:", len(messages))
    for message in messages:
        labels = set(message.get("labelIds", []))
        # These labels describe the authorized mailbox's view of each message.
        direction = "outbound" if "SENT" in labels else "inbound" if "INBOX" in labels else "unknown"
        millis = message.get("internalDate")
        # Gmail's internalDate is epoch milliseconds; retain it as a UTC event time.
        event_at = datetime.fromtimestamp(int(millis) / 1000, timezone.utc).isoformat() if millis else "missing"
        print(
            "message:",
            "id_fingerprint=" + fingerprint(message["id"]),
            "direction=" + direction,
            "event_at=" + event_at,
            "text_present=" + str(has_text(message.get("payload", {}))).lower(),
        )


if __name__ == "__main__":
    main()
