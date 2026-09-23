from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dateutil import parser as dtparser
from PIL import Image

from .ai.storyboard import fallback_storyboard, generate_storyboard
from .ai.visuals import generate_scene_visual
from .render.short_v2 import media_duration, render_scene_frame, render_short


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
OUT_DIR = ROOT / "out_v2"
WORK_DIR = ROOT / "tmp_v2"
STATE_PATH = ROOT / "state" / "v2.json"

SITE_URL = os.getenv("SITE_URL", "https://spec-avtoportal.ru/").rstrip("/")
CONTENT_JSON_PATH = Path(
    os.getenv("CONTENT_JSON_PATH", str(REPO_ROOT / "frontend" / "data" / "news.json"))
)
VOICE = os.getenv("VOICE", "ru-RU-DmitryNeural").strip()
TTS_RATE = os.getenv("TTS_RATE", "+8%").strip()


IMPORTANT_WORDS = (
    "гост", "закон", "регламент", "штраф", "тамож", "границ",
    "рынок", "цена", "подорож", "продаж", "производ",
    "тягач", "грузовик", "полуприцеп", "прицеп", "логист",
    "маз", "камаз", "krone", "schmitz", "kögel", "saf",
)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _published(item: dict[str, Any]) -> datetime | None:
    for key in ("published_at", "published", "date", "datetime"):
        value = item.get(key)
        if not value:
            continue
        try:
            dt = dtparser.parse(str(value))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
    return None


def _item_key(item: dict[str, Any]) -> str:
    return _clean(item.get("id") or item.get("slug") or item.get("canonical_url") or item.get("url") or item.get("link"))


def _score(item: dict[str, Any]) -> float:
    title = _clean(item.get("title") or item.get("headline") or "").lower()
    summary = _clean(item.get("summary") or item.get("description") or "").lower()
    haystack = f"{title} {summary}"
    score = sum(1.4 for word in IMPORTANT_WORDS if word in haystack)
    published = _published(item)
    if published:
        age_hours = max(0.0, (datetime.now(timezone.utc) - published).total_seconds() / 3600)
        score += max(0.0, 8.0 - age_hours / 12.0)
    if re.search(r"\d", title):
        score += 0.8
    return score


def load_news() -> list[dict[str, Any]]:
    data = json.loads(CONTENT_JSON_PATH.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("items", [])
    if not isinstance(data, list):
        raise RuntimeError("news.json must be a list")
    return [item for item in data if isinstance(item, dict)]


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"schema": 1, "used": [], "renders": []}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError
    except Exception:
        data = {}
    data.setdefault("schema", 1)
    data.setdefault("used", [])
    data.setdefault("renders", [])
    return data


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def pick_item(news: list[dict[str, Any]], state: dict[str, Any]) -> dict[str, Any]:
    forced = os.getenv("V2_FORCE_SLUG", "").strip()
    if forced:
        for item in news:
            if str(item.get("slug") or "") == forced:
                return item
        raise RuntimeError(f"V2_FORCE_SLUG not found: {forced}")

    used = set(str(x) for x in state.get("used", []))
    max_age_hours = int(os.getenv("V2_MAX_AGE_HOURS", "96"))
    now = datetime.now(timezone.utc)

    candidates: list[tuple[float, dict[str, Any]]] = []
    for item in news:
        title = _clean(item.get("title") or item.get("headline"))
        slug = _clean(item.get("slug"))
        key = _item_key(item)
        if not title or not slug or not key or key in used:
            continue
        published = _published(item)
        if published and (now - published).total_seconds() > max_age_hours * 3600:
            continue
        enriched = dict(item)
        enriched["site_url"] = f"{SITE_URL}/news/{slug}/"
        candidates.append((_score(enriched), enriched))

    if not candidates:
        raise RuntimeError("No fresh unused news for Short v2")

    candidates.sort(key=lambda pair: pair[0], reverse=True)
    picked = candidates[0][1]
    print(f"[pick] score={candidates[0][0]:.2f} title={_clean(picked.get('title'))[:120]}")
    return picked


async def _edge_tts(text: str, output: Path) -> None:
    import edge_tts

    communication = edge_tts.Communicate(text=text, voice=VOICE, rate=TTS_RATE)
    await communication.save(str(output))


def generate_voice(text: str, output: Path) -> str:
    output.parent.mkdir(parents=True, exist_ok=True)

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if api_key and os.getenv("OPENAI_TTS", "1").strip() == "1":
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key)
            model = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts").strip()
            voice = os.getenv("OPENAI_TTS_VOICE", "cedar").strip()
            instructions = os.getenv(
                "OPENAI_TTS_INSTRUCTIONS",
                "Speak in natural Russian with a low, restrained, authoritative male news-presenter style. "
                "Sound calm, solid and serious rather than energetic. Keep a measured pace with clear diction. "
                "Avoid theatrical delivery, sales intonation and exaggerated emotion. Pronounce company names carefully.",
            ).strip()
            with client.audio.speech.with_streaming_response.create(
                model=model,
                voice=voice,
                input=text,
                instructions=instructions,
            ) as response:
                response.stream_to_file(output)
            print(f"[tts] OpenAI {model}/{voice}")
            return f"openai:{model}:{voice}"
        except Exception as exc:
            print(f"[tts] OpenAI failed, trying edge-tts: {exc}")

    try:
        asyncio.run(_edge_tts(text, output))
        print(f"[tts] edge-tts {VOICE} {TTS_RATE}")
        return "edge-tts"
    except Exception as exc:
        print(f"[tts] edge-tts failed, using gTTS: {exc}")
        from gtts import gTTS

        gTTS(text=text, lang="ru").save(str(output))
        return "gtts"


