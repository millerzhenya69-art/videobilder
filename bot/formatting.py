from services.models import Asset, VideoScript


def format_script(script: VideoScript) -> str:
    hashtags = " ".join(script.hashtags)
    scenes = "\n".join(
        f"{scene.index}. {scene.title} ({scene.duration:.1f}с): {scene.on_screen_text}"
        for scene in script.scenes
    )
    return (
        f"🎬 <b>{script.title}</b>\n\n"
        f"<b>Хук:</b> {script.hook}\n\n"
        f"<b>Сцены:</b>\n{scenes}\n\n"
        f"<b>Описание:</b> {script.publication_description}\n\n"
        f"<b>Хештеги:</b> {hashtags}"
    )


def format_assets(assets: list[Asset]) -> str:
    lines = ["<b>Использованные ассеты:</b>"]
    for asset in assets:
        lines.append(f"• {asset.kind}: {asset.path} ({asset.license})")
    return "\n".join(lines)
