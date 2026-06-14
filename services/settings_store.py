from dataclasses import dataclass


@dataclass(slots=True)
class UserVideoSettings:
    voice_gender: str = "male"
    voice: str = "ru-RU-DmitryNeural"
    speech_rate: str = "+8%"
    music_enabled: bool = True


class SettingsStore:
    """In-memory settings store; can be replaced by persistent per-user settings."""

    def __init__(self) -> None:
        self._items: dict[int, UserVideoSettings] = {}

    def get(self, user_id: int) -> UserVideoSettings:
        return self._items.setdefault(user_id, UserVideoSettings())

    def set_voice_gender(self, user_id: int, gender: str) -> UserVideoSettings:
        settings = self.get(user_id)
        settings.voice_gender = gender
        settings.voice = "ru-RU-SvetlanaNeural" if gender == "female" else "ru-RU-DmitryNeural"
        return settings
