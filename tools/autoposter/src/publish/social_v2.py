from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .instagram import publish_reel
from .tiktok import upload_video_draft
from .youtube import upload_video


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "out_v2"
SOCIAL_STATE_PATH = ROOT / "state" / "social_v2.json"
V2_STATE_PATH = ROOT / "state" / "v2.json"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_social_state() -> dict[str, Any]:
    state = _read_json(SOCIAL_STATE_PATH, {})
    if not isinstance(state, dict):
        state = {}
    state.setdefault("schema", 1)
    state.setdefault("content", {})
    return state


def _platform_done(entry: dict[str, Any], platform: str) -> bool:
    record = (entry.get("platforms") or {}).get(platform) or {}
    return record.get("status") in {"published", "draft_uploaded"}


def _record(
    state: dict[str, Any],
    content_key: str,
    *,
    title: str,
    platform: str,
    result: dict[str, Any],
) -> None:
    content = state.setdefault("content", {})
    entry = content.setdefault(content_key, {
        "title": title,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "platforms": {},
    })
    entry["title"] = title
    entry["updated_at"] = datetime.now(timezone.utc).isoformat()
    entry.setdefault("platforms", {})[platform] = {
        **result,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(SOCIAL_STATE_PATH, state)


def _mark_v2_used(content_key: str, slug: str, title: str) -> None:
    state = _read_json(V2_STATE_PATH, {})
    if not isinstance(state, dict):
        state = {}
    state.setdefault("schema", 1)
    used = [str(x) for x in state.get("used", []) if str(x)]
    if content_key not in used:
        used.append(content_key)
    state["used"] = used[-2000:]

    renders = state.get("renders", [])
    if not isinstance(renders, list):
        renders = []
    if not any(str(x.get("content_key")) == content_key for x in renders if isinstance(x, dict)):
        renders.append({
            "content_key": content_key,
            "slug": slug,
            "title": title,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "format": "social-v2",
        })
    state["renders"] = renders[-500:]
    _write_json(V2_STATE_PATH, state)


def _configured_platforms(raw: str) -> list[str]:
    allowed = {"youtube", "instagram", "tiktok"}
    values = []
    for value in raw.split(","):
        name = value.strip().lower()
        if name and name in allowed and name not in values:
            values.append(name)
    return values


def _caption(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def publish_all(*, dry_run: bool = False) -> dict[str, Any]:
    manifest = _read_json(OUT_DIR / "manifest.json", {})
    board = _read_json(OUT_DIR / "scene_plan.json", {})
    if not isinstance(manifest, dict) or not manifest.get("content_key"):
        raise RuntimeError("Short v2 manifest is missing; run src.v2_main first")
    if not isinstance(board, dict):
        board = {}

    content_key = str(manifest["content_key"])
    slug = str(manifest.get("slug") or "")
    title = str(board.get("title") or manifest.get("title") or "СпецАвтоПортал")
    master = OUT_DIR / "master.mp4"
    tiktok_video = OUT_DIR / "tiktok.mp4"
    if not master.exists():
        raise RuntimeError(f"master video missing: {master}")

    platforms = _configured_platforms(os.getenv("SOCIAL_PLATFORMS", "youtube,instagram,tiktok"))
    state = _load_social_state()
    entry = (state.get("content") or {}).get(content_key) or {}
    summary: dict[str, Any] = {"content_key": content_key, "title": title, "platforms": {}}
    success_count = 0

    for platform in platforms:
        if _platform_done(entry, platform):
            previous = (entry.get("platforms") or {}).get(platform) or {}
            print(f"[social] {platform}: already {previous.get('status')}, skip")
            summary["platforms"][platform] = {"status": "already_done"}
            success_count += 1
            continue

        if dry_run:
            print(f"[social] {platform}: dry-run")
            summary["platforms"][platform] = {"status": "dry_run"}
            continue

        try:
            if platform == "youtube":
                token_file = Path(os.getenv("YOUTUBE_TOKEN_FILE", "youtube_token.json"))
                if not token_file.exists():
                    print("[social] youtube: YOUTUBE_TOKEN_FILE missing, skip")
                    summary["platforms"][platform] = {"status": "not_configured"}
                    continue

                youtube_title = str(board.get("youtube_title") or title).strip()[:100]
                description = _caption(OUT_DIR / "caption_youtube.txt")
                hashtags = board.get("hashtags") if isinstance(board.get("hashtags"), list) else []
                result_id = upload_video(
                    str(master),
                    title=youtube_title,
                    description=description,
                    tags=[str(x).lstrip("#") for x in hashtags[:8]],
                    privacy_status=os.getenv("YOUTUBE_PRIVACY", "public").strip(),
                )
                result = {
                    "platform": "youtube",
                    "status": "published",
                    "video_id": result_id,
                    "url": f"https://www.youtube.com/shorts/{result_id}" if result_id else "",
                }

            elif platform == "instagram":
                token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()
                ig_user_id = os.getenv("INSTAGRAM_IG_USER_ID", "").strip()
                if not token or not ig_user_id:
                    print("[social] instagram: credentials missing, skip")
                    summary["platforms"][platform] = {"status": "not_configured"}
                    continue

                result = publish_reel(
                    master,
                    caption=_caption(OUT_DIR / "caption_instagram.txt"),
                    ig_user_id=ig_user_id,
                    access_token=token,
                    share_to_feed=os.getenv("INSTAGRAM_SHARE_TO_FEED", "1").strip() == "1",
                    api_version=os.getenv("INSTAGRAM_API_VERSION", "v26.0").strip(),
                    graph_base=os.getenv("INSTAGRAM_GRAPH_BASE", "https://graph.facebook.com").strip(),
                )

            elif platform == "tiktok":
                token = os.getenv("TIKTOK_ACCESS_TOKEN", "").strip()
                if not token:
                    print("[social] tiktok: TIKTOK_ACCESS_TOKEN missing, skip")
                    summary["platforms"][platform] = {"status": "not_configured"}
                    continue
                if not tiktok_video.exists():
                    raise RuntimeError("TikTok-safe video missing; run current src.v2_main")

                # Until the TikTok app has passed Direct Post review, the compliant
                # path is upload-to-inbox/drafts for final creator review.
                result = upload_video_draft(tiktok_video, access_token=token)

            else:
                continue

            print(f"[social] {platform}: {result.get('status')}")
            _record(state, content_key, title=title, platform=platform, result=result)
            entry = (state.get("content") or {}).get(content_key) or {}
            summary["platforms"][platform] = result
            success_count += 1

        except Exception as exc:
            error_result = {
                "platform": platform,
                "status": "error",
                "error": str(exc)[:1600],
            }
            print(f"[social] {platform}: ERROR {exc}")
            _record(state, content_key, title=title, platform=platform, result=error_result)
            entry = (state.get("content") or {}).get(content_key) or {}
            summary["platforms"][platform] = error_result

    if success_count > 0:
        _mark_v2_used(content_key, slug, title)

    if os.getenv("SOCIAL_STRICT", "0").strip() == "1":
        errors = [x for x in summary["platforms"].values() if x.get("status") == "error"]
        if errors:
            raise RuntimeError(f"social publish errors: {errors}")

    print("[social] summary", json.dumps(summary, ensure_ascii=False))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    publish_all(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
