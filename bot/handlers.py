import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import FSInputFile, Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

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
    "• /generate — видео (авто-тема, чередование шаблонов)\n"
    "• /generate [тема] — видео по теме:\n"
    "  <code>/generate публичный wifi опасен</code>\n"
    "• /a [тема] — шаблон A (тёмный + синяя планета)\n"
    "• /b [тема] — шаблон B (фиолетовый + телефон)\n"
    "• /templates — список шаблонов\n"
    "• /history — последние генерации\n\n"
    "💡 Или просто напиши тему — сделаю видео!"
)


def _style_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🌑 Шаблон A", callback_data="style:dark_planet"),
        InlineKeyboardButton(text="🟣 Шаблон B", callback_data="style:gradient_phone"),
    ]])


@router.message(Command("start"))
async def start(message: Message) -> None:
    await message.answer(HELP_TEXT, parse_mode="HTML")


@router.message(Command("help"))
async def help_cmd(message: Message) -> None:
    await message.answer(HELP_TEXT, parse_mode="HTML")


@router.message(Command("generate"))
async def generate(message: Message, command: CommandObject,
                   pipeline: VideoGenerationPipeline) -> None:
    topic = command.args.strip() if command.args else None
    await _do_generate(message, pipeline, topic, visual_style=None)


@router.message(Command("a"))
async def generate_a(message: Message, command: CommandObject,
                     pipeline: VideoGenerationPipeline) -> None:
    topic = command.args.strip() if command.args else None
    await _do_generate(message, pipeline, topic, visual_style="dark_planet")


@router.message(Command("b"))
async def generate_b(message: Message, command: CommandObject,
                     pipeline: VideoGenerationPipeline) -> None:
    topic = command.args.strip() if command.args else None
    await _do_generate(message, pipeline, topic, visual_style="gradient_phone")


@router.message(Command("templates"))
async def templates(message: Message) -> None:
    text = "<b>Шаблоны сценариев:</b>\n" + "\n".join(
        f"• <code>{t.id}</code> — {t.name}: {t.angle}" for t in TEMPLATES
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("history"))
async def history(message: Message, history_repo: HistoryRepository) -> None:
    rows = await history_repo.latest(limit=10)
    if not rows:
        await message.answer("История пустая — создай первое видео командой /generate")
        return
    text = "<b>Последние генерации:</b>\n" + "\n".join(
        f"• {row['created_at'][:16]}: {row['title']}" for row in rows
    )
    await message.answer(text, parse_mode="HTML")


@router.callback_query(F.data.startswith("style:"))
async def style_callback(callback: CallbackQuery,
                          pipeline: VideoGenerationPipeline) -> None:
    style = callback.data.split(":", 1)[1]
    await callback.answer()
    await _do_generate(callback.message, pipeline, topic=None, visual_style=style)


@router.message(F.text & ~F.text.startswith("/"))
async def free_text(message: Message, pipeline: VideoGenerationPipeline) -> None:
    topic = message.text.strip() if message.text else None
    if not topic or len(topic) < 3:
        await message.answer(HELP_TEXT, parse_mode="HTML")
        return
    # Показываем кнопки выбора шаблона
    await message.answer(
        f"🎬 Тема: <i>{topic}</i>\nКакой шаблон использовать?",
        parse_mode="HTML",
        reply_markup=_style_keyboard(),
    )
    # Сохраняем тему в данные callback через pipeline (упрощённо — генерируем сразу auto)
    await _do_generate(message, pipeline, topic, visual_style=None)


async def _do_generate(
    message: Message,
    pipeline: VideoGenerationPipeline,
    topic: str | None,
    visual_style: str | None,
) -> None:
    style_label = {"dark_planet": "🌑 A", "gradient_phone": "🟣 B"}.get(visual_style or "", "🔀 авто")
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
