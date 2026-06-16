"""
ScriptGenerator — переработанный промпт под референсный стиль AtlantaVPN.

Референс (referral_1x1_ru.mp4):
  • Крупный заголовок сверху — сразу суть
  • Один ключевой визуальный элемент по центру (скриншот приложения / иконка)
  • Минимум текста на экране — каждое слово на вес золота
  • Динамика: короткие сцены (2-4 сек), резкие переходы
  • Структура: ХУК (1-3 сек) → БОЛЬ (2-4 сек) → РЕШЕНИЕ (3-5 сек) → CTA (2-3 сек)
  • Voiceover: разговорный стиль, без пафоса
"""

import json
import logging
from random import SystemRandom
from typing import Any

import aiohttp
from pydantic import ValidationError

from config.settings import Settings
from services.history import HistoryRepository
from services.models import Scene, VideoScript
from templates.library import VideoTemplate, pick_template

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SYSTEM_PROMPT = """Ты профессиональный сценарист коротких вертикальных видео для TikTok/Reels/YouTube Shorts.
Ты пишешь нативный контент для AtlantaVPN — VPN-сервиса для русскоязычной аудитории.

СТИЛЬ (строго по образцу):
• ХУК — первые 2-3 секунды: один громкий тезис, вопрос или провокация. Зритель должен остановиться.
• Короткие сцены: 2-4 секунды каждая. Без затяжных объяснений.
• On-screen текст: МАКСИМУМ 5-7 слов на экране. Только суть. Крупно.
• Voiceover: разговорный, живой. Как будто друг объясняет. Без "данный продукт".
• Без агрессивной рекламы. Нативно, полезно, с иронией если уместно.
• CTA мягкий: "ссылка в шапке профиля", "в описании", "сохрани чтобы не потерять".

ЗАПРЕЩЕНО: обещать обход законов, гарантировать анонимность, агрессивные продажи.

Отвечай ТОЛЬКО валидным JSON без markdown-блоков и без пояснений."""


