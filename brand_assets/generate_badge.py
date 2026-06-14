"""
Запускается один раз при старте бота (или вручную).
Генерирует badge.png из логотипа.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ASSETS_DIR = Path(__file__).parent

def make_badge(out_path: Path | None = None) -> Path:
    out_path = out_path or ASSETS_DIR / "badge.png"
    if out_path.exists():
        return out_path

    badge_w, badge_h = 320, 70
    badge = Image.new("RGBA", (badge_w, badge_h), (0, 0, 0, 0))
    draw  = ImageDraw.Draw(badge)
    draw.rounded_rectangle([0, 0, badge_w-1, badge_h-1], radius=35, fill=(0, 68, 170, 210))

    logo_path = ASSETS_DIR / "logo_a.png"
    if logo_path.exists():
        logo = Image.open(logo_path).convert("RGBA")
        icon_size = 46
        logo = logo.resize((icon_size, icon_size), Image.LANCZOS)
        icon_x = 12
        icon_y = (badge_h - icon_size) // 2
        badge.paste(logo, (icon_x, icon_y), logo)
        text_x = icon_x + icon_size + 10
    else:
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
    return out_path

if __name__ == "__main__":
    p = make_badge()
    print(f"Badge: {p}")
