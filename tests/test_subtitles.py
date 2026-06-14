from pathlib import Path

from services.models import Scene
from subtitles.ass import build_cues, seconds_to_ass, write_ass


def test_seconds_to_ass() -> None:
    assert seconds_to_ass(65.25) == "0:01:05.25"


def test_write_ass(tmp_path: Path) -> None:
    scenes = [
        Scene(
            index=1,
            title="Hook",
            duration=1.5,
            voiceover="voice",
            on_screen_text="Текст",
            visual_prompt="phone",
            asset_keywords=["phone"],
        )
    ]
    cues = build_cues(scenes)
    target = write_ass(cues, tmp_path / "sub.ass")
    assert target.exists()
    assert "Текст" in target.read_text(encoding="utf-8")
