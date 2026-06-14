"""
Edge TTS с retry-логикой и fallback на gTTS (Google).
Edge-TTS периодически отдаёт 403 с серверов Railway/Render —
tenacity делает 3 попытки с экспоненциальным backoff,
после чего gTTS берёт на себя роль провайдера.
"""

import logging
from pathlib import Path

import edge_tts
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

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
        try:
            await _synthesize_with_retry(text, str(target_path), voice, rate, pitch)
            logger.info("Edge TTS success: %s", target_path.name)
        except Exception as exc:
            logger.warning("Edge TTS failed after retries (%s), trying gTTS fallback", exc)
            await _gtts_fallback(text, target_path)
        return target_path


@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def _synthesize_with_retry(
    text: str,
    path: str,
    voice: str,
    rate: str,
    pitch: str,
) -> None:
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    await communicate.save(path)


async def _gtts_fallback(text: str, target_path: Path) -> None:
    """gTTS — бесплатный Google TTS, не требует аутентификации."""
    try:
        import asyncio
        from gtts import gTTS  # type: ignore[import-untyped]

        def _sync_gtts() -> None:
            tts = gTTS(text=text[:500], lang="ru", slow=False)
            tts.save(str(target_path))

        await asyncio.get_event_loop().run_in_executor(None, _sync_gtts)
        logger.info("gTTS fallback success: %s", target_path.name)
    except Exception as exc:
        logger.error("gTTS fallback also failed: %s", exc)
        raise
