from pathlib import Path

from services.models import Scene, SubtitleCue


def build_cues(scenes: list[Scene]) -> list[SubtitleCue]:
    current = 0.0
    cues: list[SubtitleCue] = []
    for scene in scenes:
        end = current + scene.duration
        cues.append(SubtitleCue(start=current, end=end, text=scene.on_screen_text))
        current = end
    return cues


def seconds_to_ass(value: float) -> str:
    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    seconds = int(value % 60)
    centiseconds = int((value - int(value)) * 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def write_ass(cues: list[SubtitleCue], target_path: Path) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,78,&H00FFFFFF,&H0000D7FF,&H00111111,&HAA000000,-1,0,0,0,100,100,0,0,1,5,2,2,72,72,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for cue in cues:
        text = cue.text.replace("\n", "\\N")
        events.append(
            f"Dialogue: 0,{seconds_to_ass(cue.start)},{seconds_to_ass(cue.end)},Default,,0,0,0,,{{\\fad(120,120)}}{text}"
        )
    target_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return target_path
