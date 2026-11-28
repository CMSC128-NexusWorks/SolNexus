"""Prove OAuth and inspect one synthetic Gmail thread without exposing its contents.

Run through the Compose gmail-spike service; see this directory's README.
"""

import argparse
import base64
import hashlib
import hmac
import os
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

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
CALLBACK_PORT = 8765


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Ignore unrelated localhost requests instead of ending the OAuth flow."""

    def do_GET(self):
        query = parse_qs(urlsplit(self.path).query)
        supplied_state = query.get("state", [""])
        valid_state = len(supplied_state) == 1 and hmac.compare_digest(
            supplied_state[0], self.server.expected_state
        )
        has_result = len(query.get("code", [])) == 1 or len(query.get("error", [])) == 1
        if not valid_state or not has_result:
            self.send_error(400, "This is not the current OAuth callback")
            return

        # Construct the URI ourselves: a hostile Host header must not change
        # the redirect URI passed to the OAuth library's token exchange.
        self.server.callback_uri = f"https://localhost:{CALLBACK_PORT}{self.path}"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Authorization received. Return to the terminal.")

    def log_message(self, format, *args):
        # The callback path can contain an authorization code; never log it.
        pass


def authorize_test_mailbox():
    """Wait for a matching local OAuth callback and exchange its code for tokens."""
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), [SCOPE])
    flow.redirect_uri = f"http://localhost:{CALLBACK_PORT}/"
    auth_url, state = flow.authorization_url(access_type="offline", prompt="consent")
    server = HTTPServer(("0.0.0.0", CALLBACK_PORT), OAuthCallbackHandler)
    server.expected_state = state
    server.callback_uri = None
    server.timeout = 1
    try:
        print("Open this URL in a browser on the Docker host:", auth_url, flush=True)
        deadline = time.monotonic() + 300
        while server.callback_uri is None and time.monotonic() < deadline:
            server.handle_request()
        if server.callback_uri is None:
            raise RuntimeError("Timed out waiting for OAuth consent")
        flow.fetch_token(authorization_response=server.callback_uri)
        return flow.credentials
    finally:
        server.server_close()


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
        # The human grants consent in a browser, then Google redirects to the
        # temporary callback published only on the Docker host's loopback port.
        creds = authorize_test_mailbox()
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
