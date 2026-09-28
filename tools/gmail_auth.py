#!/usr/bin/env python3
"""One-time local OAuth flow for Gmail send-only access.

Usage from repository root:
    python -m pip install google-auth google-auth-oauthlib
    python tools/gmail_auth.py

By default this reuses client_secrets.json if you already created it for YouTube.
Override with GMAIL_CLIENT_SECRETS=/path/to/client_secrets.json if needed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def main() -> int:
    client_path = Path(os.environ.get("GMAIL_CLIENT_SECRETS", "client_secrets.json"))
    output_path = Path(os.environ.get("GMAIL_TOKEN_FILE", "gmail_token.json"))

    if not client_path.exists():
        raise SystemExit(f"Google OAuth client file not found: {client_path}")

    flow = InstalledAppFlow.from_client_secrets_file(str(client_path), SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Gmail send-only token saved to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
