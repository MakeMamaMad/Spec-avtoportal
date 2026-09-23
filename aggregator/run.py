from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aggregator import main as collector
from aggregator.pipeline.classify import build_classifier
from aggregator.pipeline.filtering import should_exclude

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES = ROOT / "aggregator" / "sources.yml"
DEFAULT_RULES = ROOT / "aggregator" / "rules.yml"
DEFAULT_OUTPUT = ROOT / "frontend" / "data" / "news.json"


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = collector.yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def read_existing(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text("utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON array")
    return data


def apply_rules(items: list[dict[str, Any]], rules: dict[str, Any]) -> list[dict[str, Any]]:
    classifier = build_classifier(rules)
    exclude_rules = rules.get("exclude") or {}
    kept: list[dict[str, Any]] = []

    for item in items:
        if should_exclude(item, exclude_rules):
            continue

        category = classifier(
            str(item.get("title") or ""),
            str(item.get("summary") or ""),
        )
        if category:
            item["category"] = category
        else:
            item.pop("category", None)
        kept.append(item)

    return kept


def save(items: list[dict[str, Any]], output: Path, meta_output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    meta_output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(items, ensure_ascii=False, indent=2), "utf-8")
    meta_output.write_text(
        json.dumps(
            {"updated_at": datetime.now(timezone.utc).isoformat(), "count": len(items)},
            ensure_ascii=False,
            indent=2,
        ),
        "utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect SpecAvtoPortal news and apply editorial rules.")
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--meta-output", type=Path, default=None)
    parser.add_argument("--max-items", type=int, default=5000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    max_items = max(1, int(args.max_items))
    meta_output = args.meta_output or args.output.with_name("news_meta.json")

    cfg = load_yaml(args.sources)
    rules = load_yaml(args.rules)
    sources = cfg.get("sources") or []
    if not isinstance(sources, list):
        raise ValueError(f"{args.sources}: 'sources' must be a list")

    print(f"[BOOT] runner: editorial-ingest v1")
    print(f"[BOOT] sources: {args.sources}")
    print(f"[BOOT] rules:   {args.rules}")
    print(f"[BOOT] output:  {args.output}")
    print(f"[RUN] configured sources: {len(sources)}")

    fresh = collector.collect(sources)
    existing = read_existing(args.output)
    collector.preserve_stable_identity(fresh, existing)

    existing_keys = {collector.item_key(item) for item in existing if collector.item_key(item)}
    new_count = sum(
        1
        for item in fresh
        if collector.item_key(item) and collector.item_key(item) not in existing_keys
    )

    merged = collector.dedup_by_link(fresh + existing)
    before_rules = len(merged)
    merged = apply_rules(merged, rules)
    excluded = before_rules - len(merged)
    merged = collector.sort_by_date(merged)[:max_items]

    collector.log("INFO", f"fresh after aggregate: {len(fresh)}")
    collector.log("INFO", f"existing in file: {len(existing)}")
    collector.log("INFO", f"new collected items: {new_count}")
    collector.log("INFO", f"editorial rules excluded: {excluded}")
    collector.log("INFO", f"merged total (<= {max_items}): {len(merged)}")
    collector.stats(merged)

    save(merged, args.output, meta_output)
    collector.log("DONE", f"saved {len(merged)} items -> {args.output}")
    collector.log("DONE", f"meta -> {meta_output}")


if __name__ == "__main__":
    main()
