#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from promotion.build_editorial_promo import (
    KNOWLEDGE_PATH,
    TARGETS_PATH,
    HISTORY_PATH,
    LEGACY_HISTORY_PATH,
    MANUAL_QUEUE_PATH,
    email_pitch,
    is_email_target,
    load_articles,
    load_pitch_config,
    manual_action,
    pick_action,
)
from promotion.core.manual_queue import upsert_manual_action
from promotion.send_editorial_email import (
    domain_accepts_mail,
    load_credentials,
    mark_delivery_problem,
    mark_sent,
    parse_recipients,
    pending_email_entries,
    recipient_domain,
    send_message,
)

SUMMARY_PATH = ROOT / "frontend/data/promotion/editorial_summary.json"
MSK = timezone(timedelta(hours=3))
MAX_CANDIDATES_PER_RUN = 12


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


def parse_dt(raw: str) -> datetime | None:
    try:
        value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value
    except Exception:
        return None


def sent_email_today(history: dict[str, Any], now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(MSK).date()
    for row in history.get("entries", []):
        if not isinstance(row, dict) or str(row.get("status") or "") != "email_sent":
            continue
        sent = parse_dt(str(row.get("sent_at") or row.get("created_at") or ""))
        if sent and sent.astimezone(MSK).date() == today:
            return True
    return False


def persist(
    queue: dict[str, Any],
    history: dict[str, Any],
    summary: dict[str, Any],
) -> None:
    save_json(MANUAL_QUEUE_PATH, queue)
    save_json(HISTORY_PATH, history)
    save_json(SUMMARY_PATH, summary)


def prepare_next_email(
    queue: dict[str, Any],
    history: dict[str, Any],
    now: datetime,
) -> dict[str, Any] | None:
    knowledge = load_json(KNOWLEDGE_PATH, {"items": []})
    targets_data = load_json(TARGETS_PATH, {"targets": []})
    legacy = load_json(LEGACY_HISTORY_PATH, {"entries": []})

    pitch_config = load_pitch_config()
    articles = load_articles(knowledge, pitch_config)
    targets = [
        row
        for row in targets_data.get("targets", [])
        if isinstance(row, dict) and is_email_target(row)
    ]
    planning_history = [
        row for row in history.get("entries", []) if isinstance(row, dict)
    ] + [
        row for row in legacy.get("entries", []) if isinstance(row, dict)
    ]

    action = pick_action(articles, targets, planning_history, now, allow_manual=False, pitch_config=pitch_config)
    if not action or action.get("execution") != "email":
        return None

    now_text = utc_now()
    upsert_manual_action(queue.setdefault("entries", []), manual_action(action, now_text))
    queue["updated_at"] = now_text
    history.setdefault("entries", []).append(
        {
            "target_id": action.get("target_id"),
            "target_name": action.get("target_name"),
            "slug": action.get("slug"),
            "title": action.get("title"),
            "site_url": action.get("site_url"),
            "contact": action.get("contact"),
            "item_key": action.get("item_key"),
            "created_at": now_text,
            "status": "email_prepared",
        }
    )
    return action


def valid_recipients(addresses: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    valid: list[str] = []
    invalid: list[dict[str, str]] = []
    for address in addresses:
        domain = recipient_domain(address)
        verdict, detail = domain_accepts_mail(domain)
        if verdict is False:
            invalid.append({"address": address, "domain": domain, "detail": detail})
        else:
            # A transient DNS-check failure is not treated as a permanent rejection.
            valid.append(address)
    return valid, invalid


def main() -> int:
    token_path = Path(os.environ.get("GMAIL_TOKEN_FILE", "gmail_token.json"))
    if not token_path.exists():
        print("DAILY_EDITORIAL_EMAIL_SKIP token_not_configured")
        return 0

    queue = load_json(MANUAL_QUEUE_PATH, {"schema": 1, "entries": []})
    history = load_json(HISTORY_PATH, {"schema": 1, "entries": []})
    summary = load_json(SUMMARY_PATH, {"schema": 1})

    if sent_email_today(history):
        print("DAILY_EDITORIAL_EMAIL_SKIP already_sent_today")
        return 0

    creds = load_credentials(token_path)

    for attempt in range(1, MAX_CANDIDATES_PER_RUN + 1):
        rows = pending_email_entries(queue)
        if not rows:
            action = prepare_next_email(queue, history, datetime.now(timezone.utc))
            if not action:
                summary.update(
                    {
                        "status": "no_valid_email_target",
                        "updated_at": utc_now(),
                        "target_name": None,
                        "title": None,
                        "detail": "Сегодня не найден новый действующий email-контакт для редакционного предложения.",
                    }
                )
                persist(queue, history, summary)
                print("DAILY_EDITORIAL_EMAIL_NO_TARGET")
                return 0
            persist(queue, history, summary)
            rows = pending_email_entries(queue)

        if not rows:
            continue

        row = rows[0]
        recipients = parse_recipients(str(row.get("contact") or ""))
        subject = str(row.get("email_subject") or "").strip()
        body = str(row.get("message") or "").strip()

        if not recipients or not subject or not body:
            mark_delivery_problem(
                queue,
                history,
                summary,
                row,
                "missing recipient, subject, or body",
            )
            persist(queue, history, summary)
            print(f"DAILY_EDITORIAL_EMAIL_REJECT attempt={attempt} reason=incomplete")
            continue

        deliverable, invalid = valid_recipients(recipients)
        if not deliverable:
            reason = json.dumps(invalid, ensure_ascii=False)
            mark_delivery_problem(queue, history, summary, row, reason)
            persist(queue, history, summary)
            print(
                "DAILY_EDITORIAL_EMAIL_REJECT "
                + json.dumps(
                    {
                        "attempt": attempt,
                        "target_id": row.get("target_id"),
                        "reason": invalid,
                    },
                    ensure_ascii=False,
                )
            )
            continue

        message_id = send_message(creds, deliverable, subject, body)
        if invalid:
            row["recipient_validation"] = {
                "skipped_invalid": invalid,
                "sent_to": deliverable,
            }
        mark_sent(queue, history, summary, row, message_id)
        persist(queue, history, summary)
        print(
            "DAILY_EDITORIAL_EMAIL_SENT "
            + json.dumps(
                {
                    "attempt": attempt,
                    "target_id": row.get("target_id"),
                    "target_name": row.get("target_name"),
                    "recipients": deliverable,
                    "gmail_message_id": message_id,
                },
                ensure_ascii=False,
            )
        )
        return 0

    summary.update(
        {
            "status": "email_candidates_exhausted",
            "updated_at": utc_now(),
            "detail": f"Проверено кандидатов: {MAX_CANDIDATES_PER_RUN}; рабочего email-контакта не найдено.",
        }
    )
    persist(queue, history, summary)
    print(f"DAILY_EDITORIAL_EMAIL_EXHAUSTED attempts={MAX_CANDIDATES_PER_RUN}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
