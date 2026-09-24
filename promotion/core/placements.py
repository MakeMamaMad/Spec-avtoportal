from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

DEFAULT_CHECK_DAYS = (1, 3, 7, 14, 30)
SUBMISSION_STATUSES = {"submitted", "under_moderation", "accepted", "published"}
TERMINAL_STATES = {"rejected", "removed"}
SITE_MARKERS = ("spec-avtoportal.ru", "спецавтопортал")


def parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def placement_id(channel: str, target_id: str) -> str:
    return f"{channel}:{target_id}"


def row_time(row: dict[str, Any]) -> datetime | None:
    for key in ("attempted_at", "submitted_at", "published_at"):
        value = parse_dt(str(row.get(key) or ""))
        if value:
            return value
    return None


def _normalized_url(url: str) -> str:
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def probable_public_result(result_url: str, submission_url: str) -> bool:
    if not result_url:
        return False
    if submission_url and _normalized_url(result_url) == _normalized_url(submission_url):
        return False

    lowered = result_url.lower()
    form_markers = (
        "/add",
        "addsite",
        "add_url",
        "/create",
        "new_site",
        "/submit",
        "/register",
        "action=add",
        "page=add",
    )
    return not any(marker in lowered for marker in form_markers)


def check_days_for(target: dict[str, Any]) -> tuple[int, ...]:
    verification = target.get("verification") or {}
    raw = verification.get("check_days") or DEFAULT_CHECK_DAYS
    out: list[int] = []
    for value in raw:
        try:
            day = int(value)
        except (TypeError, ValueError):
            continue
        if day > 0 and day not in out:
            out.append(day)
    return tuple(sorted(out)) or DEFAULT_CHECK_DAYS


def next_check_at(submitted_at: str, check_days: tuple[int, ...], check_index: int) -> str | None:
    submitted = parse_dt(submitted_at)
    if submitted is None or check_index >= len(check_days):
        return None
    return iso(submitted + timedelta(days=check_days[check_index]))


def verification_url_for(placement: dict[str, Any], target: dict[str, Any]) -> str:
    verification = target.get("verification") or {}
    explicit = str(verification.get("url") or "").strip()
    if explicit:
        return explicit

    template = str(verification.get("url_template") or "").strip()
    if template:
        try:
            return template.format(
                domain="spec-avtoportal.ru",
                site_url="https://spec-avtoportal.ru/",
                title="СпецАвтоПортал",
                target_id=placement.get("target_id") or "",
            )
        except (KeyError, ValueError):
            return ""

    result_url = str(placement.get("result_url") or "").strip()
    submission_url = str(placement.get("submission_url") or "").strip()
    if probable_public_result(result_url, submission_url):
        return result_url
    return ""


def sync_directory_placements(
    placements: list[dict[str, Any]],
    history_rows: list[dict[str, Any]],
    targets: list[dict[str, Any]],
) -> int:
    by_id = {
        str(row.get("placement_id") or ""): row
        for row in placements
        if isinstance(row, dict) and row.get("placement_id")
    }
    targets_by_id = {
        str(target.get("id") or ""): target
        for target in targets
        if isinstance(target, dict) and target.get("id")
    }
    created = 0

    ordered = sorted(
        (row for row in history_rows if isinstance(row, dict)),
        key=lambda row: row_time(row) or datetime.min.replace(tzinfo=timezone.utc),
    )
    for row in ordered:
        status = str(row.get("status") or "")
        target_id = str(row.get("target_id") or "")
        when = row_time(row)
        if status not in SUBMISSION_STATUSES or not target_id or when is None:
            continue

        pid = placement_id("directory", target_id)
        target = targets_by_id.get(target_id, {})
        check_days = check_days_for(target)
        existing = by_id.get(pid)

        if existing is None:
            state = "live" if status == "published" else "pending_review"
            existing = {
                "placement_id": pid,
                "campaign_id": "portal-growth",
                "channel": "directory",
                "target_id": target_id,
                "target_name": row.get("target_name") or target.get("name"),
                "state": state,
                "submitted_at": iso(when),
                "submission_url": target.get("url"),
                "result_url": row.get("result_url"),
                "tracking_url": row.get("tracking_url"),
                "live_url": (
                    row.get("result_url")
                    if state == "live"
                    and probable_public_result(
                        str(row.get("result_url") or ""),
                        str(target.get("url") or ""),
                    )
                    else None
                ),
                "check_days": list(check_days),
                "check_index": 0,
                "next_check_at": next_check_at(iso(when), check_days, 0),
                "last_checked_at": None,
                "checks": [],
                "missing_count": 0,
            }
            placements.append(existing)
            by_id[pid] = existing
            created += 1
        else:
            if row.get("result_url"):
                existing["result_url"] = row.get("result_url")
            if row.get("tracking_url"):
                existing["tracking_url"] = row.get("tracking_url")
            if not existing.get("target_name"):
                existing["target_name"] = row.get("target_name") or target.get("name")
            if status == "published":
                existing["state"] = "live"
                result_url = str(row.get("result_url") or "")
                if probable_public_result(result_url, str(target.get("url") or "")):
                    existing["live_url"] = result_url
    return created


