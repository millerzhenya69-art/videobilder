from tts.base import TTSProvider
from tts.edge import EdgeTTSProvider
from tts.silent import SilentTTSProvider


def create_tts_provider(engine: str) -> TTSProvider:
    if engine == "edge":
        return EdgeTTSProvider()
    if engine == "silent":
        return SilentTTSProvider()
    raise ValueError(f"Unsupported TTS engine: {engine}")
