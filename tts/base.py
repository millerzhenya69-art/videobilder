from pathlib import Path
from typing import Protocol


class TTSProvider(Protocol):
    async def synthesize(self, text: str, target_path: Path, voice: str, rate: str, pitch: str) -> Path:
        """Synthesize text into an audio file."""
