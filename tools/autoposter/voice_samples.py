"""Render the same short narration with several male voices for comparison.

Run from tools/autoposter: python voice_samples.py <out_dir>
Needs OPENAI_API_KEY for the OpenAI voices; edge-tts needs no key.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

TEXT = (
    "Еврофура — это сорок тонн, а не сорок четыре. Тягач с трёхосным полуприцепом — пять осей, "
    "и допустимая масса для него сорок тонн. Но даже в эти сорок можно получить штраф: "
    "сдвиньте груз на два метра к передней стенке — и ведущая ось перегружена на треть. "
    "Полный разбор — на сайте СпецАвтоПортал. Подписывайтесь, чтобы не пропустить главное."
)
INSTRUCTIONS = (
    "Speak natural conversational Russian like an experienced male automotive news presenter on the radio. "
    "Warm, confident, relaxed; small natural pitch changes and short pauses at punctuation. "
    "Brisk but comfortable pace, clear diction. Not solemn, not robotic, not like a commercial voice-over."
)
OPENAI_VOICES = ["cedar", "onyx", "ash", "echo", "verse", "ballad"]
FEMALE_VOICES = ["marin", "coral", "nova", "shimmer", "sage"]
EDGE_VOICES = ["ru-RU-DmitryNeural"]


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "voice_samples")
    out.mkdir(parents=True, exist_ok=True)
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if key:
        from openai import OpenAI

        client = OpenAI(api_key=key)
        for voice in OPENAI_VOICES + FEMALE_VOICES:
            instructions = INSTRUCTIONS.replace("male", "female") if voice in FEMALE_VOICES else INSTRUCTIONS
            try:
                with client.audio.speech.with_streaming_response.create(
                    model=os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"), voice=voice, input=TEXT, instructions=instructions,
                ) as response:
                    prefix = "female" if voice in FEMALE_VOICES else "male"
                    response.stream_to_file(out / f"{prefix}-openai-{voice}.mp3")
                print("ok", voice)
            except Exception as exc:
                print("fail", voice, exc)
    import edge_tts

    for voice in EDGE_VOICES:
        try:
            asyncio.run(edge_tts.Communicate(text=TEXT, voice=voice, rate="+5%").save(str(out / f"edge-{voice}.mp3")))
            print("ok", voice)
        except Exception as exc:
            print("fail", voice, exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
