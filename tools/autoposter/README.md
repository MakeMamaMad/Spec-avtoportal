# SpecAvtoPortal Autoposter (GitHub Actions, Format B digest)

Этот ассистент:
- берёт 3 свежих новости из `frontend/data/news.json`
- делает вертикальный ролик (дайджест "ТОП-3 за неделю")
- автоматически публикует **YouTube Shorts**
- сохраняет состояние в `tools/autoposter/state/posted.json`, чтобы не повторяться
- кладёт сгенерированный ролик + подпись в Artifacts (для ручной публикации в IG/TT)

## Важно: чтобы НЕ запускать деплой сайта
У вас деплой сайта запускается на push. Поскольку автопостер коммитит `posted.json`, добавьте `paths-ignore`
в workflow деплоя сайта:

```yaml
on:
  push:
    branches: [ "main" ]
    paths-ignore:
      - "tools/autoposter/**"
```

## GitHub Secrets
Нужны:
- `YOUTUBE_CLIENT_SECRETS_B64` — base64 от `client_secrets.json`
- `YOUTUBE_TOKEN_B64` — base64 от `youtube_token.json` (с refresh_token)

## Расписание
В `.github/workflows/autoposter.yml` стоит: Вт/Чт/Сб 12:00 МСК (09:00 UTC).

## Выходные файлы
`tools/autoposter/out/`:
- `digest_*.mp4`
- `caption.txt`
