import asyncio
import logging
import os

import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import TelegramObject
from collections.abc import Awaitable, Callable
from typing import Any

from bot.handlers import router
from bot.middlewares import AccessMiddleware
from config.logging import setup_logging
from config.settings import get_settings
from services.history import HistoryRepository
from video_generation.pipeline import VideoGenerationPipeline

logger = logging.getLogger(__name__)


async def health(request: web.Request) -> web.Response:
    return web.Response(text="VideoBilder OK", content_type="text/plain")


async def _inject_dependencies(
    handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
    event: TelegramObject,
    data: dict[str, Any],
) -> Any:
    data["pipeline"] = data["dispatcher"]["pipeline"]
    data["history_repo"] = data["dispatcher"]["history_repo"]
    return await handler(event, data)


async def self_ping_loop(url: str, interval: int = 840) -> None:
    """
    Пингует собственный healthcheck каждые 14 минут.
    Render усыпляет free-инстанс после 15 минут тишины —
    при интервале 840 сек (14 мин) бот всегда остаётся активным.
    """
    # Даём боту 15 сек на старт перед первым пингом
    await asyncio.sleep(15)
    logger.info("Self-ping started → %s (every %ds)", url, interval)
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    logger.debug("Self-ping %s → %s", url, resp.status)
            except Exception as exc:
                logger.warning("Self-ping failed: %s", exc)
            await asyncio.sleep(interval)


async def run_bot() -> None:
    settings = get_settings()
    setup_logging(settings.logs_dir)

    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    history_repo = HistoryRepository(settings.sqlite_path)
    await history_repo.init()

    pipeline = VideoGenerationPipeline(settings, history_repo)

    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher()
    dispatcher["pipeline"] = pipeline
    dispatcher["history_repo"] = history_repo

    dispatcher.message.middleware(AccessMiddleware(settings.allowed_users))
    dispatcher.update.outer_middleware(_inject_dependencies)
    dispatcher.include_router(router)

    # Healthcheck server (Railway + Render)
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    logger.info("Healthcheck server started on port %s", port)

    # Self-ping: берём URL из env или строим из SERVICE_URL / RENDER_EXTERNAL_URL
    ping_url = os.getenv("SELF_PING_URL") or os.getenv("RENDER_EXTERNAL_URL") or ""
    if ping_url and not ping_url.startswith("http"):
        ping_url = f"https://{ping_url}"
    if ping_url:
        asyncio.create_task(self_ping_loop(ping_url.rstrip("/") + "/health"))
    else:
        logger.warning(
            "Self-ping disabled: set SELF_PING_URL or RENDER_EXTERNAL_URL env var"
        )

    # FIX: drop_pending_updates предотвращает конфликт инстансов при редеплое
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Starting bot polling")

    try:
        await dispatcher.start_polling(bot, drop_pending_updates=True)
    finally:
        await runner.cleanup()
        await bot.session.close()


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