def fit_voice_to_storyboard(audio: Path, planned_seconds: float) -> float:
    """Speed up unusually slow TTS while keeping speech natural."""
    current = media_duration(audio)
    if current <= 0 or current <= planned_seconds + 1.5:
        return current

    speed = min(1.12, current / max(planned_seconds, 1.0))
    tmp = audio.with_name(audio.stem + "_fit" + audio.suffix)
    proc = __import__("subprocess").run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(audio),
            "-filter:a", f"atempo={speed:.4f}",
            "-vn", str(tmp),
        ],
        stdout=__import__("subprocess").PIPE,
        stderr=__import__("subprocess").PIPE,
    )
    if proc.returncode == 0 and tmp.exists() and tmp.stat().st_size > 0:
        tmp.replace(audio)
        fitted = media_duration(audio)
        print(f"[tts] fit {current:.2f}s -> {fitted:.2f}s speed={speed:.3f}")
        return fitted
    tmp.unlink(missing_ok=True)
    return current


def write_outputs(board, manifest: dict[str, Any]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "scene_plan.json").write_text(
        json.dumps(board.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUT_DIR / "caption_instagram.txt").write_text(board.instagram_caption + "\n", encoding="utf-8")
    (OUT_DIR / "caption_tiktok.txt").write_text(board.tiktok_caption + "\n", encoding="utf-8")
    (OUT_DIR / "caption_youtube.txt").write_text(board.youtube_description + "\n", encoding="utf-8")
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def self_test() -> int:
    os.environ["AI_IMAGES"] = "0"
    sample = {
        "id": "demo-1",
        "slug": "demo-news",
        "title": "Цены на седельные тягачи изменились за год",
        "summary": "Рынок показывает заметную динамику. Перевозчики пересматривают планы обновления парка.",
        "site_url": "https://spec-avtoportal.ru/news/demo-news/",
    }
    board = fallback_storyboard(sample)
    assert board.version == 2
    assert 4 <= len(board.scenes) <= 6
    assert 20 <= sum(scene.seconds for scene in board.scenes) <= 40

    with tempfile.TemporaryDirectory(prefix="sap-v2-test-") as tmp:
        root = Path(tmp)
        visual = root / "visual.png"
        frame = root / "frame.png"
        mode = generate_scene_visual(board.scenes[0], visual)
        render_scene_frame(
            board.scenes[0], visual, frame, index=1, total=len(board.scenes), format_name=board.format
        )
        with Image.open(frame) as image:
            assert image.size == (1080, 1920)
            assert image.mode == "RGB"
        assert mode == "procedural"
        assert frame.stat().st_size > 20_000
    print("Short Generator v2 self-test OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()

    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    state = load_state()
    item = pick_item(load_news(), state)
    board = generate_storyboard(item)

    visuals_dir = WORK_DIR / "visuals"
    visual_paths: list[Path] = []
    visual_modes: list[str] = []
    for index, scene in enumerate(board.scenes, 1):
        path = visuals_dir / f"scene_{index:02d}.png"
        visual_modes.append(generate_scene_visual(scene, path))
        visual_paths.append(path)

    audio = WORK_DIR / "voice.mp3"
    tts_mode = generate_voice(board.voiceover, audio)
    fit_voice_to_storyboard(audio, sum(scene.seconds for scene in board.scenes))

    video = OUT_DIR / "master.mp4"
    render_info = render_short(board, visual_paths, audio, video, WORK_DIR / "render")

    # TikTok gets the same editorial story/voice but a clean visual export
    # without superimposed brand/logo/URL.
    tiktok_video = OUT_DIR / "tiktok.mp4"
    tiktok_render_info = render_short(
        board,
        visual_paths,
        audio,
        tiktok_video,
        WORK_DIR / "render_tiktok",
        platform="tiktok",
    )

    thumbnail_source = Path(str(render_info["thumbnail"]))
    thumbnail = OUT_DIR / "thumbnail.png"
    shutil.copyfile(thumbnail_source, thumbnail)

    key = _item_key(item)
    manifest = {
        "schema": 2,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "content_key": key,
        "slug": item.get("slug"),
        "title": board.title,
        "format": board.format,
        "visual_modes": visual_modes,
        "tts": tts_mode,
        "render": render_info,
        "render_tiktok": tiktok_render_info,
        "ai_script": bool(os.getenv("OPENAI_API_KEY", "").strip()) and os.getenv("AI_SCRIPT", "1") == "1",
        "ai_images": bool(os.getenv("OPENAI_API_KEY", "").strip()) and os.getenv("AI_IMAGES", "1") == "1",
    }
    write_outputs(board, manifest)

    if os.getenv("V2_MARK_USED", "0").strip() == "1":
        state["used"] = list(dict.fromkeys([str(x) for x in state.get("used", [])] + [key]))[-2000:]
        state["renders"] = (state.get("renders", []) + [{
            "content_key": key,
            "slug": item.get("slug"),
            "created_at": manifest["created_at"],
            "format": board.format,
        }])[-500:]
        save_state(state)

    print(
        "[OK] Short v2",
        f"scenes={len(board.scenes)}",
        f"video={video}",
        f"tiktok_video={tiktok_video}",
        f"seconds={render_info['video_seconds']}",
        f"visuals={visual_modes}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
