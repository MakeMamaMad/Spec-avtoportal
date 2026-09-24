#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGETS_PATH = ROOT / "promotion/site_targets.json"
HISTORY_PATH = ROOT / "frontend/data/site_promo_history.json"
SUMMARY_PATH = ROOT / "frontend/data/daily_catalog_target.json"

MSK = timezone(timedelta(hours=3))

SUCCESS_STATUSES = {"submitted", "under_moderation", "published", "accepted"}
FINAL_ATTEMPT_STATUSES = SUCCESS_STATUSES | {
    "rejected",
    "technical_failure",
    "needs_manual",
    "unavailable",
}
SKIP_TARGET_STATUSES = {"blocked", "do_not_post", "paused", "paused_dns", "disabled"}


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_when(row: dict[str, Any]) -> datetime | None:
    for key in ("attempted_at", "submitted_at", "published_at"):
        raw = str(row.get(key) or "").strip()
        if not raw:
            continue
        try:
            value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value
        except ValueError:
            continue
    return None


def today_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    today = datetime.now(MSK).date()
    out = []
    for row in rows:
        when = parse_when(row)
        if when and when.astimezone(MSK).date() == today:
            out.append(row)
    return out


def latest_for_target(rows: list[dict[str, Any]], target_id: str) -> dict[str, Any] | None:
    matches = [r for r in rows if str(r.get("target_id") or "") == target_id]
    return matches[-1] if matches else None


def active_candidates(targets: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for target in targets:
        target_id = str(target.get("id") or "")
        status = str(target.get("status") or "")
        if not target_id or status in SKIP_TARGET_STATUSES:
            continue

        target_rows = [
            row for row in rows
            if str(row.get("target_id") or "") == target_id
            and row.get("status") in FINAL_ATTEMPT_STATUSES
        ]
        if any(row.get("status") in SUCCESS_STATUSES for row in target_rows):
            continue

        max_attempts = max(1, int(target.get("max_attempts") or 1))
        if len(target_rows) >= max_attempts:
            continue
        out.append(target)
    return out


def write_summary(status: str, attempts: list[dict[str, Any]], detail: str = "") -> None:
    today = str(datetime.now(MSK).date())
    payload = {
        "schema": 2,
        "date_moscow": today,
        "status": status,
        "attempts": attempts,
        "detail": detail,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if attempts:
        payload["target_id"] = attempts[-1].get("target_id")
        payload["target_name"] = attempts[-1].get("target_name")
    save_json(SUMMARY_PATH, payload)


def main() -> int:
    targets_data = load_json(TARGETS_PATH, {"targets": []})
    history = load_json(HISTORY_PATH, {"entries": []})
    rows = [x for x in history.get("entries", []) if isinstance(x, dict)]
    today = today_rows(rows)

    existing_success = next((r for r in today if r.get("status") in SUCCESS_STATUSES), None)
    if existing_success:
        write_summary(
            "already_successful_today",
            [existing_success],
            "A successful catalog submission already exists for today; no duplicate submission was made.",
        )
        print(f"ALREADY_SUCCESSFUL_TODAY target={existing_success.get('target_id')}")
        return 0

    candidates = active_candidates(
        [x for x in targets_data.get("targets", []) if isinstance(x, dict)],
        rows,
    )

    if not candidates:
        write_summary("queue_exhausted", today, "No unused automatic catalog targets remain.")
        print("CATALOG_QUEUE_EXHAUSTED")
        return 0

    max_attempts = int(os.getenv("CATALOG_MAX_ATTEMPTS_PER_RUN", "20"))
    attempts: list[dict[str, Any]] = []

    for target in candidates[:max_attempts]:
        target_id = str(target.get("id") or "")
        print(f"CATALOG_ATTEMPT target={target_id} name={target.get('name')}")
        proc = subprocess.run(
            [sys.executable, str(ROOT / "promotion/submit_generic_directory.py"), "--target", target_id],
            cwd=ROOT,
            check=False,
        )
        if proc.returncode != 0:
            print(f"WARN target={target_id} submitter_exit={proc.returncode}")

        history = load_json(HISTORY_PATH, {"entries": []})
        rows = [x for x in history.get("entries", []) if isinstance(x, dict)]
        latest = latest_for_target(rows, target_id)
        if latest is None:
            attempts.append({
                "target_id": target_id,
                "target_name": target.get("name"),
                "status": "technical_failure",
                "detail": f"Submitter exited {proc.returncode} without writing history",
            })
            continue

        attempts.append({
            "target_id": latest.get("target_id"),
            "target_name": latest.get("target_name"),
            "status": latest.get("status"),
            "detail": latest.get("detail"),
            "result_url": latest.get("result_url"),
            "tracking_url": latest.get("tracking_url"),
        })

        if latest.get("status") in SUCCESS_STATUSES:
            write_summary(
                "success",
                attempts,
                f"Stopped after successful submission to {latest.get('target_name') or target_id}.",
            )
            print(f"CATALOG_SUCCESS target={target_id} status={latest.get('status')}")
            return 0

        print(f"CATALOG_SKIP target={target_id} status={latest.get('status')} -> trying next catalog")

    history = load_json(HISTORY_PATH, {"entries": []})
    rows = [x for x in history.get("entries", []) if isinstance(x, dict)]
    remaining = active_candidates(
        [x for x in targets_data.get("targets", []) if isinstance(x, dict)],
        rows,
    )
    if remaining:
        write_summary(
            "attempt_limit_reached",
            attempts,
            f"Reached safety limit of {max_attempts} attempts; {len(remaining)} automatic targets remain.",
        )
        print(f"CATALOG_ATTEMPT_LIMIT remaining={len(remaining)}")
    else:
        write_summary(
            "queue_exhausted",
            attempts,
            "All currently available automatic catalog targets were checked; none accepted a submission.",
        )
        print("CATALOG_QUEUE_EXHAUSTED_AFTER_FAILOVER")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
