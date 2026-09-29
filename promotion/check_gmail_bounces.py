#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

ROOT = Path(__file__).resolve().parents[1]
HISTORY_PATH = ROOT / "frontend/data/promotion/editorial_history.json"
QUEUE_PATH = ROOT / "frontend/data/promotion/manual_queue.json"
TARGETS_PATH = ROOT / "promotion/targets.json"
SUMMARY_PATH = ROOT / "frontend/data/promotion/editorial_summary.json"
STATE_PATH = ROOT / "frontend/data/promotion/gmail_delivery_state.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]
BOUNCE_QUERY = "newer_than:3d {from:mailer-daemon from:postmaster subject:(Delivery Status Notification) subject:(Mail delivery failed) subject:(Undelivered Mail)}"
ACTIVE_DELIVERY_STATUSES = {"email_sent", "email_partial_bounce"}


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


def parse_addresses(raw: str) -> list[str]:
    return sorted(
        {
            value.lower()
            for value in re.findall(
                r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
                str(raw or ""),
                flags=re.IGNORECASE,
            )
        }
    )


def split_contacts(raw: str) -> list[str]:
    return [value.lower() for value in parse_addresses(raw)]


def load_credentials(path: Path) -> Credentials:
    data = json.loads(path.read_text(encoding="utf-8"))
    scopes = data.get("scopes") or SCOPES
    creds = Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=scopes,
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        data["token"] = creds.token
        if getattr(creds, "expiry", None):
            data["expiry"] = creds.expiry.isoformat()
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not creds.valid:
        raise RuntimeError("Gmail OAuth credentials are not valid")
    return creds


def gmail_json(creds: Credentials, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    query = urllib.parse.urlencode(params or {})
    url = "https://gmail.googleapis.com/gmail/v1/users/me/" + path
    if query:
        url += "?" + query
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {creds.token}",
            "Accept": "application/json",
            "User-Agent": "SpecAvtoPortal-Gmail-Delivery-Check",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def decode_part(data: str) -> str:
    if not data:
        return ""
    padded = data + "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="replace")
    except Exception:
        return ""


def payload_text(payload: dict[str, Any]) -> str:
    chunks: list[str] = []

    def walk(part: dict[str, Any]) -> None:
        body = part.get("body") or {}
        raw = str(body.get("data") or "")
        mime = str(part.get("mimeType") or "").lower()
        if raw and (mime.startswith("text/") or not part.get("parts")):
            chunks.append(decode_part(raw))
        for child in part.get("parts") or []:
            if isinstance(child, dict):
                walk(child)

    walk(payload)
    headers = payload.get("headers") or []
    for header in headers:
        if isinstance(header, dict):
            name = str(header.get("name") or "").lower()
            if name in {"subject", "from", "to"}:
                chunks.append(str(header.get("value") or ""))
    return "\n".join(chunks)


def list_bounce_messages(creds: Credentials) -> list[str]:
    data = gmail_json(
        creds,
        "messages",
        {
            "q": BOUNCE_QUERY,
            "maxResults": "100",
        },
    )
    return [
        str(row.get("id") or "")
        for row in data.get("messages") or []
        if str(row.get("id") or "")
    ]


def update_target_contacts(targets: dict[str, Any], target_id: str, bounced: set[str]) -> None:
    for target in targets.get("targets") or []:
        if not isinstance(target, dict) or str(target.get("id") or "") != target_id:
            continue
        current = split_contacts(str(target.get("contact") or ""))
        remaining = [address for address in current if address not in bounced]
        if remaining:
            target["contact"] = "; ".join(remaining)
            note = f"Автоматически исключены недоставляемые адреса: {', '.join(sorted(bounced))}."
        else:
            target["contact"] = ""
            target["status"] = "paused"
            target["automation"] = "manual_verify_contact"
            target["policy"] = "editorial_manual_contact"
            note = f"Все известные email вернулись как недоставляемые: {', '.join(sorted(bounced))}. Автоматические письма приостановлены."
        old_note = str(target.get("notes") or "").strip()
        if note not in old_note:
            target["notes"] = (old_note + " " + note).strip()
        return


def apply_bounce(
    *,
    addresses: set[str],
    history: dict[str, Any],
    queue: dict[str, Any],
    targets: dict[str, Any],
    message_id: str,
) -> list[dict[str, Any]]:
    changed: list[dict[str, Any]] = []
    now = utc_now()

    for row in history.get("entries") or []:
        if not isinstance(row, dict) or str(row.get("status") or "") not in ACTIVE_DELIVERY_STATUSES:
            continue
        contacts = set(split_contacts(str(row.get("contact") or "")))
        matched = contacts & addresses
        if not matched:
            continue

        previous = set(str(value).lower() for value in row.get("bounced_recipients") or [])
        bounced = previous | matched
        row["bounced_recipients"] = sorted(bounced)
        row["last_bounce_message_id"] = message_id
        row["bounced_at"] = now
        row["delivery_detail"] = "Gmail delivery failure detected automatically."

        if contacts and contacts <= bounced:
            row["status"] = "email_bounced"
            row["delivery_status"] = "bounced"
        else:
            row["status"] = "email_partial_bounce"
            row["delivery_status"] = "partial_bounce"

        target_id = str(row.get("target_id") or "")
        slug = str(row.get("slug") or "")
        for qrow in queue.get("entries") or []:
            if not isinstance(qrow, dict):
                continue
            if str(qrow.get("target_id") or "") != target_id:
                continue
            action_id = str(qrow.get("action_id") or "")
            if slug and not action_id.endswith(":" + slug):
                continue
            qrow["status"] = row["status"]
            qrow["delivery_status"] = row["delivery_status"]
            qrow["bounced_recipients"] = sorted(bounced)
            qrow["bounced_at"] = now
            qrow["updated_at"] = now

        update_target_contacts(targets, target_id, bounced)
        changed.append(
            {
                "target_id": target_id,
                "target_name": row.get("target_name"),
                "status": row["status"],
                "bounced_recipients": sorted(bounced),
            }
        )

    return changed


def classify_error(exc: BaseException) -> dict[str, str]:
    """Reason code for the owner, without any secret values."""
    text = str(exc)
    name = type(exc).__name__
    code = name
    hint = "Нужна проверка workflow «Promotion — Gmail Delivery Check»."
    if "invalid_grant" in text:
        code = "token_expired_or_revoked"
        hint = (
            "Токен Gmail истёк или отозван. Нужно заново выпустить токен Gmail "
            "и обновить секрет GMAIL_TOKEN_B64."
        )
    elif "invalid_client" in text or "unauthorized_client" in text:
        code = "oauth_client_invalid"
        hint = "OAuth-клиент Google не принят. Проверьте client_id/client_secret в токене Gmail."
    elif isinstance(exc, urllib.error.HTTPError):
        code = f"gmail_http_{exc.code}"
        if exc.code in (401, 403):
            hint = "Gmail отклонил доступ. Вероятно, нужно заново выпустить токен Gmail."
        elif exc.code >= 500 or exc.code == 429:
            hint = "Временный сбой Gmail. Следующая проверка через час повторит попытку."
    elif isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError)):
        code = "network_error"
        hint = "Временная сетевая ошибка. Следующая проверка через час повторит попытку."
    elif isinstance(exc, (ValueError, KeyError)) and "token" in text.lower():
        code = "token_file_invalid"
        hint = "Секрет GMAIL_TOKEN_B64 повреждён. Нужно заново выпустить токен Gmail."
    detail = re.sub(r"(ya29\.|1//)[A-Za-z0-9._-]+", "***", text)[:300]
    return {"code": code, "error_type": name, "detail": detail, "hint": hint}


