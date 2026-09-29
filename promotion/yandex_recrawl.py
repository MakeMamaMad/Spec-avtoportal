#!/usr/bin/env python3
"""Send new pages to Yandex Webmaster recrawl ("Переобход страниц").

URLs come from promotion/config/recrawl_urls.txt. Each URL is submitted once
(tracked in frontend/data/promotion/yandex_recrawl_state.json) within the daily
quota reported by the API; the rest waits for the next run.

Token: YANDEX_WEBMASTER_OAUTH_TOKEN, falling back to YANDEX_METRIKA_OAUTH_TOKEN.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
URLS_PATH = ROOT / "promotion/config/recrawl_urls.txt"
STATE_PATH = ROOT / "frontend/data/promotion/yandex_recrawl_state.json"
API = "https://api.webmaster.yandex.net/v4"
HOST = "https://spec-avtoportal.ru"
SITEMAPS = [f"{HOST}/sitemap.xml", f"{HOST}/news-sitemap.xml"]

Request = Callable[[str, str, str, dict[str, Any] | None], Any]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def http(method: str, url: str, token: str, body: dict[str, Any] | None = None) -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"OAuth {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "SpecAvto-Recrawl",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def api_error(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    text = f"HTTP {code}" if code else type(exc).__name__
    reader = getattr(exc, "read", None)
    if code and callable(reader):
        try:
            body = json.loads(reader().decode("utf-8", "replace") or "{}")
            if body.get("error_code"):
                text += f" {body['error_code']}"
        except Exception:
            pass
    return text


def load_urls(path: Path | None = None) -> list[str]:
    urls = []
    for line in (path or URLS_PATH).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(HOST + "/") or line == HOST:
            urls.append(line)
    return list(dict.fromkeys(urls))


def pending(urls: list[str], state: dict[str, Any]) -> list[str]:
    done = state.get("submitted") or {}
    return [u for u in urls if u not in done]


def host_base(token: str, request: Request) -> str:
    user_id = request("GET", f"{API}/user", token, None).get("user_id")
    hosts = request("GET", f"{API}/user/{user_id}/hosts", token, None).get("hosts") or []
    host = next((h for h in hosts if str(h.get("ascii_host_url") or "").rstrip("/") == HOST), None)
    if not host:
        raise RuntimeError("host_not_found")
    return f"{API}/user/{user_id}/hosts/{urllib.parse.quote(str(host['host_id']), safe='')}"


def ensure_sitemaps(base: str, token: str, request: Request) -> list[str]:
    """Add our sitemaps to Webmaster if they are not there yet (NO_SITEMAPS)."""
    listed = request("GET", f"{base}/user-added-sitemaps", token, None).get("sitemaps") or []
    known = {str(row.get("sitemap_url") or "").rstrip("/") for row in listed}
    added = []
    for url in SITEMAPS:
        if url not in known:
            request("POST", f"{base}/user-added-sitemaps", token, {"url": url})
            added.append(url)
    return added


def run(token: str, request: Request = http) -> dict[str, Any]:
    state = json.loads(STATE_PATH.read_text("utf-8")) if STATE_PATH.exists() else {"schema": 1, "submitted": {}}
    state.setdefault("submitted", {})
    queue = pending(load_urls(), state)
    result: dict[str, Any] = {"sent": [], "failed": [], "left": 0, "quota": None}
    base = host_base(token, request)
    try:
        result["sitemaps_added"] = ensure_sitemaps(base, token, request)
    except urllib.error.HTTPError as exc:
        result["sitemaps_error"] = api_error(exc)
    if not queue:
        state["last_run"] = {"at": utc_now(), **result}
        return state

    quota = request("GET", f"{base}/recrawl/quota", token, None)
    remainder = int(quota.get("quota_remainder") or 0)
    result["quota"] = {"daily": quota.get("daily_quota"), "remainder_before": remainder}

    for url in queue:
        if remainder <= 0:
            break
        try:
            answer = request("POST", f"{base}/recrawl/queue", token, {"url": url})
            state["submitted"][url] = {"at": utc_now(), "task_id": answer.get("task_id")}
            result["sent"].append(url)
            remainder -= 1
        except urllib.error.HTTPError as exc:
            reason = api_error(exc)
            result["failed"].append({"url": url, "error": reason})
            if "QUOTA" in reason:
                break
    result["left"] = len(pending(load_urls(), state))
    state["last_run"] = {"at": utc_now(), **result}
    return state


def main() -> int:
    token = (os.getenv("YANDEX_WEBMASTER_OAUTH_TOKEN") or os.getenv("YANDEX_METRIKA_OAUTH_TOKEN") or "").strip()
    if not token:
        print("YANDEX_RECRAWL_SKIP no_token")
        return 0
    try:
        state = run(token)
    except Exception as exc:  # keep the reason, never the token
        print("YANDEX_RECRAWL_ERROR " + json.dumps({"error": api_error(exc) if isinstance(exc, urllib.error.HTTPError) else str(exc)[:200]}))
        return 1
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("YANDEX_RECRAWL_OK " + json.dumps(state["last_run"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
