import json
from pathlib import Path
from typing import List, Optional

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from ..config import cfg

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def _load_creds() -> Credentials:
    p = Path(cfg.YOUTUBE_TOKEN_FILE)
    if not p.exists():
        raise RuntimeError(f"YouTube token file not found: {p}. Run locally: python -m src.publish.youtube_auth")
    data = json.loads(p.read_text(encoding="utf-8"))
    creds = Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=data.get("scopes") or SCOPES,
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        data["token"] = creds.token
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return creds

def upload_video(file_path: str, title: str, description: str, tags: Optional[List[str]] = None, privacy_status: str = "public") -> str:
    creds = _load_creds()
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(file_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = req.execute()
    return resp.get("id", "")
