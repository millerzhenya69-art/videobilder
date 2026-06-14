import asyncio
from pathlib import Path

from config.settings import Settings
from services.history import HistoryRepository
from services.llm import ScriptGenerator


def test_fallback_script_generation(tmp_path: Path) -> None:
    async def run() -> None:
        settings = Settings(SQLITE_PATH=tmp_path / "test.sqlite3", GEMINI_API_KEY="")
        repo = HistoryRepository(settings.sqlite_path)
        await repo.init()
        script = await ScriptGenerator(settings, repo).generate("безопасность")
        assert script.scenes
        assert script.template_id
        assert "#atlantavpn" in script.hashtags

    asyncio.run(run())


def test_parse_gemini_json_response_with_markdown_fence() -> None:
    content = '```json\n{"title": "ok"}\n```'
    assert ScriptGenerator._parse_json_response(content) == {"title": "ok"}
