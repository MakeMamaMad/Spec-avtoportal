import json
import os
import re
from pathlib import Path

from langdetect import detect
import argostranslate.package
import argostranslate.translate


NEWS_PATH = os.getenv("NEWS_PATH", "frontend/data/news.json")

# Переводим ТОЛЬКО эти домены (иностранные источники)
TRANSLATE_DOMAINS = {
    "globaltrailermag.com",
    "krone-trailer.com",
    "pressebox.de",
    "stockwatch.pl",
    "trucknews.com",
    "ttnews.com",
    "trailertechnician.com",
}

# С каких языков пытаемся перевести -> ru (можно расширять)
SOURCE_LANGS = ["en", "de", "pl"]


def looks_russian(text: str) -> bool:
    return bool(text and re.search(r"[А-Яа-яЁё]", text))


def normalize_domain(domain: str) -> str:
    d = (domain or "").strip().lower()
    d = d.replace("www.", "")
    return d


def normalize_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


def detect_lang_safe(text: str) -> str:
    text = normalize_text(text)
    if not text:
        return "unknown"
    if looks_russian(text):
        return "ru"
    try:
        return detect(text)
    except Exception:
        return "unknown"


def ensure_argos_packages():
    available = argostranslate.package.get_available_packages()
    for src in SOURCE_LANGS:
        pkg = next((p for p in available if p.from_code == src and p.to_code == "ru"), None)
        if pkg:
            path = pkg.download()
            argostranslate.package.install_from_path(path)


def translate_to_ru(text: str, src_lang: str) -> str:
    text = normalize_text(text)
    if not text:
        return ""
    if src_lang == "ru" or looks_russian(text):
        return text
    try:
        return argostranslate.translate.translate(text, src_lang, "ru")
    except Exception:
        return text


def should_translate_item(item: dict) -> bool:
    domain = normalize_domain(item.get("domain", ""))
    if not domain:
        return False
    return domain in TRANSLATE_DOMAINS


def main():
    news_file = Path(NEWS_PATH)
    if not news_file.exists():
        raise FileNotFoundError(f"Не найден файл: {NEWS_PATH}")

    data = json.loads(news_file.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Ожидался JSON-массив новостей")

    ensure_argos_packages()

    changed = 0
    for item in data:
        if not isinstance(item, dict):
            continue

        # ✅ переводим только выбранные иностранные домены
        if not should_translate_item(item):
            continue

        title = item.get("title", "") or ""
        summary = item.get("summary", "") or ""

        # язык определяем по связке title+summary
        sample = (title + " " + summary).strip()
        lang = detect_lang_safe(sample)

        # ✅ если вдруг уже RU — не переводим
        if lang == "ru":
            continue

        new_title = translate_to_ru(title, lang)
        new_summary = translate_to_ru(summary, lang)

        if new_title != title:
            item["title"] = new_title
            changed += 1
        if new_summary != summary:
            item["summary"] = new_summary
            changed += 1

    news_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: обновлено полей перевода: {changed}")


if __name__ == "__main__":
    main()
