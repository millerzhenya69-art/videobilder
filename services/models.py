from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class SubtitleCue(BaseModel):
    start: float
    end: float
    text: str


class Scene(BaseModel):
    index: int
    title: str
    duration: float = Field(ge=0.5, le=8.0)
    voiceover: str
    on_screen_text: str
    visual_prompt: str
    asset_keywords: list[str]


class VideoScript(BaseModel):
    title: str
    template_id: str
    hook: str
    script: str
    voiceover: str
    on_screen_texts: list[str]
    publication_description: str
    hashtags: list[str]
    scenes: list[Scene]


class Asset(BaseModel):
    path: Path
    source_url: str = "local-generated"
    license: str = "generated-or-local-placeholder"
    kind: Literal["video", "image", "audio"]
    keywords: list[str] = Field(default_factory=list)


class GenerationResult(BaseModel):
    video_path: Path
    script: VideoScript
    assets: list[Asset]
    subtitle_path: Path | None = None
    voice_path: Path | None = None
