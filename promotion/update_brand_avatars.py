#!/usr/bin/env python3
"""Set the brand avatar (frontend/assets/avatar.png) on the Telegram channel and the VK community.

Manual, owner-approved run only. Each platform is tried independently; the
outcome is written to frontend/data/promotion/brand_avatar_state.json.
Tokens are never printed.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
AVATAR = ROOT / "frontend/assets/avatar.png"
STATE = ROOT / "frontend/data/promotion/brand_avatar_state.json"
VK_CONFIG = ROOT / "aggregator/vk_config.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def telegram(token: str, chat_id: str) -> dict[str, Any]:
    with AVATAR.open("rb") as fh:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/setChatPhoto",
            data={"chat_id": chat_id},
            files={"photo": ("avatar.png", fh, "image/png")},
            timeout=60,
        )
    body = resp.json()
    if not body.get("ok"):
        return {"status": "error", "detail": str(body.get("description") or resp.status_code)[:200]}
    return {"status": "ok"}


def vk_call(method: str, token: str, version: str, **params: Any) -> Any:
    body = requests.post(
        f"https://api.vk.com/method/{method}",
        data={**params, "access_token": token, "v": version},
        timeout=30,
    ).json()
    if "error" in body:
        err = body["error"]
        raise RuntimeError(f"{method}: {err.get('error_code')} {err.get('error_msg')}")
    return body.get("response")


def vk(token: str) -> dict[str, Any]:
    config = json.loads(VK_CONFIG.read_text("utf-8"))
    version = str(config.get("api_version") or "5.199")
    try:
        groups = vk_call("groups.getById", token, version, group_ids=config["community_screen_name"])
        rows = groups.get("groups") if isinstance(groups, dict) else groups
        group_id = abs(int(rows[0]["id"]))
        server = vk_call("photos.getOwnerPhotoUploadServer", token, version, owner_id=-group_id)
        with AVATAR.open("rb") as fh:
            uploaded = requests.post(server["upload_url"], files={"photo": ("avatar.png", fh, "image/png")}, timeout=60).json()
        vk_call("photos.saveOwnerPhoto", token, version, server=uploaded["server"], hash=uploaded["hash"], photo=uploaded["photo"])
    except Exception as exc:
        return {"status": "error", "detail": str(exc)[:200]}
    return {"status": "ok"}


def main() -> int:
    result: dict[str, Any] = {"at": now()}
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    tg_chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    result["telegram"] = telegram(tg_token, tg_chat) if tg_token and tg_chat else {"status": "skipped", "detail": "no credentials"}
    vk_token = os.getenv("VK_ACCESS_TOKEN", "").strip()
    result["vk"] = vk(vk_token) if vk_token else {"status": "skipped", "detail": "no credentials"}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("BRAND_AVATAR_RESULT " + json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