def record_error(error: dict[str, str]) -> dict[str, Any]:
    state = load_json(STATE_PATH, {"schema": 1, "processed_message_ids": []})
    previous = state.get("last_error") or {}
    streak = int(previous.get("streak") or 0) + 1 if previous.get("code") == error["code"] else 1
    state["last_error"] = {**error, "streak": streak, "at": utc_now()}
    save_json(STATE_PATH, state)
    return state["last_error"]


def main() -> int:
    try:
        return run()
    except Exception as exc:  # report a readable reason instead of a bare traceback
        error = record_error(classify_error(exc))
        print("GMAIL_BOUNCE_CHECK_ERROR " + json.dumps(error, ensure_ascii=False))
        return 1


def run() -> int:
    token_path = Path(os.environ.get("GMAIL_TOKEN_FILE", "gmail_token.json"))
    if not token_path.exists():
        print("GMAIL_BOUNCE_CHECK_SKIP token_not_configured")
        return 0

    creds = load_credentials(token_path)
    granted = set(getattr(creds, "scopes", None) or [])
    if "https://www.googleapis.com/auth/gmail.readonly" not in granted:
        print("GMAIL_BOUNCE_CHECK_SCOPE_MISSING gmail.readonly")
        return 0

    history = load_json(HISTORY_PATH, {"schema": 1, "entries": []})
    queue = load_json(QUEUE_PATH, {"schema": 1, "entries": []})
    targets = load_json(TARGETS_PATH, {"schema": 2, "targets": []})
    summary = load_json(SUMMARY_PATH, {"schema": 1})
    state = load_json(STATE_PATH, {"schema": 1, "processed_message_ids": []})
    processed = set(str(x) for x in state.get("processed_message_ids") or [])

    detected: list[dict[str, Any]] = []
    seen_now: list[str] = []

    for message_id in list_bounce_messages(creds):
        if message_id in processed:
            continue
        message = gmail_json(creds, f"messages/{message_id}", {"format": "full"})
        text = payload_text(message.get("payload") or {})
        addresses = set(parse_addresses(text))
        changed = apply_bounce(
            addresses=addresses,
            history=history,
            queue=queue,
            targets=targets,
            message_id=message_id,
        )
        detected.extend(changed)
        seen_now.append(message_id)

    if seen_now:
        state["processed_message_ids"] = (list(processed) + seen_now)[-500:]
        state["updated_at"] = utc_now()

    if detected:
        summary.update(
            {
                "status": "email_bounce_detected",
                "updated_at": utc_now(),
                "target_name": detected[-1].get("target_name"),
                "detail": f"Автоматически обнаружено возвратов Gmail: {len(detected)}.",
            }
        )

    save_json(HISTORY_PATH, history)
    save_json(QUEUE_PATH, queue)
    save_json(TARGETS_PATH, targets)
    save_json(SUMMARY_PATH, summary)
    if state.get("last_error"):
        state["recovered_at"] = utc_now()
        state.pop("last_error", None)
    save_json(STATE_PATH, state)

    print(
        "GMAIL_BOUNCE_CHECK_OK "
        + json.dumps(
            {
                "new_messages": len(seen_now),
                "matched_bounces": len(detected),
                "changes": detected,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
