#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def status_icon(conclusion: str) -> str:
    return {
        "success": "✅",
        "failure": "❌",
        "cancelled": "⚪",
        "skipped": "⏭️",
        "timed_out": "⏱️",
    }.get(conclusion, "ℹ️")


def catalog_details() -> list[str]:
    summary = load_json(ROOT / "frontend/data/daily_catalog_target.json", {})
    attempts = summary.get("attempts") or []
    lines = []
    if summary.get("status"):
        lines.append(f"**Каталоги:** {summary.get('status')}")
    for row in attempts[-8:]:
        name = row.get("target_name") or row.get("target_id") or "catalog"
        status = row.get("status") or "unknown"
        detail = str(row.get("detail") or "").strip()
        suffix = f" — {detail}" if detail else ""
        lines.append(f"- {name}: {status}{suffix}")
    return lines


def telegram_promo_details() -> list[str]:
    hist = load_json(ROOT / "frontend/data/telegram_promo_history.json", {"entries": []})
    rows = [x for x in hist.get("entries", []) if isinstance(x, dict)]
    if not rows:
        return []
    row = rows[-1]
    lines = [f"**Telegram promotion:** {row.get('target_name') or row.get('target_id')} — {row.get('status')}"]
    if row.get("detail"):
        lines.append(f"- {str(row.get('detail') or '').strip()}")
    return lines


def ads_details() -> list[str]:
    state = load_json(ROOT / "frontend/data/telegram_ads_state.json", {})
    if state.get("landing_url"):
        return [f"**Telegram Ads landing:** {state.get('landing_url')}"]
    return []


def ingest_details() -> list[str]:
    news = load_json(ROOT / "frontend/data/news.json", [])
    if isinstance(news, list):
        return [f"**Новости на сайте:** {len(news)} материалов в текущей базе."]
    return []


def main() -> int:
    event_path = Path(os.environ.get("GITHUB_EVENT_PATH", ""))
    event = load_json(event_path, {})
    run = event.get("workflow_run") or {}

    name = str(run.get("name") or "GitHub workflow")
    conclusion = str(run.get("conclusion") or "unknown")
    run_url = str(run.get("html_url") or "")
    branch = str(run.get("head_branch") or "")
    sha = str(run.get("head_sha") or "")[:8]
    event_name = str(run.get("event") or "")
    created = str(run.get("created_at") or "")
    updated = str(run.get("updated_at") or "")

    if name == "Checks — Full QA" and conclusion == "success":
        print("SKIP_REPORT")
        return 0

    lines = [
        f"### {status_icon(conclusion)} {name} — {conclusion}",
        "",
        f"- Ветка: {branch}",
        f"- Commit: {sha}",
        f"- Trigger: {event_name}",
    ]
    if created:
        lines.append(f"- Старт: {created}")
    if updated:
        lines.append(f"- Завершение: {updated}")

    if name == "Promotion — Daily Site Advertising":
        lines += [""] + catalog_details()
    elif name == "Promotion — Telegram Outreach":
        lines += [""] + telegram_promo_details()
    elif name == "Promotion — Prepare Telegram Ads":
        lines += [""] + ads_details()
    elif name == "Ingest & Publish":
        lines += [""] + ingest_details()

    if run_url:
        lines += ["", f"[Открыть GitHub Actions run]({run_url})"]

    lines += ["", f"_SpecAvto Control · {datetime.now(timezone.utc).isoformat(timespec='seconds')}_"]

    out = Path(os.environ.get("OPS_REPORT_PATH", "/tmp/specavto-report.md"))
    out.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
