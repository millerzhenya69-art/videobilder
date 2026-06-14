from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    allowed_user_ids: str = Field(default="", alias="ALLOWED_USER_IDS")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    # Исправлено: актуальная модель
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")
    llm_temperature: float = Field(default=0.9, alias="LLM_TEMPERATURE")

    app_name: str = Field(default="AtlantaVPN Video Bot", alias="APP_NAME")
    brand_name: str = Field(default="AtlantaVPN", alias="BRAND_NAME")
    brand_url: str = Field(default="https://atlantavpn.example", alias="BRAND_URL")
    cta_text: str = Field(default="Ссылка в шапке профиля", alias="CTA_TEXT")

    video_width: int = Field(default=720, alias="VIDEO_WIDTH")
    video_height: int = Field(default=1280, alias="VIDEO_HEIGHT")
    min_duration_seconds: int = Field(default=15, alias="MIN_DURATION_SECONDS")
    max_duration_seconds: int = Field(default=25, alias="MAX_DURATION_SECONDS")
    # 30 fps достаточно для Reels/TikTok и экономит RAM при FFmpeg
    fps: int = Field(default=30, alias="FPS")

    default_tts_engine: str = Field(default="edge", alias="DEFAULT_TTS_ENGINE")
    default_tts_voice: str = Field(default="ru-RU-DmitryNeural", alias="DEFAULT_TTS_VOICE")
    default_voice_gender: str = Field(default="male", alias="DEFAULT_VOICE_GENDER")
    speech_rate: str = Field(default="+5%", alias="SPEECH_RATE")
    speech_pitch: str = Field(default="+0Hz", alias="SPEECH_PITCH")

    cache_dir: Path = Field(default=Path("cache"), alias="CACHE_DIR")
    logs_dir: Path = Field(default=Path("logs"), alias="LOGS_DIR")
    assets_dir: Path = Field(default=Path("assets"), alias="ASSETS_DIR")
    templates_dir: Path = Field(default=Path("templates"), alias="TEMPLATES_DIR")
    sqlite_path: Path = Field(default=Path("cache/bot.sqlite3"), alias="SQLITE_PATH")

    pexels_api_key: str = Field(default="", alias="PEXELS_API_KEY")
    pixabay_api_key: str = Field(default="", alias="PIXABAY_API_KEY")

    @property
    def allowed_users(self) -> set[int]:
        if not self.allowed_user_ids.strip():
            return set()
        return {int(item.strip()) for item in self.allowed_user_ids.split(",") if item.strip()}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    settings.assets_dir.mkdir(parents=True, exist_ok=True)
    (settings.cache_dir / "videos").mkdir(parents=True, exist_ok=True)
    (settings.cache_dir / "audio").mkdir(parents=True, exist_ok=True)
    return settings
