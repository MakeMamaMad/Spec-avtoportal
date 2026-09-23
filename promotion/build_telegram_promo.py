#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGETS_PATH = ROOT / "promotion/telegram_targets.json"
QUEUE_PATH = ROOT / "frontend/data/telegram_promo_queue.json"
HISTORY_PATH = ROOT / "frontend/data/telegram_promo_history.json"
SITE_URL = "https://spec-avtoportal.ru/"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def tracking_url(target_id: str) -> str:
    return SITE_URL + "?" + urlencode({
        "utm_source": target_id,
        "utm_medium": "telegram",
        "utm_campaign": "community_promotion",
        "utm_content": "site_ad",
    })


def pitch_for(target: dict[str, Any], url: str) -> str:
    name = target.get("name") or "канала"
    return (
        f"Здравствуйте! Ведём СпецАвтоПортал — отраслевой ресурс о грузовой и специальной технике, "
        f"прицепах и полуприцепах, рынке, производителях, ГОСТах и регламентах. "
        f"Хотим аккуратно познакомить аудиторию {name} с порталом. "
        f"Подскажите, пожалуйста, возможен ли у вас рекламный или партнёрский пост о самом ресурсе? "
        f"Готовый короткий текст и ссылка: {url}"
    )


def ad_copy(url: str) -> str:
    return (
        "🚛 СпецАвтоПортал — отраслевой ресурс о грузовой и специальной технике.\n\n"
        "Новости рынка, грузовики, прицепы и полуприцепы, производители, ГОСТы, регламенты "
        "и практические материалы — в одном месте.\n\n"
        f"Открыть портал: {url}"
    )


def main() -> int:
    targets = load_json(TARGETS_PATH, {"targets": []})
    history = load_json(HISTORY_PATH, {"entries": []})
    done = {
        str(x.get("target_id"))
        for x in history.get("entries", [])
        if x.get("status") in {"published", "rejected", "do_not_contact"}
    }

    rows = []
    for target in targets.get("targets", []):
        if target.get("status") in {"blocked", "do_not_contact", "disabled"}:
            continue
        target_id = str(target.get("id") or "")
        if not target_id or target_id in done:
            continue
        url = tracking_url(target_id)
        rows.append({
            "target_id": target_id,
            "target_name": target.get("name"),
            "handle": target.get("handle"),
            "contact": target.get("contact"),
            "contact_type": target.get("contact_type"),
            "policy": target.get("policy"),
            "status": target.get("status"),
            "approx_audience": target.get("approx_audience"),
            "tracking_url": url,
            "outreach_pitch": pitch_for(target, url),
            "ad_copy": ad_copy(url),
        })

    rows.sort(key=lambda x: -(int(x.get("approx_audience") or 0)))
    out = {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "campaign": "telegram_external_site_promotion",
        "entries": rows,
    }
    save_json(QUEUE_PATH, out)
    print(f"Prepared {len(rows)} Telegram promotion target(s).")
    if rows:
        print("NEXT_TARGET=" + rows[0]["target_id"])
        print("NEXT_CONTACT=" + str(rows[0].get("contact") or ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
