import logging
import random
from datetime import UTC, datetime

from assets.provider import AssetProvider
from config.settings import Settings
from services.history import HistoryRepository
from services.llm import ScriptGenerator
from services.models import GenerationResult
from tts.factory import create_tts_provider
from video_generation.renderer import FFmpegRenderer

logger = logging.getLogger(__name__)

# Чередуем шаблоны: A→B→A→B... но можно задать вручную
_STYLES = ["dark_planet", "gradient_phone"]


class VideoGenerationPipeline:
    def __init__(self, settings: Settings, history: HistoryRepository) -> None:
        self.settings   = settings
        self.history    = history
        self.script_gen = ScriptGenerator(settings, history)
        self.assets     = AssetProvider(settings)
        self.tts        = create_tts_provider(settings.default_tts_engine)
        self.renderer   = FFmpegRenderer(settings)
        self._style_idx = 0   # счётчик для чередования

    async def generate(
        self,
        topic:        str | None = None,
        voice:        str | None = None,
        rate:         str | None = None,
        visual_style: str | None = None,   # None = авто-чередование
    ) -> GenerationResult:
        # Выбор шаблона
        if visual_style is None:
            visual_style = _STYLES[self._style_idx % len(_STYLES)]
            self._style_idx += 1
        logger.info("Visual style: %s | topic: %s", visual_style, topic)

        script      = await self.script_gen.generate(topic=topic)
        asset_list  = await self.assets.collect_for_scenes(script.scenes)

        stamp      = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        voice_path = self.settings.cache_dir / "audio" / f"voice_{stamp}.mp3"
        try:
            voice_path = await self.tts.synthesize(
                script.voiceover,
                voice_path,
                voice or self.settings.default_tts_voice,
                rate  or self.settings.speech_rate,
                self.settings.speech_pitch,
            )
        except Exception as exc:
            logger.warning("TTS failed, rendering without voice: %s", exc)
            voice_path = None

        video_path, subtitle_path = await self.renderer.render(
            script, asset_list, voice_path, visual_style=visual_style
        )

        result = GenerationResult(
            video_path    = video_path,
            script        = script,
            assets        = asset_list,
            subtitle_path = subtitle_path,
            voice_path    = voice_path,
        )
        await self.history.save(result)
        return result
