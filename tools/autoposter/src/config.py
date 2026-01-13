import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

def _get(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return v if v is not None else default

@dataclass(frozen=True)
class Config:
    SITE_URL: str = _get("SITE_URL", "https://spec-avtoportal.ru/")
    TELEGRAM_URL: str = _get("TELEGRAM_URL", "https://t.me/specavtoportal")

    CONTENT_JSON_PATH: str = _get("CONTENT_JSON_PATH", "frontend/data/news.json")

    VIDEO_WIDTH: int = int(_get("VIDEO_WIDTH", "1080"))
    VIDEO_HEIGHT: int = int(_get("VIDEO_HEIGHT", "1920"))
    FPS: int = int(_get("FPS", "30"))

    SLIDE_TITLE_SECONDS: float = float(_get("SLIDE_TITLE_SECONDS", "2"))
    SLIDE_NEWS_SECONDS: float = float(_get("SLIDE_NEWS_SECONDS", "4"))
    SLIDE_CTA_SECONDS: float = float(_get("SLIDE_CTA_SECONDS", "3"))

    YOUTUBE_CLIENT_SECRETS: str = _get("YOUTUBE_CLIENT_SECRETS", "client_secrets.json")
    YOUTUBE_TOKEN_FILE: str = _get("YOUTUBE_TOKEN_FILE", "youtube_token.json")
    YOUTUBE_PRIVACY: str = _get("YOUTUBE_PRIVACY", "public")

cfg = Config()
