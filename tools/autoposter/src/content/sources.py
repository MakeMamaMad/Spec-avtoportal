import json
import os
from dataclasses import dataclass
from typing import List, Any

from ..config import cfg

@dataclass
class ContentItem:
    title: str
    url: str
    summary: str = ""
    source: str = ""
    published: str = ""

def load_items() -> List[ContentItem]:
    path = cfg.CONTENT_JSON_PATH
    if not path or not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return _parse_json_items(data)

def _parse_json_items(data: Any) -> List[ContentItem]:
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    out: List[ContentItem] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        title = (it.get("title") or it.get("name") or "").strip()
        url = (it.get("url") or it.get("link") or it.get("href") or "").strip()
        summary = (it.get("summary") or it.get("desc") or it.get("description") or "").strip()
        source = (it.get("source") or it.get("publisher") or "").strip()
        published = (it.get("published") or it.get("date") or it.get("published_at") or "").strip()
        if title and url:
            out.append(ContentItem(title=title, url=url, summary=summary, source=source, published=published))
    return out
