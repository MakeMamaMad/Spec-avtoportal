from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import requests


DEFAULT_API_VERSION = os.getenv("INSTAGRAM_API_VERSION", "v26.0").strip()
DEFAULT_GRAPH_BASE = os.getenv("INSTAGRAM_GRAPH_BASE", "https://graph.facebook.com").rstrip("/")


class InstagramPublishError(RuntimeError):
    pass


def _graph_url(path: str, *, api_version: str = DEFAULT_API_VERSION, graph_base: str = DEFAULT_GRAPH_BASE) -> str:
    version = api_version.strip("/")
    return f"{graph_base}/{version}/{path.lstrip('/')}"


def _json(response: requests.Response, label: str) -> dict[str, Any]:
    try:
        data = response.json()
    except Exception as exc:
        raise InstagramPublishError(
            f"{label}: HTTP {response.status_code}, invalid JSON"
        ) from exc

    if not response.ok or data.get("error"):
        error = data.get("error") or data
        raise InstagramPublishError(f"{label}: HTTP {response.status_code}: {error}")
    return data


def publish_reel(
    video_path: str | Path,
    *,
    caption: str,
    ig_user_id: str,
    access_token: str,
    share_to_feed: bool = True,
    api_version: str = DEFAULT_API_VERSION,
    graph_base: str = DEFAULT_GRAPH_BASE,
    poll_interval: float = 4.0,
    timeout_seconds: float = 360.0,
) -> dict[str, str]:
    """Publish a local MP4 as an Instagram Reel using Meta's resumable upload flow."""
    video_path = Path(video_path)
    if not video_path.exists():
        raise InstagramPublishError(f"video not found: {video_path}")
    if not ig_user_id.strip() or not access_token.strip():
        raise InstagramPublishError("INSTAGRAM_IG_USER_ID / INSTAGRAM_ACCESS_TOKEN are required")

    create_url = _graph_url(
        f"{ig_user_id}/media",
        api_version=api_version,
        graph_base=graph_base,
    )
    create = requests.post(
        create_url,
        params={
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": caption,
            "share_to_feed": "true" if share_to_feed else "false",
            "access_token": access_token,
        },
        timeout=45,
    )
    created = _json(create, "Instagram create container")
    container_id = str(created.get("id") or "").strip()
    upload_uri = str(created.get("uri") or "").strip()
    if not container_id or not upload_uri:
        raise InstagramPublishError(f"Instagram container response missing id/uri: {created}")

    size = video_path.stat().st_size
    with video_path.open("rb") as handle:
        upload = requests.post(
            upload_uri,
            data=handle,
            headers={
                "Authorization": f"OAuth {access_token}",
                "offset": "0",
                "file_size": str(size),
                "Content-Type": "application/octet-stream",
            },
            timeout=180,
        )
    _json(upload, "Instagram upload binary")

    status_url = _graph_url(
        container_id,
        api_version=api_version,
        graph_base=graph_base,
    )
    deadline = time.monotonic() + timeout_seconds
    last_status = ""
    while time.monotonic() < deadline:
        status_response = requests.get(
            status_url,
            params={
                "fields": "status_code,status",
                "access_token": access_token,
            },
            timeout=30,
        )
        status_data = _json(status_response, "Instagram container status")
        status_code = str(status_data.get("status_code") or "").upper()
        last_status = str(status_data.get("status") or status_code)
        if status_code == "FINISHED":
            break
        if status_code in {"ERROR", "EXPIRED"}:
            raise InstagramPublishError(f"Instagram processing failed: {last_status}")
        time.sleep(poll_interval)
    else:
        raise InstagramPublishError(f"Instagram processing timeout: {last_status}")

    publish_url = _graph_url(
        f"{ig_user_id}/media_publish",
        api_version=api_version,
        graph_base=graph_base,
    )
    published = _json(
        requests.post(
            publish_url,
            params={
                "creation_id": container_id,
                "access_token": access_token,
            },
            timeout=45,
        ),
        "Instagram media_publish",
    )
    media_id = str(published.get("id") or "").strip()
    if not media_id:
        raise InstagramPublishError(f"Instagram publish response missing media id: {published}")

    permalink = ""
    try:
        detail = _json(
            requests.get(
                _graph_url(media_id, api_version=api_version, graph_base=graph_base),
                params={"fields": "permalink", "access_token": access_token},
                timeout=30,
            ),
            "Instagram permalink",
        )
        permalink = str(detail.get("permalink") or "")
    except Exception as exc:
        print(f"[instagram] permalink unavailable: {exc}")

    return {
        "platform": "instagram",
        "status": "published",
        "container_id": container_id,
        "media_id": media_id,
        "permalink": permalink,
    }
