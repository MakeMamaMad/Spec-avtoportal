#!/usr/bin/env python3
"""Publish owner-approved editorial posts to the Telegram channel.

Each post lives in promotion/channel_posts/<id>.json:

    {
      "id": "2026-09-pinned-212",
      "approved": true,                  # only approved posts are sent
      "text_html": "...",                # Telegram HTML
      "document": "path/to/file.pdf",    # optional attachment
      "pin": true                        # optional: pin after sending
    }

A post is sent at most once: its id and message_id are recorded in
frontend/data/promotion/channel_posts_state.json. The workflow that runs this
script is manual-only (workflow_dispatch), so nothing is published on push.
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POSTS_DIR = ROOT / "promotion/channel_posts"
STATE_PATH = ROOT / "frontend/data/promotion/channel_posts_state.json"
CHANNEL_HANDLE = "specavtoportal"
CAPTION_LIMIT = 1024
TEXT_LIMIT = 4096


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def visible_length(text_html: str) -> int:
    return len(html.unescape(re.sub(r"<[^>]+>", "", text_html)))


def load_posts(posts_dir: Path | None = None) -> list[dict[str, Any]]:
    posts = []
    for path in sorted((posts_dir or POSTS_DIR).glob("*.json")):
        post = json.loads(path.read_text(encoding="utf-8"))
        post.setdefault("id", path.stem)
        posts.append(post)
    return posts


def validate(post: dict[str, Any]) -> list[str]:
    problems = []
    text = str(post.get("text_html") or "")
    if not text.strip():
        problems.append("empty text_html")
    document = post.get("document")
    limit = CAPTION_LIMIT if document else TEXT_LIMIT
    if visible_length(text) > limit:
        problems.append(f"text longer than {limit} characters")
    if document and not (ROOT / str(document)).is_file():
        problems.append(f"document not found: {document}")
    return problems


def pending_posts(posts: list[dict[str, Any]], state: dict[str, Any]) -> list[dict[str, Any]]:
    sent = state.get("sent") or {}
    return [p for p in posts if p.get("approved") is True and str(p["id"]) not in sent]


def api_call(token: str, method: str, fields: dict[str, Any], file_field: tuple[str, Path] | None = None) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/{method}"
    if file_field is None:
        data = urllib.parse.urlencode({k: str(v) for k, v in fields.items()}).encode("utf-8")
        req = urllib.request.Request(url, data=data)
    else:
        boundary = uuid.uuid4().hex
        body = bytearray()
        for key, value in fields.items():
            body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n".encode()
            body += str(value).encode("utf-8") + b"\r\n"
        name, path = file_field
        body += (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{path.name}\"\r\n"
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        body += path.read_bytes() + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            url, data=bytes(body), headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
        )
    with urllib.request.urlopen(req, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("ok"):
        raise RuntimeError(payload.get("description") or f"Telegram {method} failed")
    return payload.get("result") or {}


def publish(token: str, chat_id: str, post: dict[str, Any]) -> dict[str, Any]:
    text = str(post["text_html"])
    if post.get("document"):
        result = api_call(
            token,
            "sendDocument",
            {"chat_id": chat_id, "caption": text, "parse_mode": "HTML"},
            ("document", ROOT / str(post["document"])),
        )
    else:
        result = api_call(
            token,
            "sendMessage",
            {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"},
        )
    message_id = result.get("message_id")
    if not isinstance(message_id, int):
        raise RuntimeError("Telegram response has no message_id")
    record: dict[str, Any] = {
        "message_id": message_id,
        "url": f"https://t.me/{CHANNEL_HANDLE}/{message_id}",
        "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pinned": False,
    }
    if post.get("pin"):
        try:
            api_call(token, "pinChatMessage", {"chat_id": chat_id, "message_id": message_id, "disable_notification": "true"})
            record["pinned"] = True
        except Exception as exc:  # the post itself is already out; report and keep going
            record["pin_error"] = str(exc)[:200]
    return record


def main() -> int:
    posts = load_posts()
    state = load_json(STATE_PATH, {"schema": 1, "sent": {}})
    state.setdefault("sent", {})
    queue = pending_posts(posts, state)
    if not queue:
        print("CHANNEL_POSTS_NOTHING_TO_SEND")
        return 0

    bad = {str(p["id"]): validate(p) for p in queue if validate(p)}
    if bad:
        print("CHANNEL_POSTS_INVALID " + json.dumps(bad, ensure_ascii=False), file=sys.stderr)
        return 1

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("SKIP: Telegram credentials are not configured")
        return 0

    for post in queue:
        record = publish(token, chat_id, post)
        state["sent"][str(post["id"])] = record
        save_json(STATE_PATH, state)  # save after each post so a later failure never re-sends it
        print("CHANNEL_POST_SENT " + json.dumps({"id": post["id"], **record}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
