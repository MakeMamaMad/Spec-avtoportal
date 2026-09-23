# SpecAvtoPortal Autoposter

Автопостер сейчас имеет два контура.

## Production v1

Текущий `src.main`:
- берёт свежие новости из `frontend/data/news.json`;
- делает вертикальный ролик 1080x1920;
- озвучивает его;
- автоматически публикует YouTube Shorts;
- хранит состояние в `tools/autoposter/state/posted.json`;
- сохраняет MP4 и caption в GitHub Actions artifacts.

Production workflow: `.github/workflows/autoposter.yml`.

## Short Generator v2

Новый контур предназначен для Instagram Reels, TikTok и YouTube Shorts с единым master-video.

Pipeline:

`news.json -> AI storyboard -> scene_plan.json -> AI/source visuals -> TTS -> cinematic renderer -> master.mp4`

v2 делает:
- одну сильную новость на ролик;
- 4-6 сцен длительностью примерно 24-34 секунды;
- отдельный hook, narration и visual prompt для каждой сцены;
- вертикальные AI-визуалы без текста/логотипов/водяных знаков;
- фирменную типографику SpecAvtoPortal поверх изображения;
- мягкий Ken Burns motion;
- динамические субтитры по 2-4 слова;
- отдельные captions для Instagram, TikTok и YouTube;
- thumbnail и machine-readable `scene_plan.json`.

Файлы:
- `src/ai/storyboard.py` — AI-сценарий с безопасным deterministic fallback;
- `src/ai/visuals.py` — генерация scene art + fallback на source/procedural;
- `src/render/short_v2.py` — cinematic frame/video renderer и ASS subtitles;
- `src/v2_main.py` — orchestration;
- `.github/workflows/shorts_v2_preview.yml` — безопасный preview, ничего не публикует.

## OpenAI

Если `OPENAI_API_KEY` не задан, v2 полностью работает в fallback-режиме и не делает платных AI-вызовов.

При наличии ключа используются:
- `OPENAI_TEXT_MODEL` — по умолчанию `gpt-5.6-luna`;
- `OPENAI_IMAGE_MODEL` — по умолчанию `gpt-image-2.5-sunburst`;
- `OPENAI_IMAGE_QUALITY` — `low`, `medium` или `high`;
- `AI_SCRIPT=1` включает AI-storyboard;
- `AI_IMAGES=1` включает AI visuals.

Секрет хранится только в GitHub Actions Secret `OPENAI_API_KEY`.

## Preview

Workflow **Shorts v2 Preview** можно запускать вручную. Он:
1. выполняет self-test;
2. рендерит ролик;
3. проверяет MP4 через ffprobe;
4. сохраняет `master.mp4`, thumbnail, captions, manifest и scene plan в artifact.

При обычных push этот workflow использует только fallback и не расходует OpenAI API.

## Следующий этап

После визуального утверждения v2:
1. включить production AI quality;
2. подключить Instagram Reels publishing;
3. подключить TikTok upload/draft;
4. затем переключить YouTube Shorts на тот же master renderer;
5. объединить social publishing state и аналитику.

## Legacy configuration

YouTube production secrets:
- `YOUTUBE_CLIENT_SECRETS_B64`;
- `YOUTUBE_TOKEN_B64`.

Production output (`tools/autoposter/out/`):
- `shorts_news.mp4`;
- `thumbnail.png`;
- `caption.txt`.

v2 preview output (`tools/autoposter/out_v2/`):
- `master.mp4`;
- `thumbnail.png`;
- `scene_plan.json`;
- `caption_instagram.txt`;
- `caption_tiktok.txt`;
- `caption_youtube.txt`;
- `manifest.json`.
