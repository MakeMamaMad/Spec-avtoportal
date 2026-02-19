# tools/autoposter/src/economic_templates.py
# Экспертные шаблоны Shorts: экономика владения полуприцепами
# Формат: voice_text + slides (карточки) + optional title/caption hints

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


# -----------------------------
# Data models
# -----------------------------
@dataclass
class Slide:
    title: str
    subtitle: str = ""
    badge: Optional[str] = None  # например "1/4" или "ВАЖНО"


@dataclass
class Episode:
    key: str
    title: str                 # YouTube title
    voice_text: str            # текст для TTS
    slides: List[Slide]        # 3-5 карточек
    description_lines: List[str]  # можно вставить в caption.txt


# -----------------------------
# Helpers
# -----------------------------
def _rub(n: int) -> str:
    # 54000 -> "54 000 ₽"
    s = f"{n:,}".replace(",", " ")
    return f"{s} ₽"


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _pick(rng: random.Random, a: int, b: int, step: int = 1000) -> int:
    # рандом по шагу (по умолчанию 1000 ₽)
    if step <= 0:
        step = 1
    a2 = (a // step) * step
    b2 = (b // step) * step
    if b2 < a2:
        a2, b2 = b2, a2
    return rng.randrange(a2, b2 + step, step)


def _one_line(s: str, limit: int = 90) -> str:
    s = " ".join((s or "").split())
    if len(s) <= limit:
        return s
    return s[: limit - 1].rstrip() + "…"


def _cta_lines(rng: random.Random, tg_url: str, site_url: str) -> Tuple[str, List[str]]:
    # Вариативный CTA, чтобы не было одинаково
    variants = [
        (
            "Подробный разбор и чек-листы — в Telegram. Архив — на сайте.",
            [
                f"Telegram: {tg_url}",
                f"Сайт (архив): {site_url}",
            ],
        ),
        (
            "В Telegram — чек-лист действий и типовые причины. На сайте — подборка материалов.",
            [
                f"Telegram: {tg_url}",
                f"Сайт: {site_url}",
            ],
        ),
        (
            "Хочешь меньше простоев? В Telegram — короткие схемы и проверки. Сайт — база.",
            [
                f"Telegram: {tg_url}",
                f"Сайт: {site_url}",
            ],
        ),
    ]
    return rng.choice(variants)


# -----------------------------
# Core templates
# -----------------------------
def build_episode(
    rng: random.Random,
    key: str,
    tg_url: str,
    site_url: str,
) -> Episode:
    """
    Возвращает Episode для Shorts "экономика владения".
    key: "downtime" | "tires" | "axle" | "overweight" | "used_buy"
    """
    if key == "downtime":
        return _tpl_downtime(rng, tg_url, site_url)
    if key == "tires":
        return _tpl_tires(rng, tg_url, site_url)
    if key == "axle":
        return _tpl_axle(rng, tg_url, site_url)
    if key == "overweight":
        return _tpl_overweight(rng, tg_url, site_url)
    if key == "used_buy":
        return _tpl_used_buy(rng, tg_url, site_url)

    # fallback
    return _tpl_downtime(rng, tg_url, site_url)


def pick_random_episode(
    seed: Optional[int],
    tg_url: str,
    site_url: str,
    allowed: Optional[List[str]] = None,
) -> Episode:
    rng = random.Random(seed if seed is not None else random.randrange(1_000_000_000))
    keys = allowed or ["downtime", "tires", "axle", "overweight", "used_buy"]
    key = rng.choice(keys)
    return build_episode(rng, key, tg_url, site_url)


# -----------------------------
# Template: downtime cost
# -----------------------------
def _tpl_downtime(rng: random.Random, tg_url: str, site_url: str) -> Episode:
    # Диапазоны (можешь подстроить под свой рынок)
    lost_trip = _pick(rng, 25000, 60000, 5000)     # потерянная выручка/маржа за рейс
    driver = _pick(rng, 3000, 7000, 500)          # дневной фонд водителя
    leasing = _pick(rng, 2500, 6000, 500)         # лизинг/кредит в день
    wear = _pick(rng, 1500, 5000, 500)            # амортизация/износ
    misc = _pick(rng, 1000, 4000, 500)            # стоянка/мелочи

    day = lost_trip + driver + leasing + wear + misc
    three = day * 3

    cta, cta_lines = _cta_lines(rng, tg_url, site_url)

    voice = (
        f"Один день простоя полуприцепа может стоить от {_rub(day)}.\n\n"
        f"Считаем по-простому.\n"
        f"Потерянный рейс — около {_rub(lost_trip)}.\n"
        f"Водитель — {_rub(driver)}.\n"
        f"Лизинг или кредит — {_rub(leasing)}.\n"
        f"Износ и амортизация — {_rub(wear)}.\n"
        f"Стоянка и мелкие расходы — {_rub(misc)}.\n\n"
        f"Итого: примерно {_rub(day)} за один день.\n"
        f"А три дня простоя — это уже {_rub(three)}.\n\n"
        f"{cta}"
    )

    slides = [
        Slide(title="СКОЛЬКО СТОИТ\n1 ДЕНЬ ПРОСТОЯ?", subtitle="Полуприцеп / прицеп", badge="ЭКОНОМИКА"),
        Slide(title=f"≈ {_rub(day)}", subtitle="потери за 1 день", badge="РАСЧЁТ"),
        Slide(title=f"3 ДНЯ = {_rub(three)}", subtitle="это уже серьёзно", badge="РИСК"),
        Slide(title="КАК СНИЗИТЬ\nПРОСТОИ?", subtitle="чек-лист в Telegram", badge="РЕШЕНИЕ"),
    ]

    title = "Сколько стоит 1 день простоя полуприцепа? (расчёт)"

    desc = [
        "Экономика владения: простой = потери.",
        "Короткий расчёт + что делать дальше.",
        *cta_lines,
    ]

    return Episode(key="downtime", title=title, voice_text=voice, slides=slides, description_lines=desc)


# -----------------------------
# Template: tires cost
# -----------------------------
def _tpl_tires(rng: random.Random, tg_url: str, site_url: str) -> Episode:
    # Колёса/шины — понятный "денежный" триггер
    set_cost = _pick(rng, 180000, 420000, 10000)  # комплект на оси/полный комплект (обобщённо)
    bad_pressure_loss = _pick(rng, 15000, 60000, 5000)  # потери на ускоренном износе
    downtime_day = _pick(rng, 30000, 60000, 5000)

    cta, cta_lines = _cta_lines(rng, tg_url, site_url)

    voice = (
        f"Комплект шин на полуприцеп — это примерно {_rub(set_cost)}.\n"
        f"И чаще всего его убивает не пробег, а давление и углы.\n\n"
        f"Если давление неправильное — легко теряется {_rub(bad_pressure_loss)} только на износе.\n"
        f"А если встал на день из-за резины — добавь ещё {_rub(downtime_day)} простоя.\n\n"
        f"Вывод: давление и контроль износа — это деньги.\n"
        f"{cta}"
    )

    slides = [
        Slide(title="ШИНЫ = ДЕНЬГИ", subtitle="полуприцеп", badge="ЭКОНОМИКА"),
        Slide(title=f"{_rub(set_cost)}", subtitle="примерно комплект", badge="ЦЕНА"),
        Slide(title=f"+{_rub(bad_pressure_loss)}", subtitle="потери из-за давления", badge="ПОТЕРИ"),
        Slide(title="ДАВЛЕНИЕ + ИЗНОС", subtitle="чек-лист контроля в TG", badge="РЕШЕНИЕ"),
    ]

    title = "Шины на полуприцеп: где теряются деньги (давление/износ)"

    desc = [
        "Экономика владения: шины и простой.",
        "Короткий разбор: почему шины «съедают» маржу.",
        *cta_lines,
    ]

    return Episode(key="tires", title=title, voice_text=voice, slides=slides, description_lines=desc)


# -----------------------------
# Template: axle / hub failure
# -----------------------------
def _tpl_axle(rng: random.Random, tg_url: str, site_url: str) -> Episode:
    repair = _pick(rng, 60000, 220000, 5000)
    tow = _pick(rng, 10000, 60000, 5000)
    downtime_day = _pick(rng, 30000, 60000, 5000)
    total = repair + tow + downtime_day

    cta, cta_lines = _cta_lines(rng, tg_url, site_url)

    voice = (
        f"Поломка по оси или ступице — это не только ремонт.\n\n"
        f"Ремонт — около {_rub(repair)}.\n"
        f"Эвакуатор — ещё {_rub(tow)}.\n"
        f"И минимум день простоя — {_rub(downtime_day)}.\n\n"
        f"В сумме легко выходит {_rub(total)}.\n"
        f"Поэтому диагностика и регламент — дешевле.\n"
        f"{cta}"
    )

    slides = [
        Slide(title="ОСЬ / СТУПИЦА", subtitle="сколько стоит поломка", badge="ЭКОНОМИКА"),
        Slide(title=f"{_rub(repair)}", subtitle="ремонт (примерно)", badge="РЕМОНТ"),
        Slide(title=f"+{_rub(tow)}", subtitle="эвакуатор", badge="ЭВАКУАТОР"),
        Slide(title=f"ИТОГО ≈ {_rub(total)}", subtitle="с учётом простоя", badge="РИСК"),
    ]

    title = "Ось/ступица: во сколько обходится поломка (с простоями)"

    desc = [
        "Экономика владения: оси/ступицы = риски и простой.",
        *cta_lines,
    ]

    return Episode(key="axle", title=title, voice_text=voice, slides=slides, description_lines=desc)


# -----------------------------
# Template: overweight / fines risk (обобщённо)
# -----------------------------
def _tpl_overweight(rng: random.Random, tg_url: str, site_url: str) -> Episode:
    fine = _pick(rng, 50000, 300000, 5000)
    downtime = _pick(rng, 1, 3, 1)  # дни
    downtime_cost = _pick(rng, 30000, 60000, 5000) * downtime
    total = fine + downtime_cost

    cta, cta_lines = _cta_lines(rng, tg_url, site_url)

    voice = (
        f"Перегруз — это не только штраф.\n\n"
        f"Штраф может быть около {_rub(fine)}.\n"
        f"Плюс простой на {downtime} день — это ещё {_rub(downtime_cost)}.\n\n"
        f"Итого риск — примерно {_rub(total)}.\n"
        f"Вывод: контроль веса и документов — это прямые деньги.\n"
        f"{cta}"
    )

    slides = [
        Slide(title="ПЕРЕГРУЗ", subtitle="сколько стоит ошибка", badge="РИСК"),
        Slide(title=f"{_rub(fine)}", subtitle="штраф (примерно)", badge="ШТРАФ"),
        Slide(title=f"+{_rub(downtime_cost)}", subtitle=f"простой {downtime} дн.", badge="ПРОСТОЙ"),
        Slide(title=f"РИСК ≈ {_rub(total)}", subtitle="контроль = экономия", badge="ВЫВОД"),
    ]

    title = "Перегруз: штраф + простой (сколько теряешь на одной ошибке)"

    desc = [
        "Экономика владения: перегруз = штрафы + простой.",
        *cta_lines,
    ]

    return Episode(key="overweight", title=title, voice_text=voice, slides=slides, description_lines=desc)


# -----------------------------
# Template: used trailer buying (чек-лист)
# -----------------------------
def _tpl_used_buy(rng: random.Random, tg_url: str, site_url: str) -> Episode:
    hidden = _pick(rng, 80000, 350000, 10000)
    downtime = _pick(rng, 1, 4, 1)
    downtime_cost = _pick(rng, 30000, 60000, 5000) * downtime
    total = hidden + downtime_cost

    cta, cta_lines = _cta_lines(rng, tg_url, site_url)

    voice = (
        f"Покупка б.у. полуприцепа часто ломает экономику не ценой, а скрытыми расходами.\n\n"
        f"Скрытый ремонт может вылезти на {_rub(hidden)}.\n"
        f"И ещё {downtime} день простоя — примерно {_rub(downtime_cost)}.\n\n"
        f"В сумме легко {_rub(total)} сверху.\n"
        f"Поэтому нужен чек-лист осмотра: оси, тормоза, рама, пневматика.\n"
        f"{cta}"
    )

    slides = [
        Slide(title="Б/У ПОЛУПРИЦЕП", subtitle="где теряются деньги", badge="ПОКУПКА"),
        Slide(title=f"{_rub(hidden)}", subtitle="скрытый ремонт", badge="РИСК"),
        Slide(title=f"+{_rub(downtime_cost)}", subtitle=f"простой {downtime} дн.", badge="ПРОСТОЙ"),
        Slide(title="ЧЕК-ЛИСТ ОСМОТРА", subtitle="оси/тормоза/рама — в TG", badge="РЕШЕНИЕ"),
    ]

    title = "Б/У полуприцеп: сколько съедают скрытые расходы (и простой)"

    desc = [
        "Экономика владения: б/у покупка = риск скрытых расходов.",
        *cta_lines,
    ]

    return Episode(key="used_buy", title=title, voice_text=voice, slides=slides, description_lines=desc)