def is_due(placement: dict[str, Any], now: datetime) -> bool:
    if str(placement.get("state") or "") in TERMINAL_STATES:
        return False
    due = parse_dt(str(placement.get("next_check_at") or ""))
    return bool(due and due <= now.astimezone(timezone.utc))


def _decode_response(response: Any) -> str:
    raw = response.read(2_000_000)
    charset = response.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def body_has_listing(body: str, target: dict[str, Any]) -> bool:
    lowered = body.lower()
    markers = list(SITE_MARKERS)
    verification = target.get("verification") or {}
    for marker in verification.get("expected_markers") or []:
        value = str(marker).strip().lower()
        if value:
            markers.append(value)
    return any(marker in lowered for marker in markers)


def body_has_rejection(body: str, target: dict[str, Any]) -> bool:
    lowered = body.lower()
    verification = target.get("verification") or {}
    markers = [
        str(marker).strip().lower()
        for marker in (verification.get("rejection_markers") or [])
        if str(marker).strip()
    ]
    return bool(markers) and any(marker in lowered for marker in markers)


def fetch_verification(url: str, target: dict[str, Any], timeout: int = 25) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "User-Agent": "SpecAvtoPortal-PlacementVerifier/1.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = _decode_response(response)
            final_url = str(response.geturl() or url)
            if body_has_rejection(body, target):
                return {"outcome": "rejected", "url": final_url, "detail": "Площадка сообщает об отклонении размещения."}
            if body_has_listing(body, target):
                return {"outcome": "live", "url": final_url, "detail": "Публичное размещение подтверждено."}
            return {"outcome": "not_found", "url": final_url, "detail": "На публичной странице размещение пока не найдено."}
    except HTTPError as exc:
        return {
            "outcome": "missing" if exc.code in {404, 410} else "temporary_error",
            "url": url,
            "detail": f"HTTP {exc.code}",
        }
    except (URLError, TimeoutError, OSError) as exc:
        return {"outcome": "temporary_error", "url": url, "detail": type(exc).__name__}


def apply_verification_result(
    placement: dict[str, Any],
    result: dict[str, Any],
    checked_at: datetime,
) -> bool:
    before = (
        placement.get("state"),
        placement.get("live_url"),
        placement.get("next_check_at"),
        placement.get("missing_count"),
    )
    outcome = str(result.get("outcome") or "not_found")
    previous_state = str(placement.get("state") or "pending_review")
    placement["last_checked_at"] = iso(checked_at)

    checks = placement.setdefault("checks", [])
    checks.append(
        {
            "checked_at": iso(checked_at),
            "outcome": outcome,
            "url": result.get("url"),
            "detail": result.get("detail"),
        }
    )
    if len(checks) > 20:
        del checks[:-20]

    if outcome == "live":
        placement["state"] = "live"
        placement["live_url"] = result.get("url") or placement.get("live_url")
        placement["missing_count"] = 0
    elif outcome == "rejected" and previous_state != "live":
        placement["state"] = "rejected"
        placement["missing_count"] = 0
    elif outcome in {"missing", "not_found"} and previous_state == "live":
        missing_count = int(placement.get("missing_count") or 0) + 1
        placement["missing_count"] = missing_count
        if missing_count >= 2:
            placement["state"] = "removed"
    elif previous_state != "live":
        placement["state"] = "still_pending"

    if str(placement.get("state") or "") in TERMINAL_STATES:
        placement["next_check_at"] = None
    else:
        check_index = int(placement.get("check_index") or 0) + 1
        placement["check_index"] = check_index
        check_days = tuple(int(x) for x in (placement.get("check_days") or DEFAULT_CHECK_DAYS))
        placement["next_check_at"] = next_check_at(
            str(placement.get("submitted_at") or ""),
            check_days,
            check_index,
        )

    after = (
        placement.get("state"),
        placement.get("live_url"),
        placement.get("next_check_at"),
        placement.get("missing_count"),
    )
    return before != after
