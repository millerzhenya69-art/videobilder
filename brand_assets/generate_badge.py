"""
generate_badge.py v2
Генерирует badge.png с реальным логотипом AtlantaVPN.
Ищет logo в brand_assets/, затем fallback на текстовый badge.
"""
from pathlib import Path

ASSETS_DIR = Path(__file__).parent
# Путь ASCII (для ffmpeg movie= filter)
_TMP_BADGE = Path("/tmp/atlanta_badge.png")


def make_badge(out_path: Path | None = None) -> Path:
    out_path = out_path or ASSETS_DIR / "badge.png"

    # Если badge уже собран — сразу возвращаем
    if out_path.exists() and out_path.stat().st_size > 1000:
        # Также копируем в /tmp для ffmpeg (ASCII путь)
        import shutil
        shutil.copy2(out_path, _TMP_BADGE)
        return _TMP_BADGE

    from PIL import Image, ImageDraw, ImageFont

    badge_w, badge_h = 320, 70
    badge = Image.new("RGBA", (badge_w, badge_h), (0, 0, 0, 0))
    draw  = ImageDraw.Draw(badge)

    # Тёмно-синий pill-фон с небольшим blur-shadow через rounded_rectangle
    draw.rounded_rectangle(
        [0, 0, badge_w - 1, badge_h - 1],
        radius=35,
        fill=(0, 55, 150, 220),
    )

    # Ищем логотип: сначала logo_a.png (оригинальный), потом Channel_VPN.png
    logo_path = None
    for candidate in [
        ASSETS_DIR / "logo_a.png",
        ASSETS_DIR / "Logo_VPN.png",
        ASSETS_DIR / "Channel_VPN.png",
        ASSETS_DIR / "Сhannel_VPN.png",
    ]:
        if candidate.exists():
            logo_path = candidate
            break

    text_x = 20
    if logo_path:
        try:
            logo_img = Image.open(logo_path).convert("RGBA")
            arr = __import__("numpy").array(logo_img)

            # Убираем белый фон (Channel_VPN) или тёмный (Logo_VPN)
            r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
            white_bg = (r > 240) & (g > 240) & (b > 240)
            dark_bg  = (r < 40) & (g < 40) & (b < 80)
            arr[white_bg | dark_bg, 3] = 0

            logo_img = Image.fromarray(arr)
            bbox = logo_img.getbbox()
            if bbox:
                logo_img = logo_img.crop(bbox)

            icon_size = 46
            logo_img = logo_img.resize((icon_size, icon_size), Image.LANCZOS)
            icon_x = 12
            icon_y = (badge_h - icon_size) // 2
            badge.paste(logo_img, (icon_x, icon_y), logo_img)
            text_x = icon_x + icon_size + 10
        except Exception:
            text_x = 20

    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28
        )
    except Exception:
        font = ImageFont.load_default()

    text_y = (badge_h - 32) // 2
    draw.text((text_x, text_y), "Atlanta VPN", font=font, fill=(255, 255, 255, 245))
    badge.save(out_path, "PNG")

    import shutil
    shutil.copy2(out_path, _TMP_BADGE)
    return _TMP_BADGE


if __name__ == "__main__":
    p = make_badge()
    print(f"Badge: {p}")
