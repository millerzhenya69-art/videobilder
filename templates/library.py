from dataclasses import dataclass
from random import SystemRandom


@dataclass(frozen=True)
class VideoTemplate:
    id: str
    name: str
    angle: str
    hook_pattern: str
    scene_pattern: tuple[str, ...]
    cta_style: str
    asset_keywords: tuple[str, ...]


TEMPLATES: tuple[VideoTemplate, ...] = (
    VideoTemplate("myth_check", "Проверка мифа", "развенчание популярного мифа", "Правда ли, что {myth}?", ("миф", "эксперимент", "результат", "мягкий CTA"), "ссылка в описании", ("phone", "internet", "security")),
    VideoTemplate("service_access", "Не открывается сервис", "быстрый доступ к сервису", "Если у тебя не открывается {service}", ("ошибка", "включение VPN", "доступ", "CTA"), "инструкция в профиле", ("smartphone", "app", "wifi")),
    VideoTemplate("digital_safety", "Цифровая безопасность", "приватность в публичном Wi-Fi", "Не подключайся к Wi‑Fi, пока не сделаешь это", ("риск", "защита", "проверка", "CTA"), "подробности в Telegram", ("public wifi", "coffee shop", "privacy")),
    VideoTemplate("hidden_setting", "Скрытая настройка", "полезная настройка смартфона", "90% людей не знают об этой настройке", ("хук", "путь в настройках", "VPN", "результат"), "сохрани и проверь", ("phone settings", "technology", "hands")),
    VideoTemplate("travel_tip", "Совет в поездке", "интернет в путешествии", "Перед поездкой включи это заранее", ("ситуация", "решение", "экономия времени", "CTA"), "забери инструкцию", ("airport", "travel", "phone")),
    VideoTemplate("speed_test", "Тест скорости", "сравнение до/после", "Я проверил скорость с VPN и без", ("до", "тест", "после", "вывод"), "ссылка в описании", ("speed test", "internet", "laptop")),
    VideoTemplate("subscription_save", "Экономия на сервисах", "цифровой лайфхак", "Этот способ многие пропускают", ("проблема", "локация", "проверка", "CTA"), "подробности в Telegram", ("streaming", "payment", "phone")),
    VideoTemplate("privacy_story", "История приватности", "короткий сторителлинг", "Я понял это только после одной ошибки", ("история", "риск", "AtlantaVPN", "урок"), "инструкция в профиле", ("cyber security", "night phone", "lock")),
    VideoTemplate("three_sites", "3 полезных сайта", "подборка полезных сайтов", "Три сайта, которые стоит открыть через VPN", ("сайт 1", "сайт 2", "сайт 3", "CTA"), "сохрани подборку", ("websites", "browser", "desk")),
    VideoTemplate("blocked_news", "Доступ к информации", "доступ к источникам", "Не знаю, сколько это ещё будет работать", ("ограничение", "подключение", "результат", "CTA"), "ссылка в описании", ("news", "phone", "city")),
    VideoTemplate("work_remote", "Удалённая работа", "безопасная работа из кафе", "Если работаешь не из дома — проверь это", ("кафе", "опасность", "VPN", "спокойная работа"), "подробности в Telegram", ("remote work", "coffee laptop", "wifi")),
    VideoTemplate("gaming_ping", "Игровой пинг", "стабильность подключения", "Пинг прыгает? Проверь один момент", ("лаг", "маршрут", "VPN", "результат"), "инструкция в профиле", ("gaming", "router", "monitor")),
    VideoTemplate("family_security", "Семейная безопасность", "защита устройств семьи", "Покажи это родителям", ("простая угроза", "объяснение", "VPN", "CTA"), "отправь близким", ("family phone", "home wifi", "security")),
    VideoTemplate("public_wifi", "Публичный Wi‑Fi", "опасность открытых сетей", "Бесплатный Wi‑Fi может стоить дорого", ("подключение", "перехват", "защита", "CTA"), "подробности в Telegram", ("free wifi", "mall", "phone")),
    VideoTemplate("browser_error", "Ошибка браузера", "решение проблемы доступа", "Если видишь эту ошибку — попробуй так", ("ошибка", "причина", "AtlantaVPN", "результат"), "ссылка в описании", ("browser error", "laptop", "internet")),
    VideoTemplate("one_minute_setup", "Настройка за минуту", "быстрый онбординг", "Настроил VPN быстрее, чем за минуту", ("таймер", "шаги", "проверка", "CTA"), "инструкция в профиле", ("timer", "phone app", "fast")),
    VideoTemplate("anti_tracking", "Антитрекинг", "как меньше оставлять следов", "Сайты узнают о тебе больше, чем кажется", ("факт", "пример", "VPN", "CTA"), "сохрани чеклист", ("tracking", "privacy", "browser")),
    VideoTemplate("student_lifehack", "Лайфхак студента", "полезный инструмент для учебы", "Студенты часто забывают про это", ("задача", "ресурс", "VPN", "результат"), "подробности в Telegram", ("student", "library", "laptop")),
    VideoTemplate("creator_stack", "Стек креатора", "инструменты для контента", "Креаторам это экономит часы", ("проблема", "сервисы", "VPN", "CTA"), "ссылка в описании", ("content creator", "editing", "phone")),
    VideoTemplate("weekly_checklist", "Еженедельный чеклист", "цифровая гигиена", "Проверь эти 4 пункта раз в неделю", ("пункт 1", "пункт 2", "VPN", "CTA"), "сохрани чеклист", ("checklist", "security", "phone")),
)


def pick_template() -> VideoTemplate:
    return SystemRandom().choice(TEMPLATES)
