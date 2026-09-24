from __future__ import annotations

from typing import Any

from .manual_queue import upsert_manual_action

BOT_UNSUPPORTED_STATUS = "bot_outreach_unsupported"
LEGACY_UNSUPPORTED_STATUSES = {"waiting_bot_to_bot", "outreach_unavailable"}


def is_bot_to_bot_failure(row: dict[str, Any]) -> bool:
    status = str(row.get("status") or "")
    detail = str(row.get("detail") or "")
    return (
        status == BOT_UNSUPPORTED_STATUS
        or (
            status in LEGACY_UNSUPPORTED_STATUSES
            and "USER_BOT_TO_BOT_DISABLED" in detail
        )
    )


def human_contact(target: dict[str, Any]) -> str:
    contact = str(target.get("contact") or "").strip()
    bot_contact = str(target.get("bot_contact") or "").strip()
    contact_type = str(target.get("contact_type") or "").strip().lower()

    if not contact:
        return ""
    if contact_type == "advertising_bot":
        return ""
    if bot_contact and contact.lower() == bot_contact.lower():
        return ""
    return contact


def fallback_pitch(target: dict[str, Any], tracking_url: str) -> str:
    name = str(target.get("name") or "канала")
    return (
        "Здравствуйте! Ведём СпецАвтоПортал — отраслевой ресурс о грузовой "
        "и специальной технике, прицепах и полуприцепах, рынке, производителях, "
        "ГОСТах и регламентах. "
        f"Хотим аккуратно познакомить аудиторию {name} с порталом. "
        "Подскажите, пожалуйста, возможен ли у вас рекламный или партнёрский пост? "
        f"Ссылка: {tracking_url}"
    )


def build_manual_action(
    target: dict[str, Any],
    queue_row: dict[str, Any] | None,
    *,
    created_at: str,
) -> dict[str, Any] | None:
    contact = human_contact(target)
    if not contact:
        return None

    target_id = str(target.get("id") or "")
    row = queue_row or {}
    tracking_url = str(row.get("tracking_url") or "").strip()
    pitch = str(row.get("outreach_pitch") or "").strip()
    if not pitch:
        pitch = fallback_pitch(target, tracking_url)

    return {
        "action_id": f"telegram-contact:{target_id}",
        "channel": "telegram_community",
        "target_id": target_id,
        "target_name": target.get("name"),
        "action": "contact_admin",
        "contact": contact,
        "status": "ready",
        "reason": (
            "Рекламный бот площадки не принимает сообщения от других ботов. "
            "Автоматические повторы отключены."
        ),
        "message": pitch,
        "tracking_url": tracking_url or None,
        "created_at": created_at,
        "updated_at": created_at,
    }


def unsupported_target_ids(history_rows: list[dict[str, Any]]) -> set[str]:
    return {
        str(row.get("target_id") or "")
        for row in history_rows
        if row.get("target_id") and is_bot_to_bot_failure(row)
    }


def migrate_legacy_failures(
    history_rows: list[dict[str, Any]],
    targets: list[dict[str, Any]],
    queue_rows: list[dict[str, Any]],
    manual_entries: list[dict[str, Any]],
    *,
    now: str,
) -> dict[str, Any]:
    targets_by_id = {
        str(target.get("id") or ""): target
        for target in targets
        if target.get("id")
    }
    queue_by_id = {
        str(row.get("target_id") or ""): row
        for row in queue_rows
        if row.get("target_id")
    }

    terminal_ids = {
        str(row.get("target_id") or "")
        for row in history_rows
        if row.get("status") == BOT_UNSUPPORTED_STATUS
    }

    latest_legacy: dict[str, dict[str, Any]] = {}
    for row in history_rows:
        target_id = str(row.get("target_id") or "")
        if not target_id or target_id in terminal_ids:
            continue
        status = str(row.get("status") or "")
        detail = str(row.get("detail") or "")
        if (
            status in LEGACY_UNSUPPORTED_STATUSES
            and "USER_BOT_TO_BOT_DISABLED" in detail
        ):
            latest_legacy[target_id] = row

    migrated = 0
    manual_created = 0
    manual_updated = 0
    for target_id, legacy in latest_legacy.items():
        target = targets_by_id.get(target_id, {})
        history_rows.append(
            {
                "target_id": target_id,
                "target_name": legacy.get("target_name") or target.get("name"),
                "contact": legacy.get("contact") or target.get("bot_contact"),
                "tracking_url": legacy.get("tracking_url"),
                "attempted_at": now,
                "status": BOT_UNSUPPORTED_STATUS,
                "detail": (
                    "Автоматическое обращение отключено после ответа Telegram "
                    "USER_BOT_TO_BOT_DISABLED; повторных попыток не будет."
                ),
            }
        )
        migrated += 1

        action = build_manual_action(
            target,
            queue_by_id.get(target_id),
            created_at=now,
        )
        if action:
            outcome = upsert_manual_action(manual_entries, action)
            if outcome == "created":
                manual_created += 1
            elif outcome == "updated":
                manual_updated += 1

    return {
        "migrated": migrated,
        "manual_created": manual_created,
        "manual_updated": manual_updated,
    }
