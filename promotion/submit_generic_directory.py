#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from playwright.sync_api import Locator, Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_PATH = ROOT / "promotion/site_campaign.json"
TARGETS_PATH = ROOT / "promotion/site_targets.json"
HISTORY_PATH = ROOT / "frontend/data/site_promo_history.json"
SITE_URL = "https://spec-avtoportal.ru/"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def target_by_id(target_id: str) -> dict[str, Any]:
    data = load_json(TARGETS_PATH, {"targets": []})
    for target in data.get("targets", []):
        if target.get("id") == target_id:
            return target
    raise RuntimeError(f"Unknown catalog target: {target_id}")


def tracked_site_url(target: dict[str, Any]) -> str:
    params = urlencode({
        "utm_source": str(target.get("id") or "catalog"),
        "utm_medium": "directory",
        "utm_campaign": "catalog_promotion",
        "utm_content": "site_listing",
    })
    return f"{SITE_URL}?{params}"


def record(target: dict[str, Any], status: str, result_url: str = "", detail: str = "") -> None:
    history = load_json(HISTORY_PATH, {"schema": 1, "entries": []})
    history.setdefault("entries", []).append({
        "target_id": target.get("id"),
        "target_name": target.get("name"),
        "site_url": SITE_URL,
        "tracking_url": tracked_site_url(target),
        "utm_source": target.get("id"),
        "utm_medium": "directory",
        "utm_campaign": "catalog_promotion",
        "result_url": result_url,
        "attempted_at": utc_now(),
        "status": status,
        "detail": detail[:300],
    })
    save_json(HISTORY_PATH, history)
    print("RESULT=" + json.dumps(history["entries"][-1], ensure_ascii=False))


def visible(locator: Locator) -> list[Locator]:
    out: list[Locator] = []
    for i in range(locator.count()):
        el = locator.nth(i)
        try:
            if el.is_visible():
                out.append(el)
        except Exception:
            pass
    return out


def detect_captcha(page: Page) -> bool:
    selectors = [
        'iframe[src*="captcha" i]',
        'img[src*="captcha" i]',
        '.g-recaptcha',
        '[class*="captcha" i]',
        '[id*="captcha" i]',
        'input[name*="captcha" i]',
    ]
    if any(page.locator(s).count() for s in selectors):
        return True
    body = (page.locator("body").inner_text() or "").lower()
    return any(x in body for x in ("captcha", "капча", "я не робот", "код с картинки"))


def health_check(context) -> None:
    page = context.new_page()
    try:
        resp = page.goto(SITE_URL, wait_until="domcontentloaded", timeout=60000)
        if not resp or not resp.ok:
            raise RuntimeError("SpecAvtoPortal homepage is not reachable")
        result = page.evaluate(
            """async () => {
                for (const u of ['/data/news.json', 'data/news.json']) {
                    try {
                        const r = await fetch(u, {cache:'no-store'});
                        if (!r.ok) continue;
                        const d = await r.json();
                        const items = Array.isArray(d) ? d : (d.items || []);
                        if (items.length) return {ok:true, count:items.length};
                    } catch (_) {}
                }
                return {ok:false};
            }"""
        )
        if not result or not result.get("ok"):
            raise RuntimeError("SpecAvtoPortal news feed health-check failed")
        print(f"SITE_HEALTH_OK items={result.get('count')}")
    finally:
        page.close()


def control_signature(el: Locator) -> str:
    try:
        labels = el.evaluate(
            """el => Array.from(el.labels || []).map(x => (x.innerText || '').trim()).join(' ')"""
        )
    except Exception:
        labels = ""
    parts = [
        el.get_attribute("name") or "",
        el.get_attribute("id") or "",
        el.get_attribute("placeholder") or "",
        el.get_attribute("aria-label") or "",
        el.get_attribute("type") or "",
        str(labels or ""),
    ]
    return " ".join(parts).lower()


def accept_required_consents(form: Locator) -> None:
    for el in visible(form.locator('input[type="checkbox"]')):
        sig = control_signature(el)
        if not any(k in sig for k in ("соглас", "підтвердж", "подтверж", "правил", "terms", "policy")):
            continue
        try:
            if not el.is_checked():
                el.check()
        except Exception:
            continue


def pick_form(page: Page) -> Locator | None:
    forms = page.locator("form")
    best = None
    best_score = -1
    for i in range(forms.count()):
        form = forms.nth(i)
        try:
            if not form.is_visible():
                continue
        except Exception:
            continue
        score = 0
        action = (form.get_attribute("action") or "").lower()
        if any(k in action for k in ("add", "site", "url", "catalog", "register")):
            score += 5
        controls = visible(form.locator("input, textarea, select"))
        score += min(len(controls), 8)
        signatures = " ".join(control_signature(x) for x in controls)
        for token in ("url", "site", "link", "назван", "title", "name", "опис", "descr", "email", "mail"):
            if token in signatures:
                score += 2
        if form.locator('input[type="submit"], button[type="submit"]').count():
            score += 3
        if score > best_score:
            best_score = score
            best = form
    return best


def fill_matching(form: Locator, patterns: tuple[str, ...], value: str, tags: str = "input, textarea") -> bool:
    for el in visible(form.locator(tags)):
        sig = control_signature(el)
        if any(re.search(p, sig, re.I) for p in patterns):
            try:
                el.fill(value)
                return True
            except Exception:
                continue
    return False


