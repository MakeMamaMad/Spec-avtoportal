from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import requests


API_BASE = "https://open.tiktokapis.com"


class TikTokPublishError(RuntimeError):
    pass


def _json(response: requests.Response, label: str) -> dict[str, Any]:
    try:
        data = response.json()
    except Exception as exc:
        raise TikTokPublishError(f"{label}: HTTP {response.status_code}, invalid JSON") from exc

    error = data.get("error") if isinstance(data, dict) else None
    if not response.ok or (isinstance(error, dict) and error.get("code") not in (None, "", "ok")):
        raise TikTokPublishError(f"{label}: HTTP {response.status_code}: {error or data}")
    return data


def _chunk_plan(size: int) -> tuple[int, int]:
    """Return TikTok-compatible (chunk_size, total_chunk_count)."""
    if size <= 0:
        raise TikTokPublishError("video is empty")
    max_chunk = 64 * 1024 * 1024
    preferred = 32 * 1024 * 1024

    if size <= max_chunk:
        return size, 1

    chunk_size = preferred
    total = max(1, size // chunk_size)
    if total > 1000:
        chunk_size = math.ceil(size / 1000)
        total = size // chunk_size
    return chunk_size, total


def _upload_chunks(video_path: Path, upload_url: str, chunk_size: int, total_chunks: int) -> None:
    size = video_path.stat().st_size
    offset = 0

    with video_path.open("rb") as handle:
        for index in range(total_chunks):
            if index == total_chunks - 1:
                length = size - offset
            else:
                length = chunk_size

            payload = handle.read(length)
            if len(payload) != length:
                raise TikTokPublishError(
                    f"TikTok chunk read mismatch at {index + 1}/{total_chunks}: "
                    f"expected {length}, got {len(payload)}"
                )

            end = offset + length - 1
            response = requests.put(
                upload_url,
                data=payload,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(length),
                    "Content-Range": f"bytes {offset}-{end}/{size}",
                },
                timeout=240,
            )
            expected = 201 if index == total_chunks - 1 else 206
            if response.status_code != expected:
                raise TikTokPublishError(
                    f"TikTok upload chunk {index + 1}/{total_chunks}: "
                    f"HTTP {response.status_code}: {response.text[:800]}"
                )
            offset += length


def upload_video_draft(
    video_path: str | Path,
    *,
    access_token: str,
) -> dict[str, str]:
    """Upload a video to the creator's TikTok inbox/drafts for final review and posting."""
    video_path = Path(video_path)
    if not video_path.exists():
        raise TikTokPublishError(f"video not found: {video_path}")
    if not access_token.strip():
        raise TikTokPublishError("TIKTOK_ACCESS_TOKEN is required")

    size = video_path.stat().st_size
    chunk_size, total_chunks = _chunk_plan(size)

    response = requests.post(
        f"{API_BASE}/v2/post/publish/inbox/video/init/",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json={
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunks,
            }
        },
        timeout=45,
    )
    data = _json(response, "TikTok draft init")
    payload = data.get("data") or {}
    publish_id = str(payload.get("publish_id") or "").strip()
    upload_url = str(payload.get("upload_url") or "").strip()
    if not publish_id or not upload_url:
        raise TikTokPublishError(f"TikTok init response missing publish_id/upload_url: {data}")

    _upload_chunks(video_path, upload_url, chunk_size, total_chunks)

    return {
        "platform": "tiktok",
        "status": "draft_uploaded",
        "publish_id": publish_id,
    }


def fetch_publish_status(*, access_token: str, publish_id: str) -> dict[str, Any]:
    response = requests.post(
        f"{API_BASE}/v2/post/publish/status/fetch/",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json={"publish_id": publish_id},
        timeout=30,
    )
    return _json(response, "TikTok publish status")
