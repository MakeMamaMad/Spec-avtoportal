#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "promotion/telegram_ads_config.json"
STATE_PATH = ROOT / "frontend/data/telegram_ads_state.json"
PACKAGE_PATH = ROOT / "frontend/data/telegram_ads_package.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def main() -> int:
    cfg = load_json(CONFIG_PATH, {})
    state = load_json(STATE_PATH, {})
    destination = state.get("landing_url") or cfg.get("destination", {}).get("channel_url")

    ads = []
    limit = int(cfg.get("rules", {}).get("max_ad_text_chars") or 160)
    for ad in cfg.get("ads", []):
        text = str(ad.get("text") or "")
        if len(text) > limit:
            raise SystemExit(f"Ad {ad.get('id')} is {len(text)} chars; Telegram limit is {limit}")
        ads.append({
            "id": ad.get("id"),
            "title": f"SpecAvtoPortal | {ad.get('target_channel')}",
            "text": text,
            "url": destination,
            "target_channels": [ad.get("target_url")],
            "cpm_ton": cfg.get("budget_policy", {}).get("cpm_start_ton"),
            "maximum_budget_ton": cfg.get("budget_policy", {}).get("maximum_budget_ton_per_ad"),
            "status": "ready_for_one_time_ads_setup",
            "text_chars": len(text),
        })

    out = {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "destination": destination,
        "site_tracking_url": state.get("site_tracking_url") or cfg.get("destination", {}).get("site_tracking_url"),
        "account_setup": {
            "recommended_account": "Organization linked to @specavtoportal",
            "funding_model": "Account balance is replenished by owner; ads spend while balance and per-ad maximum budget allow.",
        },
        "ads": ads,
        "kpis": cfg.get("kpis", {}),
    }
    PACKAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PACKAGE_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(ads)} Telegram Ads definitions. destination={destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
