"""Free TTS candidates for the shorts narration: edge-tts, Silero, Piper.

Run: python free_voice_samples.py <out_dir>. Each engine is optional — a
failure is printed and the rest continue.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
import urllib.request
from pathlib import Path

from voice_samples import TEXT

EDGE = {"male-edge-dmitry": "ru-RU-DmitryNeural", "female-edge-svetlana": "ru-RU-SvetlanaNeural", "female-edge-dariya": "ru-RU-DariyaNeural"}
SILERO = {"male-silero-aidar": "aidar", "male-silero-eugene": "eugene", "female-silero-baya": "baya", "female-silero-xenia": "xenia"}
PIPER = {"male-piper-dmitri": "dmitri", "male-piper-ruslan": "ruslan", "male-piper-denis": "denis", "female-piper-irina": "irina"}


def to_mp3(wav: Path) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-c:a", "libmp3lame", "-q:a", "2", str(wav.with_suffix(".mp3"))], check=True)
    wav.unlink()


def edge(out: Path) -> None:
    import edge_tts

    for name, voice in EDGE.items():
        try:
            asyncio.run(edge_tts.Communicate(text=TEXT, voice=voice, rate="+5%").save(str(out / f"{name}.mp3")))
            print("ok", name, (out / f"{name}.mp3").stat().st_size)
        except Exception as exc:
            print("fail", name, exc)


def silero(out: Path) -> None:
    try:
        import torch
        import soundfile as sf

        model, _ = torch.hub.load("snakers4/silero-models", "silero_tts", language="ru", speaker="v4_ru")
        for name, speaker in SILERO.items():
            audio = model.apply_tts(text=TEXT, speaker=speaker, sample_rate=48000, put_accent=True, put_yo=True)
            wav = out / f"{name}.wav"
            sf.write(wav, audio.numpy(), 48000)
            to_mp3(wav)
            print("ok", name)
    except Exception as exc:
        print("fail silero", exc)


def piper(out: Path) -> None:
    base = "https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/{v}/medium/ru_RU-{v}-medium.onnx"
    for name, v in PIPER.items():
        try:
            model = out / f"{v}.onnx"
            urllib.request.urlretrieve(base.format(v=v), model)
            urllib.request.urlretrieve(base.format(v=v) + ".json", str(model) + ".json")
            wav = out / f"{name}.wav"
            subprocess.run(["piper", "--model", str(model), "--output_file", str(wav)], input=TEXT.encode(), check=True)
            model.unlink()
            Path(str(model) + ".json").unlink()
            to_mp3(wav)
            print("ok", name)
        except Exception as exc:
            print("fail", name, exc)


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "voice_samples")
    out.mkdir(parents=True, exist_ok=True)
    edge(out)
    silero(out)
    piper(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
