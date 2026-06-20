"""
Edge TTS с быстрым fallback на gTTS.

v11: главный фикс — pyproject.toml снял потолок версии edge-tts с "<7" на "<8".
Версии 6.x генерировали Sec-MS-GEC токен по устаревшему алгоритму (или не
генерировали вовсе), из-за чего Microsoft массово возвращал 403 на любых
серверных IP. В 7.2+ добавлена корректная генерация токена с clock-skew
correction — тот же механизм, что использует сам Edge-браузер.
Голос по умолчанию — ru-RU-DmitryNeural (мужской), задаётся в settings.py.
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
        # Одна попытка Edge TTS — если упадёт, сразу идём в gTTS без ожиданий.
        # timeout увеличен с 12 до 20с: на free-tier Render холодный старт
        # сетевого стека иногда занимает больше времени, чем сам синтез.
        try:
            import edge_tts
            communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
            await asyncio.wait_for(communicate.save(str(target_path)), timeout=20)
            if target_path.exists() and target_path.stat().st_size > 100:
                logger.info("Edge TTS success: %s (voice=%s)", target_path.name, voice)
                return target_path
            logger.warning("Edge TTS produced empty/tiny file, using gTTS fallback")
        except Exception as exc:
            logger.warning(
                "Edge TTS failed (%s: %s), using gTTS fallback",
                type(exc).__name__, str(exc)[:150],
            )

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
