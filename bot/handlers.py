"""
handlers.py — исправленная логика выбора шаблона.

Баг: при свободном тексте бот показывал кнопки шаблона
И тут же сразу генерировал без ожидания нажатия.

Фикс: при свободном тексте — ТОЛЬКО показываем кнопки и сохраняем тему
в callback_data. Генерация запускается ТОЛЬКО после нажатия кнопки.

Тема передаётся через callback_data: "style:dark_planet:тема"
"""
import logging
import urllib.parse

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from services.history import HistoryRepository
from services.settings_store import SettingsStore
from templates.library import TEMPLATES
from video_generation.pipeline import VideoGenerationPipeline

logger = logging.getLogger(__name__)
router = Router()
settings_store = SettingsStore()

HELP_TEXT = (
    "🎬 <b>AtlantaVPN Video Bot</b>\n\n"
    "<b>Команды:</b>\n"
    "• /generate — видео (авто-тема)\n"
    "• /generate [тема] — видео по теме:\n"
    "  <code>/generate публичный wifi опасен</code>\n"
    "• /a [тема] — шаблон A (тёмный + синяя планета)\n"
    "• /b [тема] — шаблон B (фиолетовый + телефон)\n"
    "• /templates — список шаблонов\n"
    "• /history — последние генерации\n\n"
    "💡 Или просто напиши тему — выберешь шаблон и я сделаю видео!"
)

# Максимальная длина темы в callback_data (Telegram лимит 64 байт на весь data)
_MAX_TOPIC_IN_CB = 40


def _style_keyboard(topic: str | None = None) -> InlineKeyboardMarkup:
    """Кнопки выбора шаблона. Тема кодируется в callback_data."""
    topic_part = ""
    if topic:
        # URL-encode чтобы не сломать разбор по ":"
        encoded = urllib.parse.quote(topic[:_MAX_TOPIC_IN_CB], safe="")
        topic_part = f":{encoded}"
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🌑 Шаблон A",
            callback_data=f"style:dark_planet{topic_part}",
        ),
        InlineKeyboardButton(
            text="🟣 Шаблон B",
            callback_data=f"style:gradient_phone{topic_part}",
        ),
    ]])


@router.message(Command("start"))
async def start(message: Message) -> None:
    await message.answer(HELP_TEXT, parse_mode="HTML")


@router.message(Command("help"))
async def help_cmd(message: Message) -> None:
    await message.answer(HELP_TEXT, parse_mode="HTML")


@router.message(Command("generate"))
async def generate(
    message: Message,
    command: CommandObject,
    pipeline: VideoGenerationPipeline,
) -> None:
    topic = command.args.strip() if command.args else None
    await _do_generate(message, pipeline, topic, visual_style=None)


@router.message(Command("a"))
async def generate_a(
    message: Message,
    command: CommandObject,
    pipeline: VideoGenerationPipeline,
) -> None:
    topic = command.args.strip() if command.args else None
    await _do_generate(message, pipeline, topic, visual_style="dark_planet")


@router.message(Command("b"))
async def generate_b(
    message: Message,
    command: CommandObject,
    pipeline: VideoGenerationPipeline,
) -> None:
    topic = command.args.strip() if command.args else None
    await _do_generate(message, pipeline, topic, visual_style="gradient_phone")


@router.message(Command("templates"))
async def templates_cmd(message: Message) -> None:
    text = "<b>Шаблоны сценариев:</b>\n" + "\n".join(
        f"• <code>{t.id}</code> — {t.name}: {t.angle}" for t in TEMPLATES
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("history"))
async def history_cmd(message: Message, history_repo: HistoryRepository) -> None:
    rows = await history_repo.latest(limit=10)
    if not rows:
        await message.answer("История пустая — создай первое видео командой /generate")
        return
    text = "<b>Последние генерации:</b>\n" + "\n".join(
        f"• {row['created_at'][:16]}: {row['title']}" for row in rows
    )
    await message.answer(text, parse_mode="HTML")


@router.callback_query(F.data.startswith("style:"))
async def style_callback(
    callback: CallbackQuery,
    pipeline: VideoGenerationPipeline,
) -> None:
    """
    Обрабатывает нажатие кнопки выбора шаблона.
    callback_data формат: "style:<visual_style>" или "style:<visual_style>:<encoded_topic>"
    """
    await callback.answer()

    parts = callback.data.split(":", 2)
    visual_style = parts[1] if len(parts) > 1 else "dark_planet"
    topic: str | None = None
    if len(parts) > 2:
        try:
            topic = urllib.parse.unquote(parts[2])
        except Exception:
            topic = None

    # Убираем кнопки из исходного сообщения
    if callback.message:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await _do_generate(callback.message, pipeline, topic=topic, visual_style=visual_style)


@router.message(F.text & ~F.text.startswith("/"))
async def free_text(message: Message) -> None:
    """
    Свободный текст — показываем кнопки выбора шаблона.
    Генерация НЕ запускается здесь — только после нажатия кнопки.
    """
    topic = message.text.strip() if message.text else None
    if not topic or len(topic) < 2:
        await message.answer(HELP_TEXT, parse_mode="HTML")
        return

    await message.answer(
        f"🎬 Тема: <i>{topic}</i>\n\nКакой шаблон использовать?",
        parse_mode="HTML",
        reply_markup=_style_keyboard(topic),
    )


async def _do_generate(
    message: Message,
    pipeline: VideoGenerationPipeline,
    topic: str | None,
    visual_style: str | None,
) -> None:
    style_label = {
        "dark_planet": "🌑 A (тёмный)",
        "gradient_phone": "🟣 B (фиолетовый)",
    }.get(visual_style or "", "🔀 авто")

    topic_str = f" — <i>{topic}</i>" if topic else ""
    status = await message.answer(
        f"⏳ Генерирую видео {style_label}{topic_str}\n"
        "Сценарий → ассеты → озвучка → монтаж (~1-2 мин)",
        parse_mode="HTML",
    )
    try:
        result = await pipeline.generate(
            topic=topic,
            visual_style=visual_style,
        )
        await message.answer_video(
            FSInputFile(result.video_path),
            caption=(
                f"🎬 <b>{result.script.title}</b>\n\n"
                f"{result.script.publication_description}\n\n"
                f"{' '.join(result.script.hashtags)}"
            ),
            parse_mode="HTML",
        )
        await status.delete()
    except Exception as exc:
        logger.exception("Generation failed: topic=%s style=%s", topic, visual_style)
        await status.edit_text(
            f"❌ Ошибка генерации.\n<code>{exc}</code>",
            parse_mode="HTML",
        )