class ScriptGenerator:
    def __init__(self, settings: Settings, history: HistoryRepository) -> None:
        self.settings = settings
        self.history = history

    async def generate(self, topic: str | None = None) -> VideoScript:
        template = pick_template()
        used = await self.history.used_scripts(limit=20)
        if not self.settings.gemini_api_key:
            return self._fallback_script(template, topic)
        prompt = self._build_prompt(template, topic, used)
        try:
            content = await self._generate_with_gemini(prompt)
            data = self._parse_json_response(content)
            data["template_id"] = template.id
            script = VideoScript.model_validate(data)
            logger.info("Generated script: %s (%d scenes)", script.title, len(script.scenes))
            return script
        except (aiohttp.ClientError, json.JSONDecodeError, ValidationError, KeyError, ValueError) as exc:
            logger.warning("Gemini generation failed, using fallback: %s", exc)
            return self._fallback_script(template, topic)

    async def _generate_with_gemini(self, prompt: str) -> str:
        url = GEMINI_API_URL.format(model=self.settings.gemini_model)
        payload: dict[str, Any] = {
            "systemInstruction": {
                "parts": [{"text": SYSTEM_PROMPT}]
            },
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": self.settings.llm_temperature,
                "responseMimeType": "application/json",
            },
        }
        params = {"key": self.settings.gemini_api_key}
        timeout = aiohttp.ClientTimeout(total=90)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, params=params, json=payload) as response:
                response_text = await response.text()
                if response.status >= 400:
                    raise ValueError(f"Gemini API error {response.status}: {response_text[:500]}")
                data = json.loads(response_text)
        candidates = data.get("candidates") or []
        if not candidates:
            raise ValueError("Gemini response has no candidates")
        parts = candidates[0].get("content", {}).get("parts") or []
        text = "".join(part.get("text", "") for part in parts)
        if not text.strip():
            raise ValueError("Gemini response text is empty")
        return text

    @staticmethod
    def _parse_json_response(content: str) -> dict[str, Any]:
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = stripped.removeprefix("```json").removeprefix("```").strip()
            stripped = stripped.removesuffix("```").strip()
        return json.loads(stripped)

    def _build_prompt(
        self,
        template: VideoTemplate,
        topic: str | None,
        used: list[VideoScript],
    ) -> str:
        used_titles = [item.title for item in used]
        return json.dumps(
            {
                "task": (
                    "Напиши сценарий вертикального видео 9:16, длина 15-25 секунд, для AtlantaVPN. "
                    "Аудитория: Россия и СНГ, 18-35 лет. Платформа: TikTok / Instagram Reels / YouTube Shorts."
                ),
                "topic": topic or "выбери актуальный угол сам — что-то что зацепит прямо сейчас",
                "template": {
                    "id": template.id,
                    "name": template.name,
                    "angle": template.angle,
                    "hook_pattern": template.hook_pattern,
                },
                "video_style_reference": (
                    "Как в лучших роликах Wallet/TON или банковских приложений: "
                    "градиентный фон, крупный заголовок сверху, "
                    "один ключевой объект по центру (телефон с приложением, иконка, цифра), "
                    "минимум текста — максимум удара."
                ),
                "structure": {
                    "scene_1_hook": "2-3 сек — один тезис, вопрос или факт. Зритель должен остановиться.",
                    "scene_2_pain": "3-4 сек — проблема близко и знакома. Без воды.",
                    "scene_3_solution": "4-5 сек — AtlantaVPN решает. Показываем как.",
                    "scene_4_result": "3-4 сек — конкретный результат/цифра/ощущение.",
                    "scene_5_cta": "2-3 сек — мягкий призыв. Ссылка в профиле.",
                },
                "on_screen_text_rules": [
                    "МАКСИМУМ 6 слов на сцену",
                    "Только caps или Title Case для заголовков",
                    "Без длинных предложений — только суть",
                    "Хук должен быть провокационным или вопросом",
                ],
                "avoid_titles": used_titles,
                "required_json_schema": {
                    "title": "str — заголовок видео (для внутреннего использования)",
                    "hook": "str — первая фраза которую скажет голос",
                    "script": "str — полный текст voiceover",
                    "voiceover": "str — финальный текст для синтеза речи, разговорный стиль",
                    "on_screen_texts": ["str — тексты на экране по сценам"],
                    "publication_description": "str — описание для публикации с эмодзи",
                    "hashtags": ["str"],
                    "scenes": [
                        {
                            "index": "int 1-5",
                            "title": "str — внутреннее название сцены (хук/боль/решение/результат/cta)",
                            "duration": "float 2.0-5.0 секунд",
                            "voiceover": "str — что говорит голос в этой сцене",
                            "on_screen_text": "str — МАКСИМУМ 6 слов крупно на экране",
                            "visual_prompt": "str — описание визуала для поиска в Pexels (English)",
                            "asset_keywords": ["str — 2-3 English keywords for Pexels search"],
                        }
                    ],
                },
                "constraints": [
                    "Строго 4-5 сцен",
                    "Общая длина 15-25 секунд",
                    "on_screen_text не более 6 слов",
                    "Хук в первые 3 секунды",
                    "Мягкий CTA без давления",
                    "Не повторять темы из avoid_titles",
                    "asset_keywords на английском для Pexels API",
                ],
            },
            ensure_ascii=False,
        )

    def _fallback_script(self, template: VideoTemplate, topic: str | None) -> VideoScript:
        rng = SystemRandom()
        # Если topic выглядит как template_id (нет пробелов, содержит _)
        # — заменяем на человекочитаемую тему
        _template_to_topic = {
            "digital_safety": "публичный Wi-Fi",
            "gaming_ping": "пинг в играх",
            "family_security": "безопасность семьи",
            "privacy_story": "приватность в сети",
            "work_remote": "удалённая работа",
            "speed_test": "скорость интернета",
            "blocked_news": "заблокированные сайты",
            "public_wifi": "публичный Wi-Fi",
            "travel_tip": "интернет в путешествии",
            "subscription_save": "сервисы за рубежом",
            "hidden_setting": "настройки смартфона",
            "anti_tracking": "слежка в интернете",
            "student_lifehack": "учёба онлайн",
            "creator_stack": "работа контент-мейкера",
            "weekly_checklist": "цифровая безопасность",
            "browser_error": "ошибки браузера",
            "three_sites": "полезные сайты",
            "one_minute_setup": "быстрая настройка VPN",
        }
        if topic and "_" in topic and " " not in topic:
            topic = _template_to_topic.get(topic, topic.replace("_", " "))

        subject = topic or rng.choice(
            ["публичный Wi-Fi", "потоковые сервисы", "приватность в сети", "работа за рубежом"]
        )
        scenes = [
            Scene(
                index=1,
                title="Хук",
                duration=2.5,
                voiceover=f"Ты точно не делаешь это при использовании {subject}?",
                on_screen_text="ТЫ ДЕЛАЕШЬ ЭТО?",
                visual_prompt="person looking at smartphone surprised",
                asset_keywords=["phone", "surprised", "internet"],
            ),
            Scene(
                index=2,
                title="Боль",
                duration=3.5,
                voiceover=f"Без защиты в {subject} твои данные видны всем вокруг.",
                on_screen_text="ТВОИ ДАННЫЕ ОТКРЫТЫ",
                visual_prompt="hacker cyber security threat phone",
                asset_keywords=["cyber", "security", "hacker"],
            ),
            Scene(
                index=3,
                title="Решение",
                duration=4.5,
                voiceover="AtlantaVPN шифрует соединение за секунду. Один клик — и ты в безопасности.",
                on_screen_text="ОДИН КЛИК — ЗАЩИТА",
                visual_prompt="vpn app shield protection smartphone",
                asset_keywords=["vpn", "shield", "phone app"],
            ),
            Scene(
                index=4,
                title="Результат",
                duration=3.5,
                voiceover="Всё работает как обычно — просто безопасно.",
                on_screen_text="РАБОТАЕТ. БЕЗОПАСНО.",
                visual_prompt="person relaxed using phone cafe",
                asset_keywords=["relax", "phone", "cafe"],
            ),
            Scene(
                index=5,
                title="CTA",
                duration=2.5,
                voiceover="Ссылка в шапке профиля. Не откладывай.",
                on_screen_text="ССЫЛКА В ПРОФИЛЕ",
                visual_prompt="call to action arrow pointing up",
                asset_keywords=["arrow", "profile", "link"],
            ),
        ]
        voiceover = " ".join(scene.voiceover for scene in scenes)
        return VideoScript(
            title=f"AtlantaVPN: {subject}",
            template_id=template.id,
            hook=scenes[0].voiceover,
            script=" → ".join(scene.title for scene in scenes),
            voiceover=voiceover,
            on_screen_texts=[scene.on_screen_text for scene in scenes],
            publication_description=f"🔒 {subject} без риска. AtlantaVPN — попробуй бесплатно.",
            hashtags=["#vpn", "#atlantavpn", "#безопасность", "#лайфхак", "#shorts"],
            scenes=scenes,
        )
