"""
FFmpegRenderer v9 — брендовые ассеты AtlantaVPN.

Изменения vs v8:
  • Реальный badge через movie= filter (PNG с прозрачностью из /tmp/atlanta_badge.png)
    Fallback на drawtext если badge недоступен
  • Новый метод _badge_overlay() — встраивает badge через filter_complex
  • Шаблон A (_a_video, _a_solid): badge через overlay, текст ниже badge
  • Финальный слайд: использует IMG_5778.MP4 (официальный CTA-ролик)
    если файл доступен в brand_assets/; иначе сгенерированный
  • Текст заголовков: уменьшен и обёрнут жёстче (12 симв.) → нет обрезки справа
  • Sub-текст: fontsize 40 (было 46) + truncate 42 симв. → влезает целиком
  • Все encode-флаги сохранены из v8 (ultrafast для сегментов, veryfast для mix)
"""
from __future__ import annotations

import asyncio
import gc
import logging
import shlex
from pathlib import Path

from brand_assets.generate_badge import make_badge
from config.settings import Settings
from services.models import Asset, VideoScript
from subtitles.ass import build_cues, write_ass

logger = logging.getLogger(__name__)

_A_BG = [
    ("0x07070f", "0x0d1a2e"),
    ("0x08080f", "0x0a1828"),
    ("0x070a14", "0x0b1e3a"),
    ("0x060810", "0x091522"),
    ("0x050810", "0x0c1f35"),
]
_B_BG = [
    ("0x2d0b6b", "0x6a21d4"),
    ("0x1a0a4a", "0x5b16c4"),
    ("0x250960", "0x7c3aed"),
    ("0x1e0850", "0x6d28d9"),
    ("0x2a0a70", "0x7c3aed"),
]

# Ищем официальный CTA-ролик для финального слайда
_BRAND_ASSETS_DIR = Path(__file__).parent.parent / "brand_assets"
_OFFICIAL_CTA_NAMES = ["IMG_5778.MP4", "img_5778.mp4", "cta_final.mp4", "official_cta.mp4"]

_SEG_ENCODE = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
               "-threads", "1", "-pix_fmt", "yuv420p", "-bufsize", "1500k", "-maxrate", "2000k"]
# v10: mix переведён на ultrafast — на Render free-tier (512MB) именно финальный
# concat+reencode+audio-mix шаг чаще всего убивает процесс по OOM, так как к этому
# моменту уже накоплен мусор от 5 сегментов. veryfast давал чуть лучшую картинку,
# но стабильность важнее на бесплатном плане.
_MIX_ENCODE = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "24",
               "-threads", "1", "-pix_fmt", "yuv420p", "-bufsize", "1500k", "-maxrate", "2500k"]

# Путь к badge (ASCII, для ffmpeg movie= filter)
_BADGE_TMP = Path("/tmp/atlanta_badge.png")


