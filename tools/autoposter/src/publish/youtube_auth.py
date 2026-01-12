"""One-time local OAuth flow to create youtube_token.json.

Run locally (NOT on GitHub Actions):
    python -m src.publish.youtube_auth
"""
import json
from google_auth_oauthlib.flow import InstalledAppFlow

from ..config import cfg

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def main():
    flow = InstalledAppFlow.from_client_secrets_file(cfg.YOUTUBE_CLIENT_SECRETS, SCOPES)
    creds = flow.run_local_server(port=0)
    data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }
    with open(cfg.YOUTUBE_TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[youtube] token saved to {cfg.YOUTUBE_TOKEN_FILE}")

if __name__ == "__main__":
    main()
