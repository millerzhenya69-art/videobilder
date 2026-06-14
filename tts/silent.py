import asyncio
from pathlib import Path


class SilentTTSProvider:
    """Fallback TTS that creates silence with ffmpeg when external TTS is unavailable."""

    async def synthesize(self, text: str, target_path: Path, voice: str, rate: str, pitch: str) -> Path:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        seconds = max(5, min(30, len(text.split()) // 2))
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t",
            str(seconds),
            str(target_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(stderr.decode("utf-8", errors="ignore"))
        return target_path