def fill_selects(form: Locator, target: dict[str, Any]) -> None:
    wanted_categories = [str(x) for x in target.get("preferred_categories", [])]
    for sel in visible(form.locator("select")):
        sig = control_signature(sel)
        try:
            options = sel.locator("option")
            pairs = [
                ((options.nth(i).inner_text() or "").strip(), options.nth(i).get_attribute("value") or "")
                for i in range(options.count())
            ]
            if any(k in sig for k in ("country", "страна")):
                for label, value in pairs:
                    if "росси" in label.lower() and value:
                        sel.select_option(value=value)
                        break
                continue
            if any(k in sig for k in ("categor", "rubric", "раздел", "категор")) or wanted_categories:
                picked = False
                for wanted in wanted_categories:
                    for label, value in pairs:
                        if wanted.lower() in label.lower() and value:
                            sel.select_option(value=value)
                            picked = True
                            break
                    if picked:
                        break
                if picked:
                    continue
            if sel.get_attribute("required") is not None and not sel.input_value():
                for label, value in pairs:
                    if value:
                        sel.select_option(value=value)
                        break
        except Exception:
            continue


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    args = parser.parse_args()

    target = target_by_id(args.target)
    campaign = load_json(CAMPAIGN_PATH, {})
    email = os.getenv("PROMOTION_CONTACT_EMAIL", "").strip()

    if target.get("requires_email") is True and not email:
        record(target, "needs_manual", detail="PROMOTION_CONTACT_EMAIL is missing")
        return 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="ru-RU")
        page = None
        try:
            health_check(context)
            page = context.new_page()
            url = str(target.get("url") or "")
            resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            if not resp or not resp.ok:
                record(target, "unavailable", result_url=page.url, detail=f"HTTP {resp.status if resp else 'no response'}")
                return 0

            if detect_captcha(page):
                record(target, "needs_manual", result_url=page.url, detail="CAPTCHA/manual verification detected")
                return 0

            form = pick_form(page)
            if form is None:
                record(target, "technical_failure", result_url=page.url, detail="No suitable submission form found")
                return 0

            title = str(target.get("title_override") or campaign.get("title") or "СпецАвтоПортал")
            description = str(target.get("description_override") or campaign.get("full_description") or campaign.get("short_description") or "")
            keywords = str(target.get("keywords_override") or ", ".join(campaign.get("keywords") or []))
            region = str(campaign.get("region") or "Россия")
            promotion_url = tracked_site_url(target)

            url_ok = fill_matching(form, (r"url", r"site", r"link", r"адрес", r"сайт"), promotion_url)
            title_ok = fill_matching(form, (r"title", r"name", r"назван", r"заголов"), title)
            description_ok = fill_matching(form, (r"descr", r"description", r"text", r"опис"), description, "textarea, input")
            if email:
                fill_matching(form, (r"email", r"mail", r"почт"), email)
            fill_matching(form, (r"keyword", r"keyw", r"tag", r"ключ"), keywords)
            fill_matching(form, (r"city", r"region", r"город", r"регион"), region)
            fill_selects(form, target)
            accept_required_consents(form)

            if not url_ok:
                text_inputs = visible(form.locator('input[type="url"], input[type="text"], input:not([type])'))
                for el in text_inputs:
                    sig = control_signature(el)
                    if "search" in sig or "поиск" in sig:
                        continue
                    try:
                        el.fill(promotion_url)
                        url_ok = True
                        break
                    except Exception:
                        pass

            if not title_ok:
                candidates = visible(form.locator('input[type="text"], input:not([type])'))
                for el in candidates:
                    sig = control_signature(el)
                    if any(k in sig for k in ("search", "url", "site", "link", "email", "mail")):
                        continue
                    try:
                        if not el.input_value():
                            el.fill(title)
                            title_ok = True
                            break
                    except Exception:
                        pass

            if not description_ok:
                tas = visible(form.locator("textarea"))
                if tas:
                    tas[0].fill(description)
                    description_ok = True

            if not (url_ok and title_ok and description_ok):
                record(
                    target,
                    "technical_failure",
                    result_url=page.url,
                    detail=f"Required fields not confidently identified: url={url_ok}, title={title_ok}, description={description_ok}",
                )
                return 0

            if detect_captcha(page):
                record(target, "needs_manual", result_url=page.url, detail="CAPTCHA/manual verification appeared after filling")
                return 0

            submit = None
            for candidate in visible(form.locator('input[type="submit"], button[type="submit"]')):
                submit = candidate
                break
            if submit is None:
                buttons = visible(form.get_by_role("button"))
                for button in buttons:
                    label = (button.inner_text() or "").lower()
                    if any(k in label for k in ("добав", "отправ", "сохран", "регист", "submit", "add")):
                        submit = button
                        break
            if submit is None:
                record(target, "technical_failure", result_url=page.url, detail="No visible submit control")
                return 0

            submit.click(timeout=15000)
            page.wait_for_load_state("domcontentloaded", timeout=60000)
            body = (page.locator("body").inner_text() or "").lower()

            if detect_captcha(page):
                record(target, "needs_manual", result_url=page.url, detail="CAPTCHA/manual verification after submit")
                return 0

            error_markers = ("ошибка", "неверно", "заполните обязатель", "error")
            if any(marker in body for marker in error_markers):
                record(target, "technical_failure", result_url=page.url, detail="Site returned validation/error text")
                return 0

            status = "under_moderation" if any(
                marker in body for marker in ("модерац", "провер", "рассмотр", "на провер")
            ) else "submitted"
            record(target, status, result_url=page.url, detail="Automated directory submission completed")
            return 0

        except Exception as exc:
            record(target, "technical_failure", result_url=(page.url if page else ""), detail=f"{type(exc).__name__}: {exc}")
            return 0
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    raise SystemExit(main())
