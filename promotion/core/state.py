from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def append_event(path: Path, event: dict[str, Any]) -> None:
    payload = load_json(path, {"schema": 1, "events": []})
    events = payload.setdefault("events", [])
    if not isinstance(events, list):
        raise ValueError("promotion event store has invalid 'events' value")
    events.append(event)
    save_json(path, payload)
