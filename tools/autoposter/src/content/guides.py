"""Weekly evergreen shorts built from our own knowledge articles and calculators.

News is forgotten in a day; fines, driver rest rules or axle loads are
searched for all year, and each episode links to a specific page on the site.
Episodes are hand-written in promotion/config/guide_shorts.json from the
article texts.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..ai.storyboard import Scene, Storyboard, _scene_prompt

REPO_ROOT = Path(__file__).resolve().parents[4]
CONFIG_PATH = REPO_ROOT / "promotion" / "config" / "guide_shorts.json"
KEY_PREFIX = "guide:"


def load_config(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or CONFIG_PATH).read_text(encoding="utf-8"))


def episode_key(episode: dict[str, Any]) -> str:
    return KEY_PREFIX + str(episode["id"])


def pick_episode(config: dict[str, Any], used: list[str]) -> dict[str, Any] | None:
    """First episode not yet published; None when all are out (slot falls back to news)."""
    done = set(used)
    for episode in config.get("episodes", []):
        if isinstance(episode, dict) and episode.get("id") and episode_key(episode) not in done:
            return episode
    return None


def build_storyboard(config: dict[str, Any], episode: dict[str, Any]) -> Storyboard:
    url = str(episode["url"])
    title = str(episode["title"]).strip()
    visual = str(episode.get("visual") or title)
    hashtags = [str(x) for x in config.get("hashtags", [])][:8]
    angles = [
        "hero shot, immediate visual hook",
        "documentary detail showing the core rule in practice",
        "operational context: fleet, road transport, paperwork",
        "practical close-up, problem and solution",
    ]
    scenes: list[Scene] = []
    for index, raw in enumerate(episode["scenes"], 1):
        scenes.append(Scene(
            id=f"guide-{index}",
            seconds=5.5,
            overlay=str(raw["overlay"]).strip(),
            narration=str(raw["narration"]).strip(),
            visual_prompt=_scene_prompt(visual, angles[(index - 1) % len(angles)]),
        ))
    scenes.append(Scene(
        id="cta",
        seconds=4.5,
        overlay="ПОДРОБНЕЕ НА САЙТЕ",
        narration="Полный разбор — на сайте СпецАвтоПортал, ссылка в описании. Подписывайтесь, чтобы не пропустить главное.",
        visual_prompt=_scene_prompt(visual, "clean closing hero shot with dark negative space"),
    ))
    body = "\n".join(f"— {s.overlay}" for s in scenes[:-1])
    description = f"{title}\n\n{body}\n\nПодробно: {url}\n\n" + " ".join(hashtags)
    return Storyboard(
        version=2,
        format="explainer",
        title=title,
        hook=scenes[0].overlay,
        voiceover=" ".join(s.narration for s in scenes),
        instagram_caption=description,
        tiktok_caption=f"{title}. {' '.join(hashtags[:4])}",
        youtube_title=title[:100],
        youtube_description=description,
        hashtags=hashtags,
        source_urls=[url],
        scenes=scenes,
    )
