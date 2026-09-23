import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


NEWS_PATH = os.getenv("NEWS_PATH", "frontend/data/news.json")

# Fixed source-language mapping lets the cheap "count" pass run without
# importing language-detection or Argos packages.
DOMAIN_LANG = {
    "globaltrailermag.com": "en",
    "krone-trailer.com": "de",
    "pressebox.de": "de",
    "stockwatch.pl": "pl",
    "trucknews.com": "en",
    "ttnews.com": "en",
    "trailertechnician.com": "en",
}


def looks_russian(text: str) -> bool:
    return bool(text and re.search(r"[А-Яа-яЁё]", text))


def normalize_domain(domain: str) -> str:
    return (domain or "").strip().lower().replace("www.", "")


def normalize_text(text: Any) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


def source_lang(item: dict) -> str:
    return DOMAIN_LANG.get(normalize_domain(item.get("domain", "")), "")


def should_translate_item(item: dict) -> bool:
    lang = source_lang(item)
    if not lang:
        return False
    if item.get("translation_status") == "ru":
        return False

    title = normalize_text(item.get("title", ""))
    summary = normalize_text(item.get("summary", ""))
    sample = f"{title} {summary}".strip()
    if not sample or looks_russian(sample):
        return False
    return True


def candidate_items(data: list[dict]) -> list[dict]:
    return [
        item
        for item in data
        if isinstance(item, dict) and should_translate_item(item)
    ]


def load_news() -> tuple[Path, list[dict]]:
    news_file = Path(NEWS_PATH)
    if not news_file.exists():
        raise FileNotFoundError(f"Не найден файл: {NEWS_PATH}")

    data = json.loads(news_file.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Ожидался JSON-массив новостей")
    return news_file, data


def required_argos_pairs(required_langs: set[str]) -> set[tuple[str, str]]:
    """Return installable translation pairs needed to reach Russian.

    Argos can compose installed translations through intermediate languages.
    The public package index does not guarantee direct src->ru models for every
    source language, so German/Polish are routed through English.
    """
    pairs: set[tuple[str, str]] = set()
    for src in required_langs:
        if src == "ru":
            continue
        if src == "en":
            pairs.add(("en", "ru"))
        else:
            pairs.add((src, "en"))
            pairs.add(("en", "ru"))
    return pairs


def ensure_argos_packages(required_langs: set[str]) -> None:
    if not required_langs:
        return

    import argostranslate.package
    import argostranslate.translate

    installed = {
        (pkg.from_code, pkg.to_code)
        for pkg in argostranslate.package.get_installed_packages()
    }
    required_pairs = required_argos_pairs(required_langs)
    missing_pairs = required_pairs - installed

    if missing_pairs:
        pair_text = ", ".join(f"{src}->{dst}" for src, dst in sorted(missing_pairs))
        print(f"Installing missing Argos models: {pair_text}")
        argostranslate.package.update_package_index()
        available = argostranslate.package.get_available_packages()

        for src, dst in sorted(missing_pairs):
            pkg = next(
                (p for p in available if p.from_code == src and p.to_code == dst),
                None,
            )
            if not pkg:
                raise RuntimeError(f"Argos package {src}->{dst} not found")
            package_path = pkg.download()
            argostranslate.package.install_from_path(package_path)

    # Installing packages changes the translation graph. Clear Argos' cached
    # language list so newly installed pivot routes are immediately visible.
    try:
        argostranslate.translate.get_installed_languages.cache_clear()
    except AttributeError:
        pass

    installed_after = {
        (pkg.from_code, pkg.to_code)
        for pkg in argostranslate.package.get_installed_packages()
    }
    unresolved = required_pairs - installed_after
    if unresolved:
        raise RuntimeError(f"Argos models still missing after install: {sorted(unresolved)}")

    print(
        "Argos routes ready: "
        + ", ".join(f"{src}->ru" for src in sorted(required_langs))
    )


def translate_to_ru(text: str, src_lang: str) -> str:
    text = normalize_text(text)
    if not text or looks_russian(text):
        return text

    import argostranslate.translate

    try:
        translated = argostranslate.translate.translate(text, src_lang, "ru")
        return normalize_text(translated) or text
    except Exception as exc:
        print(f"WARN: translation failed {src_lang}->ru: {exc}")
        return text


def translate_item(item: dict) -> int:
    lang = source_lang(item)
    if not lang:
        return 0

    title = normalize_text(item.get("title", ""))
    summary = normalize_text(item.get("summary", ""))

    item.setdefault("original_title", title)
    item.setdefault("original_summary", summary)

    changed = 0
    new_title = translate_to_ru(title, lang)
    new_summary = translate_to_ru(summary, lang)

    if new_title != title:
        item["title"] = new_title
        changed += 1
    if new_summary != summary:
        item["summary"] = new_summary
        changed += 1

    # Mark complete only if translated content is actually Russian. This keeps
    # failures retryable on the next run.
    final_sample = f"{item.get('title', '')} {item.get('summary', '')}".strip()
    if looks_russian(final_sample):
        item["translation_status"] = "ru"
        item["translation_source_lang"] = lang
        item["translation_updated_at"] = datetime.now(timezone.utc).isoformat()

    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--count",
        action="store_true",
        help="Print how many items need translation without importing Argos.",
    )
    args = parser.parse_args()

    news_file, data = load_news()
    candidates = candidate_items(data)

    if args.count:
        print(len(candidates))
        return 0

    if not candidates:
        print("OK: перевод не требуется; новых иностранных материалов нет")
        return 0

    langs = {source_lang(item) for item in candidates if source_lang(item)}
    print(
        f"Translation queue: {len(candidates)} item(s), "
        f"languages: {', '.join(sorted(langs))}"
    )
    ensure_argos_packages(langs)

    changed = 0
    completed = 0
    for item in candidates:
        changed += translate_item(item)
        if item.get("translation_status") == "ru":
            completed += 1

    news_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"OK: translated items: {completed}/{len(candidates)}; "
        f"updated fields: {changed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
