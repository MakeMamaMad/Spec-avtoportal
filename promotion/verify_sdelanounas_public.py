#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HISTORY_PATH = ROOT / "frontend/data/promotion/editorial_history.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize(value: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return re.sub(r"\s+", " ", value).strip().lower()


def public_url_from_result(result_url: str) -> str | None:
    try:
        parts = urllib.parse.urlsplit(result_url)
        query = urllib.parse.parse_qs(parts.query)
        raw = (query.get("id") or [""])[0]
        if raw.isdigit():
            return f"https://sdelanounas.ru/blogs/{raw}/"
    except Exception:
        return None
    return None


def fetch(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "SpecAvtoPortal-SdelanoU nas-Verifier/1.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read(2_000_000).decode(
            response.headers.get_content_charset() or "utf-8",
            errors="replace",
        )


def main() -> int:
    history = load_json(HISTORY_PATH, {"schema": 1, "entries": []})
    pending = [
        row
        for row in history.get("entries", [])
        if isinstance(row, dict)
        and row.get("target_id") == "sdelanounas"
        and str(row.get("status") or "") in {"submitted", "verified_in_author_cabinet"}
    ]
    if not pending:
        print("SDELANOUNAS_VERIFY_SKIP no_pending")
        return 0

    published = 0
    for row in pending:
        result_url = str(row.get("result_url") or "")
        public_url = public_url_from_result(result_url)
        row["last_public_check_at"] = utc_now()
        if not public_url:
            row["public_status"] = "unknown"
            continue

        try:
            body = fetch(public_url)
        except Exception as exc:
            row["public_status"] = "pending"
            row["public_check_detail"] = type(exc).__name__
            continue

        title = normalize(str(row.get("title") or ""))
        page = normalize(body)
        if title and title in page:
            row["status"] = "published"
            row["public_status"] = "published"
            row["public_url"] = public_url
            row["published_at"] = utc_now()
            published += 1
        else:
            row["public_status"] = "pending"

    save_json(HISTORY_PATH, history)
    print(f"SDELANOUNAS_VERIFY_OK checked={len(pending)} published={published}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