class FFmpegRenderer:
    def __init__(self, settings: Settings) -> None:
        self.settings    = settings
        self.output_dir  = settings.cache_dir / "videos"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._font       = self._find_font()
        self._badge_path: Path | None = None
        self._cta_video:  Path | None = self._find_cta_video()

    def _find_cta_video(self) -> Path | None:
        """Ищем официальный CTA-ролик в brand_assets/."""
        for name in _OFFICIAL_CTA_NAMES:
            p = _BRAND_ASSETS_DIR / name
            if p.exists() and p.stat().st_size > 10_000:
                logger.info("Official CTA video found: %s", p)
                return p
        return None

    # ── Public ────────────────────────────────────────────────────────────────

    async def render(
        self,
        script:       VideoScript,
        assets:       list[Asset],
        voice_path:   Path | None,
        visual_style: str = "dark_planet",
    ) -> tuple[Path, Path]:
        safe   = "".join(c for c in script.title.lower() if c.isalnum() or c in "-_")[:48]
        target = self.output_dir / f"{safe or 'video'}.mp4"

        subtitle_path = self.output_dir / f"{target.stem}.ass"
        write_ass(build_cues(script.scenes), subtitle_path)

        # Подготавливаем badge (реальный логотип)
        try:
            self._badge_path = make_badge()
            if not (self._badge_path.exists() and self._badge_path.stat().st_size > 500):
                self._badge_path = None
        except Exception as e:
            logger.warning("Badge generation failed: %s", e)
            self._badge_path = None

        video_assets: dict[int, Path] = {
            script.scenes[i].index: asset.path
            for i, asset in enumerate(assets)
            if (asset.kind == "video"
                and asset.path.exists()
                and asset.path.suffix.lower() == ".mp4"
                and i < len(script.scenes))
        }

        if visual_style == "gradient_phone":
            clips = await self._clips_b(script, video_assets)
        else:
            clips = await self._clips_a(script, video_assets)

        concat = self.output_dir / f"{target.stem}_concat.txt"
        concat.write_text("".join(f"file '{p.resolve()}'\n" for p in clips), encoding="utf-8")

        # v10: явная пауза + сборка мусора перед самым тяжёлым шагом (mix).
        # На Render free-tier (512MB) ОС нужно время чтобы реально освободить
        # память от завершившихся ffmpeg-процессов сегментов, иначе mix
        # стартует на уже частично занятой RAM и может схватить OOM.
        gc.collect()
        await asyncio.sleep(1.5)

        await self._mix_with_retry(concat, voice_path, target)
        self._cleanup_segments(clips, concat)
        return target, subtitle_path

    def _cleanup_segments(self, clips: list[Path], concat: Path) -> None:
        for clip in clips:
            try:
                if clip.exists():
                    clip.unlink()
            except Exception as e:
                logger.warning("Could not delete segment %s: %s", clip, e)
        try:
            if concat.exists():
                concat.unlink()
        except Exception as e:
            logger.warning("Could not delete concat: %s", e)
        gc.collect()

    # ── Badge helpers ─────────────────────────────────────────────────────────

    def _badge_overlay_fc(self, base_label: str, out_label: str, w: int, h: int) -> str:
        """
        filter_complex фрагмент для overlay badge PNG поверх [base_label].
        Использует movie= source (не доп. input) → не меняет нумерацию inputs.
        Возвращает строку для вставки в filter_complex.
        """
        if not self._badge_path:
            return ""
        bw, bh = 280, 56
        bx = (w - bw) // 2
        by = int(h * 0.07)
        esc = str(self._badge_path).replace("'", "\\'")
        return (
            f"movie='{esc}',scale={bw}:{bh},format=yuva420p[badge_img];"
            f"[{base_label}][badge_img]overlay={bx}:{by}[{out_label}]"
        )

    def _badge_drawtext(self, f: str, h: int) -> list[str]:
        """Текстовый fallback для badge в простом -vf пайплайне."""
        by = int(h * 0.07)
        bw, bh_v = 280, 56
        return [
            f"drawbox=x=(w-{bw})/2:y={by}:w={bw}:h={bh_v}:color=0x003799@0.92:t=fill",
            f"drawtext={f}fontcolor=white:fontsize=32:borderw=1:bordercolor=0x002060@0.6:"
            f"x=(w-text_w)/2:y={by+13}:text='Atlanta VPN'",
        ]

    def _badge_fc_or_drawtext(self, f: str, h: int, w: int,
                               vf_filters: list[str]) -> tuple[list[str], str | None]:
        """
        Возвращает (vf_filters_с_badge, None) если badge через drawtext,
        или (vf_filters_без_badge, fc_fragment) если через movie overlay.
        """
        if self._badge_path:
            return vf_filters, self._badge_overlay_fc("base", "out", w, h)
        return vf_filters + self._badge_drawtext(f, h), None

    # ── Шаблон A ──────────────────────────────────────────────────────────────

    async def _clips_a(self, script: VideoScript, va: dict[int, Path]) -> list[Path]:
        n = len(script.scenes)
        clips = []
        for i, sc in enumerate(script.scenes):
            out = self.output_dir / f"a{sc.index}_{script.template_id}.mp4"

            # Последний слайд — официальный CTA если есть
            is_last = (i == n - 1)
            if is_last and self._cta_video:
                await self._a_cta_official(sc, out)
            else:
                bg = va.get(sc.index)
                await (self._a_video(sc, bg, out, i == 0, is_last)
                       if bg else
                       self._a_solid(sc, out, i == 0, is_last))
            clips.append(out)
            gc.collect()
        return clips

    async def _a_solid(self, sc, out: Path, hook: bool, cta: bool) -> None:
        w, h, fps = self.settings.video_width, self.settings.video_height, self.settings.fps
        idx      = (sc.index - 1) % len(_A_BG)
        bg_color = _A_BG[idx][0]
        f        = self._fa()

        planet = _planet_boxes(w, h)
        grid = (
            [f"drawbox=x=0:y={h*i//6}:w={w}:h=1:color=0x1a2a3a@0.2:t=fill" for i in range(1, 6)]
            + [f"drawbox=x={w*i//4}:y=0:w=1:h={h}:color=0x1a2a3a@0.2:t=fill" for i in range(1, 4)]
        )
        # badge и текст позиционируем ниже badge
        badge_bottom = int(h * 0.07) + 56 + 8   # ≈153
        sz    = 82 if hook else 72
        lines = _wrap(sc.on_screen_text.upper(), 12)  # жёстче оборот — нет обрезки
        lh    = sz + 10
        sy    = badge_bottom + 16

        title = [
            f"drawtext={f}fontcolor=white:fontsize={sz}:borderw=4:bordercolor=black@0.7:"
            f"x=(w-text_w)/2:y={sy+i*lh}:text='{_esc(l)}'"
            for i, l in enumerate(lines)
        ]
        sub = _esc(sc.voiceover[:42]) if sc.voiceover and not cta else ""
        sub_f = (
            [f"drawtext={f}fontcolor=0xB0C8E0:fontsize=40:borderw=2:bordercolor=black@0.5:"
             f"x=(w-text_w)/2:y=h*0.71:text='{sub}'"]
            if sub else []
        )
        cta_f = []
        if cta:
            ct = _esc("Ссылка в описании")
            cta_f = [
                f"drawbox=x=(w-460)/2:y=h*0.74:w=460:h=60:color=0x003070@0.75:t=fill",
                f"drawtext={f}fontcolor=white:fontsize=40:borderw=2:bordercolor=black@0.4:"
                f"x=(w-text_w)/2:y=h*0.757:text='{ct}'",
            ]

        vf_base = (
            [f"scale={w}:{h}"] + planet + grid + title + sub_f + cta_f + ["format=yuv420p"]
        )

        if self._badge_path:
            # badge через movie= overlay в filter_complex
            bw, bh_val = 280, 56
            bx = (w - bw) // 2
            by = int(h * 0.07)
            esc_badge = str(self._badge_path).replace("'", "\\'")
            fc = (
                f"[0:v]{','.join(vf_base[:-1])}[base];"
                f"movie='{esc_badge}',scale={bw}:{bh_val},format=yuva420p[bdg];"
                f"[base][bdg]overlay={bx}:{by},format=yuv420p[v]"
            )
            await self._run([
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c={bg_color}:s={w}x{h}:r={fps}",
                "-t", str(sc.duration),
                "-filter_complex", fc, "-map", "[v]", "-an",
            ] + _SEG_ENCODE + [str(out)])
        else:
            badge_filters = self._badge_drawtext(f, h)
            vf = [f"scale={w}:{h}"] + planet + grid + badge_filters + title + sub_f + cta_f + ["format=yuv420p"]
            await self._run([
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c={bg_color}:s={w}x{h}:r={fps}",
                "-t", str(sc.duration), "-vf", ",".join(vf), "-an",
            ] + _SEG_ENCODE + [str(out)])

    async def _a_video(self, sc, bg: Path, out: Path, hook: bool, cta: bool) -> None:
        w, h, fps = self.settings.video_width, self.settings.video_height, self.settings.fps
        f         = self._fa()

        badge_bottom = int(h * 0.07) + 56 + 8
        sz    = 90 if hook else 80
        lines = _wrap(sc.on_screen_text.upper(), 12)
        lh    = sz + 10
        sy    = badge_bottom + 16

        title_f = [
            f"drawtext={f}fontcolor=white:fontsize={sz}:borderw=5:bordercolor=black@0.8:"
            f"x=(w-text_w)/2:y={sy+i*lh}:text='{_esc(l)}'"
            for i, l in enumerate(lines)
        ]
        sub = _esc(sc.voiceover[:42]) if sc.voiceover else ""
        sub_f = (
            [f"drawtext={f}fontcolor=0xB0C8E0:fontsize=40:borderw=3:bordercolor=black@0.5:"
             f"x=(w-text_w)/2:y=h*0.71:text='{sub}'"]
            if sub else []
        )

        vf_base = (
            [f"scale={w}:{h},crop={w}:{h}:(iw-{w})/2:(ih-{h})/2",
             "colorchannelmixer=rr=0.30:gg=0.30:bb=0.38"]
            + title_f + sub_f
        )

        if self._badge_path:
            bw, bh_val = 280, 56
            bx = (w - bw) // 2
            by = int(h * 0.07)
            esc_badge = str(self._badge_path).replace("'", "\\'")
            fc = (
                f"[0:v]{','.join(vf_base)}[base];"
                f"movie='{esc_badge}',scale={bw}:{bh_val},format=yuva420p[bdg];"
                f"[base][bdg]overlay={bx}:{by},format=yuv420p[v]"
            )
            await self._run([
                "ffmpeg", "-y",
                "-stream_loop", "-1", "-i", str(bg),
                "-t", str(sc.duration),
                "-filter_complex", fc, "-map", "[v]", "-an", "-r", str(fps),
            ] + _SEG_ENCODE + [str(out)])
        else:
            badge_f = self._badge_drawtext(f, h)
            vf = vf_base + badge_f + ["format=yuv420p"]
            await self._run([
                "ffmpeg", "-y",
                "-stream_loop", "-1", "-i", str(bg),
                "-t", str(sc.duration),
                "-vf", ",".join(vf), "-an", "-r", str(fps),
            ] + _SEG_ENCODE + [str(out)])

    async def _a_cta_official(self, sc, out: Path) -> None:
        """
        Финальный слайд: официальный CTA-ролик IMG_5778.MP4.
        640x432 горизонтальное → pad до 720x1280 (чёрные полосы сверху/снизу).
        Длина = длина сцены или длина ролика (берём меньшее).
        """
        w, h, fps = self.settings.video_width, self.settings.video_height, self.settings.fps
        duration = min(sc.duration, 5.8)  # IMG_5778 = 5.8с
        await self._run([
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", str(self._cta_video),
            "-t", str(duration),
            "-vf", (
                f"scale={w}:-2:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,"
                f"setsar=1,format=yuv420p"
            ),
            "-an",
        ] + _SEG_ENCODE + [str(out)])

    # ── Шаблон B ──────────────────────────────────────────────────────────────

    async def _clips_b(self, script: VideoScript, va: dict[int, Path]) -> list[Path]:
        n = len(script.scenes)
        clips = []
        for i, sc in enumerate(script.scenes):
            out = self.output_dir / f"b{sc.index}_{script.template_id}.mp4"
            bg  = va.get(sc.index)
            is_last = (i == n - 1)
            if is_last and self._cta_video:
                await self._a_cta_official(sc, out)
            elif is_last:
                await self._b_final(sc, out)
            elif bg:
                await self._b_phone(sc, bg, out, i == 0)
            else:
                await self._b_text(sc, out, i == 0)
            clips.append(out)
            gc.collect()
        return clips

    def _b_bg_color(self, idx: int) -> str:
        return _B_BG[idx][0]

    async def _b_text(self, sc, out: Path, hook: bool) -> None:
        w, h, fps = self.settings.video_width, self.settings.video_height, self.settings.fps
        idx      = (sc.index - 1) % len(_B_BG)
        bg_color = self._b_bg_color(idx)
        f        = self._fa()
        stars    = _stars(w, h, sc.index)

        sz    = 90 if hook else 80
        lines = _wrap(sc.on_screen_text, 11)
        lh    = sz + 14
        ty    = (h - len(lines) * lh) // 2 - 40
        title = [
            f"drawtext={f}fontcolor=white:fontsize={sz}:borderw=3:bordercolor=black@0.3:"
            f"x=(w-text_w)/2:y={ty+i*lh}:text='{_esc(l)}'"
            for i, l in enumerate(lines)
        ]
        sub  = _esc(sc.voiceover[:42]) if sc.voiceover else ""
        subf = (
            [f"drawtext={f}fontcolor=0xE0D0FF:fontsize=42:borderw=2:bordercolor=black@0.3:"
             f"x=(w-text_w)/2:y=h*0.78:text='{sub}'"]
            if sub else []
        )
        vf_base = [f"scale={w}:{h}"] + stars + title + subf

        if self._badge_path:
            bw, bh_val = 280, 56
            bx = (w - bw) // 2
            by = int(h * 0.07)
            esc_badge = str(self._badge_path).replace("'", "\\'")
            fc = (
                f"[0:v]{','.join(vf_base)}[base];"
                f"movie='{esc_badge}',scale={bw}:{bh_val},format=yuva420p[bdg];"
                f"[base][bdg]overlay={bx}:{by},format=yuv420p[v]"
            )
            await self._run([
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c={bg_color}:s={w}x{h}:r={fps}",
                "-t", str(sc.duration),
                "-filter_complex", fc, "-map", "[v]", "-an",
            ] + _SEG_ENCODE + [str(out)])
        else:
            badge_f = self._badge_drawtext(f, h)
            vf = vf_base + badge_f + ["format=yuv420p"]
            await self._run([
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c={bg_color}:s={w}x{h}:r={fps}",
                "-t", str(sc.duration), "-vf", ",".join(vf), "-an",
            ] + _SEG_ENCODE + [str(out)])

    async def _b_phone(self, sc, bg: Path, out: Path, hook: bool) -> None:
        w, h, fps = self.settings.video_width, self.settings.video_height, self.settings.fps
        idx      = (sc.index - 1) % len(_B_BG)
        bg_color = self._b_bg_color(idx)
        f        = self._fa()

        pw = int(w * 0.68); ph = int(h * 0.50)
        px = (w - pw) // 2; py = int(h * 0.24)
        iw = pw - 24;       ih = ph - 60
        ix = px + 12;       iy = py + 36

        stars       = _stars(w, h, sc.index)
        phone_frame = [
            f"drawbox=x={px+6}:y={py+6}:w={pw}:h={ph}:color=0x000020@0.45:t=fill",
            f"drawbox=x={px}:y={py}:w={pw}:h={ph}:color=0x1a1a2e:t=fill",
            f"drawbox=x={ix}:y={iy}:w={iw}:h={ih}:color=0x080818:t=fill",
            f"drawbox=x={(w-56)//2}:y={py+6}:w=56:h=14:color=0x0d0d1a:t=fill",
        ]
        sz     = 70 if hook else 62
        tlines = _wrap(sc.on_screen_text, 16)
        tlh    = sz + 10
        # Заголовок между badge и phone frame
        _badge_bottom = int(h * 0.07) + 56 + 10
        _zone_h       = py - 10 - _badge_bottom
        _block_h      = len(tlines) * tlh - 10
        tsy = _badge_bottom + max(0, (_zone_h - _block_h) // 2)

        title = [
            f"drawtext={f}fontcolor=white:fontsize={sz}:borderw=3:bordercolor=black@0.3:"
            f"x=(w-text_w)/2:y={tsy+i*tlh}:text='{_esc(l)}'"
            for i, l in enumerate(tlines)
        ]
        sub  = _esc(sc.voiceover[:42]) if sc.voiceover else ""
        subf = (
            [f"drawtext={f}fontcolor=0xE0D0FF:fontsize=40:borderw=2:bordercolor=black@0.3:"
             f"x=(w-text_w)/2:y=h*0.795:text='{sub}'"]
            if sub else []
        )

        vf_bg_base = [f"scale={w}:{h}"] + stars + phone_frame + title + subf

        if self._badge_path:
            bw, bh_val = 280, 56
            bx = (w - bw) // 2
            by = int(h * 0.07)
            esc_badge = str(self._badge_path).replace("'", "\\'")
            filter_complex = (
                f"[0:v]{','.join(vf_bg_base)}[bg_raw];"
                f"movie='{esc_badge}',scale={bw}:{bh_val},format=yuva420p[bdg];"
                f"[bg_raw][bdg]overlay={bx}:{by},format=yuv420p[bg];"
                f"[1:v]scale={iw}:{ih},setsar=1,format=yuv420p[pv];"
                f"[bg][pv]overlay={ix}:{iy}[v]"
            )
        else:
            badge_f = self._badge_drawtext(f, h)
            vf_bg = vf_bg_base + badge_f + ["format=yuv420p"]
            filter_complex = (
                f"[0:v]{','.join(vf_bg)}[bg];"
                f"[1:v]scale={iw}:{ih},setsar=1,format=yuv420p[pv];"
                f"[bg][pv]overlay={ix}:{iy}[v]"
            )

        await self._run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c={bg_color}:s={w}x{h}:r={fps}",
            "-stream_loop", "-1", "-i", str(bg),
            "-t", str(sc.duration),
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-threads", "1",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-pix_fmt", "yuv420p",
            "-an", str(out),
        ])

    async def _b_final(self, sc, out: Path) -> None:
        """Fallback финальный слайд (если нет официального CTA видео)."""
        w, h, fps = self.settings.video_width, self.settings.video_height, self.settings.fps
        bg_color  = _B_BG[0][0]
        f         = self._fa()
        stars     = _stars(w, h, seed=99, count=18)

        bx      = (w - 400) // 2
        icon_cy = h // 2 - 80
        icon_y  = icon_cy - 36
        text_y  = icon_cy - 35
        logo = [
            f"drawbox=x={bx}:y={icon_y}:w=72:h=72:color=0x0055cc@0.92:t=fill",
            f"drawtext={f}fontcolor=white:fontsize=48:borderw=2:bordercolor=0x003080@0.6:"
            f"x={bx+14}:y={icon_y+12}:text='A'",
            f"drawtext={f}fontcolor=white:fontsize=64:borderw=3:bordercolor=0x003080@0.4:"
            f"x={bx+88}:y={text_y}:text='Atlanta VPN'",
        ]
        ct  = _esc(sc.on_screen_text)
        cta = [
            f"drawtext={f}fontcolor=0xD0C0FF:fontsize=50:borderw=2:bordercolor=black@0.3:"
            f"x=(w-text_w)/2:y=h*0.70:text='{ct}'"
        ]
        vf_base = [f"scale={w}:{h}"] + stars + logo + cta

        if self._badge_path:
            bw, bh_val = 280, 56
            bx_b = (w - bw) // 2
            by = int(h * 0.07)
            esc_badge = str(self._badge_path).replace("'", "\\'")
            fc = (
                f"[0:v]{','.join(vf_base)}[base];"
                f"movie='{esc_badge}',scale={bw}:{bh_val},format=yuva420p[bdg];"
                f"[base][bdg]overlay={bx_b}:{by},format=yuv420p[v]"
            )
            await self._run([
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c={bg_color}:s={w}x{h}:r={fps}",
                "-t", str(sc.duration),
                "-filter_complex", fc, "-map", "[v]", "-an",
            ] + _SEG_ENCODE + [str(out)])
        else:
            badge_f = self._badge_drawtext(f, h)
            vf = vf_base + badge_f + ["format=yuv420p"]
            await self._run([
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c={bg_color}:s={w}x{h}:r={fps}",
                "-t", str(sc.duration), "-vf", ",".join(vf), "-an",
            ] + _SEG_ENCODE + [str(out)])

    # ── Mix ───────────────────────────────────────────────────────────────────

    async def _mix(self, concat: Path, voice: Path | None, target: Path) -> None:
        if voice and voice.exists():
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", str(concat),
                "-i", str(voice),
                "-filter_complex", "[1:a]volume=1.0[a]",
                "-map", "0:v", "-map", "[a]",
                "-shortest",
            ] + _MIX_ENCODE + ["-c:a", "aac", "-b:a", "128k", str(target)]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", str(concat),
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-shortest",
            ] + _MIX_ENCODE + ["-c:a", "aac", "-b:a", "128k", str(target)]
        await self._run(cmd)

    async def _mix_with_retry(self, concat: Path, voice: Path | None, target: Path) -> None:
        """
        v10: mix — самый тяжёлый шаг (concat + полный re-encode + audio).
        Если первая попытка падает (OOM/timeout/crash), повторяем с более
        лёгкими настройками: ниже битрейт и разрешение, без аудио-фильтра.
        Это жертвует качеством только в худшем случае, а не всегда.
        """
        try:
            await self._mix(concat, voice, target)
            return
        except Exception as e:
            logger.warning("Mix attempt 1 failed (%s), retrying with lighter settings", e)

        gc.collect()
        await asyncio.sleep(2.0)

        w, h = self.settings.video_width, self.settings.video_height
        light_encode = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
                         "-threads", "1", "-pix_fmt", "yuv420p",
                         "-bufsize", "800k", "-maxrate", "1200k",
                         "-vf", f"scale={w}:{h}"]
        if voice and voice.exists():
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", str(concat),
                "-i", str(voice),
                "-map", "0:v", "-map", "1:a",
                "-shortest",
            ] + light_encode + ["-c:a", "aac", "-b:a", "96k", str(target)]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", str(concat),
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-shortest",
            ] + light_encode + ["-c:a", "aac", "-b:a", "96k", str(target)]
        await self._run(cmd, timeout=240)
        logger.info("Mix succeeded on retry with lighter settings")

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _run(self, cmd: list[str], timeout: int = 300) -> None:
        logger.info("ffmpeg: %s", " ".join(shlex.quote(p) for p in cmd))
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            raise RuntimeError(f"ffmpeg timed out after {timeout}s")
        if proc.returncode != 0:
            raise RuntimeError(stderr.decode("utf-8", errors="ignore")[-2000:])

    def _fa(self) -> str:
        return f"fontfile={shlex.quote(self._font)}:" if self._font else ""

    @staticmethod
    def _find_font() -> str | None:
        for p in [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
            "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
        ]:
            if Path(p).exists():
                return p
        return None


