import json
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from services.models import GenerationResult, VideoScript


class HistoryRepository:
    def __init__(self, sqlite_path: Path) -> None:
        self.sqlite_path = sqlite_path

    async def init(self) -> None:
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.sqlite_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS generations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    title TEXT NOT NULL,
                    template_id TEXT NOT NULL,
                    video_path TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            await db.commit()

    async def save(self, result: GenerationResult) -> None:
        payload = result.model_dump_json()
        async with aiosqlite.connect(self.sqlite_path) as db:
            await db.execute(
                """
                INSERT INTO generations(created_at, title, template_id, video_path, payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(UTC).isoformat(),
                    result.script.title,
                    result.script.template_id,
                    str(result.video_path),
                    payload,
                ),
            )
            await db.commit()

    async def latest(self, limit: int = 10) -> list[dict[str, str]]:
        async with aiosqlite.connect(self.sqlite_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT created_at, title, template_id, video_path
                FROM generations
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def used_scripts(self, limit: int = 30) -> list[VideoScript]:
        async with aiosqlite.connect(self.sqlite_path) as db:
            cursor = await db.execute(
                "SELECT payload FROM generations ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            rows = await cursor.fetchall()
        scripts: list[VideoScript] = []
        for (payload,) in rows:
            data = json.loads(payload)
            scripts.append(VideoScript.model_validate(data["script"]))
        return scripts
