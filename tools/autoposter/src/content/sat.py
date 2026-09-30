"""Weekly partner shorts about SAT semi-trailers (satpricep.by).

Episodes are hand-written in promotion/config/sat_shorts.json so every fact
comes from the manufacturer's catalog — no AI-invented specs or AI images of
a real product. The storyboard uses real photos and ends on a partner card.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..ai.storyboard import Scene, Storyboard

REPO_ROOT = Path(__file__).resolve().parents[4]
CONFIG_PATH = REPO_ROOT / "promotion" / "config" / "sat_shorts.json"
KEY_PREFIX = "sat:"


def load_config(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or CONFIG_PATH).read_text(encoding="utf-8"))


def episode_key(episode: dict[str, Any]) -> str:
    return KEY_PREFIX + str(episode["id"])


def pick_episode(config: dict[str, Any], used: list[str]) -> dict[str, Any] | None:
    """First episode not yet published, or None when the catalog is exhausted.

    Published keys are skipped by the social publisher, so episodes are never
    repeated: when this returns None the slot falls back to a news short.
    """
    done = set(used)
    for episode in config.get("episodes", []):
        if isinstance(episode, dict) and episode.get("id") and episode_key(episode) not in done:
            return episode
    return None


def _tagged(url: str, utm: str) -> str:
    return url + ("&" if "?" in url else "?") + utm if utm else url


def build_storyboard(config: dict[str, Any], episode: dict[str, Any]) -> Storyboard:
    utm = str(config.get("utm") or "")
    url = _tagged(str(episode.get("url") or "https://satpricep.by/"), utm)
    domain = str(config.get("partner_domain") or "satpricep.by")
    photos = episode.get("photos") or [config.get("default_photo", "")]
    title = str(episode["title"]).strip()
    hashtags = [str(x) for x in config.get("hashtags", [])][:8]

    scenes: list[Scene] = []
    for index, raw in enumerate(episode["scenes"], 1):
        scenes.append(Scene(
            id=f"sat-{index}",
            seconds=5.5,
            overlay=str(raw["overlay"]).strip(),
            narration=str(raw["narration"]).strip(),
            visual_prompt="",
            highlight_words=[],
            source_image_url=str(photos[(index - 1) % len(photos)]),
        ))
    scenes.append(Scene(
        id="cta-partner",
        seconds=4.5,
        overlay=domain,
        narration="Цены и комплектации — на сайте производителя, ссылка в описании. Подписывайтесь на СпецАвтоПортал.",
        visual_prompt="",
        highlight_words=[],
        source_image_url=str(photos[0]),
    ))

    body = "\n".join(f"— {s.overlay}" for s in scenes[:-1])
    description = (
        f"{title}\n\n{body}\n\n"
        f"Цены и комплектации у производителя: {url}\n\n"
        "Реклама. Партнёрский материал о полуприцепах SAT.\n\n"
        + " ".join(hashtags)
    )
    return Storyboard(
        version=2,
        format="partner",
        title=title,
        hook=scenes[0].overlay,
        voiceover=" ".join(s.narration for s in scenes),
        instagram_caption=description,
        tiktok_caption=f"{title}. Реклама. {' '.join(hashtags[:4])}",
        youtube_title=title[:100],
        youtube_description=description,
        hashtags=hashtags,
        source_urls=[url],
        scenes=scenes,
    )