# ── Utils ─────────────────────────────────────────────────────────────────────

def _esc(v: str) -> str:
    return (
        v.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        .replace("%", "\\%").replace("\n", " ").replace("[", "\\[").replace("]", "\\]")
    )[:68]  # чуть меньше чем раньше (было 72)


def _wrap(text: str, n: int = 12) -> list[str]:
    """Оборачивает текст по n символов — жёстче, нет обрезки справа."""
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        if len(cur) + len(w) + (1 if cur else 0) <= n:
            cur = f"{cur} {w}".strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [text[:n]]


def _stars(w: int, h: int, seed: int = 1, count: int = 10) -> list[str]:
    import random
    rng = random.Random(seed * 137 + 42)
    boxes = []
    for _ in range(count):
        sx = rng.randint(30, w - 30)
        sy = rng.randint(int(h * 0.05), int(h * 0.90))
        sz = rng.choice([6, 8, 10, 12])
        a  = rng.uniform(0.25, 0.55)
        boxes.append(f"drawbox=x={sx}:y={sy}:w={sz}:h={sz}:color=white@{a:.2f}:t=fill")
    return boxes


def _planet_boxes(w: int, h: int) -> list[str]:
    import math
    cx    = w // 2
    cy    = int(h * 0.82)
    rx    = int(w * 0.50)
    ry    = int(h * 0.20)
    boxes = []
    steps = 15
    for i in range(steps):
        dy      = (i / (steps - 1)) * 2 - 1
        xh      = int(rx * math.sqrt(max(0, 1 - dy ** 2)))
        py      = cy + int(dy * ry)
        if not (0 <= py < h):
            continue
        intensity = 1.0 - abs(dy) * 0.6
        r_v = int(0   * intensity)
        g_v = int(90  * intensity)
        b_v = int(220 * intensity)
        ph  = max(4, ry * 2 // steps)
        boxes.append(
            f"drawbox=x={cx-xh}:y={py}:w={xh*2}:h={ph}"
            f":color=#{r_v:02x}{g_v:02x}{b_v:02x}@0.85:t=fill"
        )
    return boxes
