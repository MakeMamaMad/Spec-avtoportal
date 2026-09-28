#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import re
import urllib.parse
import urllib.request
from urllib.error import HTTPError
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = ROOT / "frontend/data/promotion/manual_queue.json"
HISTORY_PATH = ROOT / "frontend/data/promotion/editorial_history.json"
SUMMARY_PATH = ROOT / "frontend/data/promotion/editorial_summary.json"

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
READY_STATUSES = {"ready", "pending", "todo"}


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


def parse_recipients(raw: str) -> list[str]:
    values = [part.strip() for part in re.split(r"[;,]", raw or "") if part.strip()]
    return values


def dns_lookup(name: str, record_type: str) -> dict[str, Any] | None:
    query = urllib.parse.urlencode({"name": name, "type": record_type})
    request = urllib.request.Request(
        "https://dns.google/resolve?" + query,
        headers={
            "Accept": "application/dns-json",
            "User-Agent": "SpecAvtoPortal-Editorial-Mailer",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


def domain_accepts_mail(domain: str) -> tuple[bool | None, str]:
    domain = domain.strip().lower().rstrip(".")
    if not domain:
        return False, "empty_domain"

    mx = dns_lookup(domain, "MX")
    if mx is None:
        return None, "dns_check_unavailable"

    status = int(mx.get("Status", -1))
    if status == 3:
        return False, "NXDOMAIN"
    if status != 0:
        return None, f"dns_status_{status}"

    mx_answers = [row for row in (mx.get("Answer") or []) if int(row.get("type") or 0) == 15]
    for answer in mx_answers:
        data = str(answer.get("data") or "").strip()
        if data.endswith(" .") and data.startswith("0 "):
            return False, "null_mx"
        if data:
            return True, "mx"

    # RFC SMTP fallback: when MX is absent, the domain itself may accept mail.
    for record_type in ("A", "AAAA"):
        lookup = dns_lookup(domain, record_type)
        if lookup is None:
            continue
        if int(lookup.get("Status", -1)) == 3:
            return False, "NXDOMAIN"
        answers = lookup.get("Answer") or []
        if int(lookup.get("Status", -1)) == 0 and answers:
            return True, record_type.lower()

    return False, "no_mx_or_address"


def recipient_domain(address: str) -> str:
    return address.rsplit("@", 1)[-1].strip().lower() if "@" in address else ""


def pending_email_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [
        row
        for row in payload.get("entries", [])
        if isinstance(row, dict)
        and str(row.get("channel") or "").lower() == "email"
        and str(row.get("status") or "").lower() in READY_STATUSES
    ]
    rows.sort(key=lambda row: (str(row.get("created_at") or ""), str(row.get("action_id") or "")))
    return rows


def load_credentials(path: Path) -> Credentials:
    data = json.loads(path.read_text(encoding="utf-8"))
    creds = Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=data.get("scopes") or [GMAIL_SEND_SCOPE],
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


def send_message(creds: Credentials, recipients: list[str], subject: str, body: str) -> str:
    message = EmailMessage()
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(body)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")

    request = urllib.request.Request(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        data=json.dumps({"raw": raw}).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {creds.token}",
            "Content-Type": "application/json",
            "User-Agent": "SpecAvtoPortal-Editorial-Mailer",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gmail API HTTP {exc.code}: {detail}") from exc
    message_id = str(payload.get("id") or "").strip()
    if not message_id:
        raise RuntimeError("Gmail API returned no message id")
    return message_id


def mark_delivery_problem(
    queue: dict[str, Any],
    history: dict[str, Any],
    summary: dict[str, Any],
    row: dict[str, Any],
    reason: str,
) -> None:
    now = utc_now()
    row["status"] = "email_invalid_domain"
    row["delivery_status"] = "rejected_preflight"
    row["delivery_detail"] = reason
    row["updated_at"] = now

    target_id = str(row.get("target_id") or "")
    action_id = str(row.get("action_id") or "")
    slug = action_id.rsplit(":", 1)[-1] if ":" in action_id else ""
    for item in reversed(history.get("entries", [])):
        if not isinstance(item, dict):
            continue
        if str(item.get("target_id") or "") != target_id:
            continue
        if slug and str(item.get("slug") or "") != slug:
            continue
        if str(item.get("status") or "") in {"email_prepared", "email_sent"}:
            item["status"] = "email_invalid_domain"
            item["delivery_checked_at"] = now
            item["delivery_detail"] = reason
            break

    summary["status"] = "email_invalid_domain"
    summary["updated_at"] = now
    summary["target_name"] = row.get("target_name")
    summary["title"] = row.get("email_subject")
    summary["detail"] = "Письмо не отправлено: домен получателя не принимает почту или не существует."
    queue["updated_at"] = now


def mark_sent(
    queue: dict[str, Any],
    history: dict[str, Any],
    summary: dict[str, Any],
    row: dict[str, Any],
    message_id: str,
) -> None:
    sent_at = utc_now()
    row["status"] = "completed"
    row["sent_at"] = sent_at
    row["gmail_message_id"] = message_id
    row["updated_at"] = sent_at

    target_id = str(row.get("target_id") or "")
    action_id = str(row.get("action_id") or "")
    slug = action_id.rsplit(":", 1)[-1] if ":" in action_id else ""

    matched = False
    for item in reversed(history.get("entries", [])):
        if not isinstance(item, dict):
            continue
        if str(item.get("target_id") or "") != target_id:
            continue
        if slug and str(item.get("slug") or "") != slug:
            continue
        if str(item.get("status") or "") not in {"email_prepared", "email_sent"}:
            continue
        item["status"] = "email_sent"
        item["sent_at"] = sent_at
        item["gmail_message_id"] = message_id
        matched = True
        break

    if not matched:
        history.setdefault("entries", []).append(
            {
                "target_id": target_id,
                "target_name": row.get("target_name"),
                "slug": slug or None,
                "contact": row.get("contact"),
                "created_at": sent_at,
                "sent_at": sent_at,
                "status": "email_sent",
                "gmail_message_id": message_id,
            }
        )

    summary["status"] = "email_sent"
    summary["updated_at"] = sent_at
    summary["target_name"] = row.get("target_name")
    summary["title"] = row.get("email_subject")
    summary["detail"] = "Редакционное письмо автоматически отправлено через Gmail."

    queue["updated_at"] = sent_at


def main() -> int:
    token_path = Path(os.environ.get("GMAIL_TOKEN_FILE", "gmail_token.json"))
    if not token_path.exists():
        print("GMAIL_EMAIL_SEND_SKIP token_not_configured")
        return 0

    queue = load_json(QUEUE_PATH, {"schema": 1, "entries": []})
    rows = pending_email_entries(queue)
    if not rows:
        print("GMAIL_EMAIL_SEND_SKIP no_pending_email")
        return 0

    row = rows[0]
    recipients = parse_recipients(str(row.get("contact") or ""))
    subject = str(row.get("email_subject") or "").strip()
    body = str(row.get("message") or "").strip()

    if not recipients or not subject or not body:
        raise RuntimeError("Pending editorial email is missing recipient, subject, or body")

    history = load_json(HISTORY_PATH, {"schema": 1, "entries": []})
    summary = load_json(SUMMARY_PATH, {"schema": 1})

    invalid = []
    for address in recipients:
        domain = recipient_domain(address)
        verdict, detail = domain_accepts_mail(domain)
        if verdict is False:
            invalid.append({"address": address, "domain": domain, "detail": detail})

    if invalid:
        reason = json.dumps(invalid, ensure_ascii=False)
        mark_delivery_problem(queue, history, summary, row, reason)
        save_json(QUEUE_PATH, queue)
        save_json(HISTORY_PATH, history)
        save_json(SUMMARY_PATH, summary)
        print("GMAIL_EMAIL_PREFLIGHT_REJECT " + reason)
        return 0

    creds = load_credentials(token_path)
    message_id = send_message(creds, recipients, subject, body)
    mark_sent(queue, history, summary, row, message_id)

    save_json(QUEUE_PATH, queue)
    save_json(HISTORY_PATH, history)
    save_json(SUMMARY_PATH, summary)

    print(
        "GMAIL_EMAIL_SENT "
        + json.dumps(
            {
                "target_id": row.get("target_id"),
                "target_name": row.get("target_name"),
                "recipients": recipients,
                "gmail_message_id": message_id,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
