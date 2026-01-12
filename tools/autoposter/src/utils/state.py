import json
from pathlib import Path
from typing import Set

STATE_PATH = Path(__file__).resolve().parents[2] / "state" / "posted.json"

def load_posted_urls() -> Set[str]:
    if not STATE_PATH.exists():
        return set()
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        urls = data.get("posted_urls") if isinstance(data, dict) else []
        if not isinstance(urls, list):
            return set()
        return set(str(u) for u in urls if u)
    except Exception:
        return set()

def save_posted_urls(urls: Set[str]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {"posted_urls": sorted(urls)}
    STATE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
