"""
Edge TTS с быстрым fallback на gTTS.

Edge TTS на Render/Railway стабильно возвращает 403 — Microsoft закрыл
публичный WSS endpoint для серверных IP. Делаем ровно 1 попытку (без
многократных ретраев) и немедленно переходим на gTTS при любой ошибке.
Это экономит ~8–14 секунд на каждой генерации.
"""

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class EdgeTTSProvider:
    async def synthesize(
        self,
        text: str,
        target_path: Path,
        voice: str,
        rate: str,
        pitch: str,
    ) -> Path:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        # Одна попытка Edge TTS — если упадёт (403 с серверных IP),
        # сразу идём в gTTS без ожиданий.
        try:
            import edge_tts
            communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
            await asyncio.wait_for(communicate.save(str(target_path)), timeout=12)
            logger.info("Edge TTS success: %s", target_path.name)
            return target_path
        except Exception as exc:
            logger.warning("Edge TTS failed (%s), using gTTS fallback", type(exc).__name__)

        await _gtts_fallback(text, target_path, voice)
        return target_path


async def _gtts_fallback(text: str, target_path: Path, voice: str = "") -> None:
    """
    gTTS — бесплатный Google TTS, работает с серверных IP.
    Язык определяем по voice-строке: ru-RU-* → ru, иначе ru по умолчанию.
    """
    try:
        from gtts import gTTS  # type: ignore[import-untyped]

        lang = "ru"
        if voice and "-" in voice:
            lang_code = voice.split("-")[0].lower()
            if lang_code in ("ru", "en", "uk", "de", "fr", "es"):
                lang = lang_code

        def _sync() -> None:
            tts = gTTS(text=text[:500], lang=lang, slow=False)
            tts.save(str(target_path))

        await asyncio.get_event_loop().run_in_executor(None, _sync)
        logger.info("gTTS fallback success: %s", target_path.name)
    except Exception as exc:
        logger.error("gTTS fallback also failed: %s", exc)
        raise
