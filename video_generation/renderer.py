"""
FFmpegRenderer v5 — два шаблона Atlanta VPN, оптимизированный рендер.

ШАБЛОН A  (visual_style="dark_planet"):
  Тёмный #07070f фон, синяя планета через geq, бейдж + текст.

ШАБЛОН B  (visual_style="gradient_phone"):
  Фиолетово-синий диагональный градиент, звёздочки, телефон-рамка
  с Pexels-видео внутри, финальная сцена — логотип на чистом фоне.

Оптимизация: планета рисуется через один geq-фильтр (не 274 drawbox).
"""
from __future__ import annotations

import asyncio
import logging
import shlex
from pathlib import Path

from config.settings import Settings
from brand_assets.generate_badge import make_badge
from services.models import Asset, VideoScript
from subtitles.ass import build_cues, write_ass

logger = logging.getLogger(__name__)

# ── Палитры ───────────────────────────────────────────────────────────────────
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


class FFmpegRenderer:
    def __init__(self, settings: Settings) -> None:
        self.settings   = settings
        self.output_dir = settings.cache_dir / "videos"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._font      = self._find_font()

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
        await self._mix(concat, voice_path, target)
        return target, subtitle_path

    # ── Шаблон A ──────────────────────────────────────────────────────────────

    async def _clips_a(self, script: VideoScript, va: dict[int, Path]) -> list[Path]:
        n = len(script.scenes)
        clips = []
        for i, sc in enumerate(script.scenes):
            out = self.output_dir / f"a{sc.index}_{script.template_id}.mp4"
            bg  = va.get(sc.index)
            await (self._a_video(sc, bg, out, i == 0, i == n-1)
                   if bg else
                   self._a_solid(sc, out, i == 0, i == n-1))
            clips.append(out)
        return clips

    async def _a_solid(self, sc, out: Path, hook: bool, cta: bool) -> None:
        w, h, fps = self.settings.video_width, self.settings.video_height, self.settings.fps
        idx        = (sc.index - 1) % len(_A_BG)
        dr,dg,db   = _hx(_A_BG[idx][0])
        mr,mg,mb   = _hx(_A_BG[idx][1])
        f          = self._fa()

        # Фон + сетка + планета — всё в одном geq
        geq = (
            f"geq="
            # Фон: вертикальный градиент тёмный→синий
            f"r='{dr}+({mr}-{dr})*Y/H + 180*max(0,1-sqrt(((X-W/2)/({w}*0.58))^2+((Y-H*0.80)/({h}*0.23))^2))':"
            f"g='{dg}+({mg}-{dg})*Y/H + 100*max(0,1-sqrt(((X-W/2)/({w}*0.58))^2+((Y-H*0.80)/({h}*0.23))^2))':"
            f"b='{db}+({mb}-{db})*Y/H + 255*max(0,1-sqrt(((X-W/2)/({w}*0.58))^2+((Y-H*0.80)/({h}*0.23))^2))'"
        )
        # Сетка через drawbox (только 10 линий — быстро)
        grid = (
            [f"drawbox=x=0:y={h*i//6}:w={w}:h=1:color=0x1a2a3a@0.2:t=fill" for i in range(1,6)]
            + [f"drawbox=x={w*i//4}:y=0:w=1:h={h}:color=0x1a2a3a@0.2:t=fill" for i in range(1,4)]
        )
        sz    = 86 if hook else 78
        yf    = 0.26 if hook else 0.30
        lines = _wrap(sc.on_screen_text.upper(), 14)
        lh    = sz + 12
        sy    = int(h*yf) - len(lines)*lh//2
        title = [
            f"drawtext={f}fontcolor=white:fontsize={sz}:borderw=4:bordercolor=black@0.7:x=(w-text_w)/2:y={sy+i*lh}:text='{_esc(l)}'"
            for i,l in enumerate(lines)
        ]
        sub = _esc(sc.voiceover[:55]) if sc.voiceover and not cta else ""
        sub_f = ([f"drawtext={f}fontcolor=0xB0C8E0:fontsize=46:borderw=3:bordercolor=black@0.5:x=(w-text_w)/2:y=h*0.68:text='{sub}'"]
                 if sub else [])
        cta_f = []
        if cta:
            ct = _esc("Ссылка в описании")
            cta_f = [
                f"drawbox=x=(w-480)/2:y=h*0.72:w=480:h=64:color=0x003070@0.75:t=fill",
                f"drawtext={f}fontcolor=white:fontsize=42:borderw=2:bordercolor=black@0.4:x=(w-text_w)/2:y=h*0.737:text='{ct}'",
            ]
        vf = [f"scale={w}:{h}", geq] + grid + title + sub_f + cta_f + ["format=yuv420p"]
        await self._run([
            "ffmpeg","-y","-f","lavfi","-i",f"color=c=black:s={w}x{h}:r={fps}",
            "-t",str(sc.duration),"-vf",",".join(vf),"-an",str(out),
        ])
        badge = self._badge()
        if badge:
            await self._overlay_badge(out, badge, w, h)

    async def _a_video(self, sc, bg: Path, out: Path, hook: bool, cta: bool) -> None:
        w,h,fps = self.settings.video_width, self.settings.video_height, self.settings.fps
        f       = self._fa()
        bw,bh   = 280,56; bx=(w-bw)//2; by=int(h*0.07)
        sz      = 100 if hook else 88
        lines   = _wrap(sc.on_screen_text.upper(), 14)
        lh      = sz+12; sy = int(h*0.33)-len(lines)*lh//2
        sub     = _esc(sc.voiceover[:55]) if sc.voiceover else ""
        vf = (
            [f"scale={w}:{h},crop={w}:{h}:(iw-{w})/2:(ih-{h})/2",
             "geq=r='r(X,Y)*0.28':g='g(X,Y)*0.28':b='b(X,Y)*0.38'",
             f"drawbox=x={bx}:y={by}:w={bw}:h={bh}:color=0x0055aa@0.88:t=fill",
             f"drawtext={f}fontcolor=white:fontsize=34:borderw=2:bordercolor=0x003090@0.5:x=(w-text_w)/2:y={by+11}:text='Atlanta VPN'"]
            + [f"drawtext={f}fontcolor=white:fontsize={sz}:borderw=5:bordercolor=black@0.8:x=(w-text_w)/2:y={sy+i*lh}:text='{_esc(l)}'"
               for i,l in enumerate(lines)]
            + ([f"drawtext={f}fontcolor=0xB0C8E0:fontsize=46:borderw=3:bordercolor=black@0.5:x=(w-text_w)/2:y=h*0.68:text='{sub}'"] if sub else [])
            + ["format=yuv420p"]
        )
        await self._run([
            "ffmpeg","-y","-stream_loop","-1","-i",str(bg),
            "-t",str(sc.duration),"-vf",",".join(vf),"-an","-r",str(fps),str(out),
        ])
        badge = self._badge()
        if badge:
            await self._overlay_badge(out, badge, w, h)

    # ── Шаблон B ──────────────────────────────────────────────────────────────

    async def _clips_b(self, script: VideoScript, va: dict[int, Path]) -> list[Path]:
        n = len(script.scenes)
        clips = []
        for i, sc in enumerate(script.scenes):
            out = self.output_dir / f"b{sc.index}_{script.template_id}.mp4"
            bg  = va.get(sc.index)
            if i == n-1:
                await self._b_final(sc, out)
            elif bg:
                await self._b_phone(sc, bg, out, i == 0)
            else:
                await self._b_text(sc, out, i == 0)
            clips.append(out)
        return clips

    def _b_geq(self, idx: int) -> str:
        dr,dg,db = _hx(_B_BG[idx][0])
        lr,lg,lb = _hx(_B_BG[idx][1])
        return (
            f"geq="
            f"r='{dr}+({lr}-{dr})*(X/W*0.4+Y/H*0.6)':"
            f"g='{dg}+({lg}-{dg})*(X/W*0.4+Y/H*0.6)':"
            f"b='{db}+({lb}-{db})*(X/W*0.4+Y/H*0.6)'"
        )

    async def _b_text(self, sc, out: Path, hook: bool) -> None:
        w,h,fps = self.settings.video_width, self.settings.video_height, self.settings.fps
        idx     = (sc.index-1) % len(_B_BG)
        f       = self._fa()
        stars   = _stars(w, h, sc.index)
        sz      = 96 if hook else 84
        lines   = _wrap(sc.on_screen_text, 12)
        lh      = sz+14; ty = (h - len(lines)*lh)//2 - 40
        title   = [
            f"drawtext={f}fontcolor=white:fontsize={sz}:borderw=3:bordercolor=black@0.3:x=(w-text_w)/2:y={ty+i*lh}:text='{_esc(l)}'"
            for i,l in enumerate(lines)
        ]
        sub  = _esc(sc.voiceover[:50]) if sc.voiceover else ""
        subf = ([f"drawtext={f}fontcolor=0xE0D0FF:fontsize=48:borderw=2:bordercolor=black@0.3:x=(w-text_w)/2:y=h*0.78:text='{sub}'"]
                if sub else [])
        vf = [f"scale={w}:{h}", self._b_geq(idx)] + stars + title + subf + ["format=yuv420p"]
        await self._run([
            "ffmpeg","-y","-f","lavfi","-i",f"color=c=black:s={w}x{h}:r={fps}",
            "-t",str(sc.duration),"-vf",",".join(vf),"-an",str(out),
        ])
        badge = self._badge()
        if badge:
            await self._overlay_badge(out, badge, w, h)

    async def _b_phone(self, sc, bg: Path, out: Path, hook: bool) -> None:
        w,h,fps = self.settings.video_width, self.settings.video_height, self.settings.fps
        idx     = (sc.index-1) % len(_B_BG)
        f       = self._fa()

        # Размеры телефона
        pw = int(w*0.68); ph = int(h*0.50)
        px = (w-pw)//2;   py = int(h*0.24)
        iw = pw-24;       ih = ph-60
        ix = px+12;       iy = py+36

        stars = _stars(w, h, sc.index)
        phone_frame = [
            f"drawbox=x={px+6}:y={py+6}:w={pw}:h={ph}:color=0x000020@0.45:t=fill",   # тень
            f"drawbox=x={px}:y={py}:w={pw}:h={ph}:color=0x1a1a2e:t=fill",              # корпус
            f"drawbox=x={ix}:y={iy}:w={iw}:h={ih}:color=0x080818:t=fill",              # экран
            f"drawbox=x={(w-56)//2}:y={py+6}:w=56:h=14:color=0x0d0d1a:t=fill",        # нотч
        ]
        sz     = 74 if hook else 66
        tlines = _wrap(sc.on_screen_text, 18)
        tlh    = sz+10; tsy = int(h*0.08)
        title  = [
            f"drawtext={f}fontcolor=white:fontsize={sz}:borderw=3:bordercolor=black@0.3:x=(w-text_w)/2:y={tsy+i*tlh}:text='{_esc(l)}'"
            for i,l in enumerate(tlines)
        ]
        sub  = _esc(sc.voiceover[:45]) if sc.voiceover else ""
        subf = ([f"drawtext={f}fontcolor=0xE0D0FF:fontsize=46:borderw=2:bordercolor=black@0.3:x=(w-text_w)/2:y=h*0.80:text='{sub}'"]
                if sub else [])

        vf_bg = [f"scale={w}:{h}", self._b_geq(idx)] + stars + phone_frame + title + subf + ["format=yuv420p"]

        # Один проход: фоновая графика через lavfi (input 0) + Pexels-видео (input 1)
        # масштабируется и накладывается через overlay в единый filter_complex
        filter_complex = (
            f"[0:v]{','.join(vf_bg)}[bg];"
            f"[1:v]scale={iw}:{ih},setsar=1,format=yuv420p[pv];"
            f"[bg][pv]overlay={ix}:{iy}[v]"
        )
        await self._run([
            "ffmpeg","-y",
            "-f","lavfi","-i",f"color=c=black:s={w}x{h}:r={fps}",
            "-stream_loop","-1","-i",str(bg),
            "-t",str(sc.duration),
            "-filter_complex",filter_complex,
            "-map","[v]",
            "-c:v","libx264","-preset","veryfast","-pix_fmt","yuv420p",
            "-an",str(out),
        ])

    async def _b_final(self, sc, out: Path) -> None:
        w,h,fps = self.settings.video_width, self.settings.video_height, self.settings.fps
        f       = self._fa()
        stars   = _stars(w, h, seed=99, count=18)
        logo    = [
            f"drawbox=x={(w-400)//2}:y={(h-90)//2-10}:w=72:h=72:color=0x0055cc@0.9:t=fill",
            f"drawtext={f}fontcolor=white:fontsize=70:borderw=3:bordercolor=0x003080@0.4:x=(w-text_w)/2+45:y=(h-text_h)/2:text='Atlanta VPN'",
        ]
        ct  = _esc(sc.on_screen_text)
        cta = [f"drawtext={f}fontcolor=0xD0C0FF:fontsize=52:borderw=2:bordercolor=black@0.3:x=(w-text_w)/2:y=h*0.62:text='{ct}'"]
        vf  = [f"scale={w}:{h}", self._b_geq(0)] + stars + logo + cta + ["format=yuv420p"]
        await self._run([
            "ffmpeg","-y","-f","lavfi","-i",f"color=c=black:s={w}x{h}:r={fps}",
            "-t",str(sc.duration),"-vf",",".join(vf),"-an",str(out),
        ])
        badge = self._badge()
        if badge:
            await self._overlay_badge(out, badge, w, h)

    # ── Mix ───────────────────────────────────────────────────────────────────

    async def _mix(self, concat: Path, voice: Path | None, target: Path) -> None:
        if voice and voice.exists():
            cmd = [
                "ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),
                "-i",str(voice),
                "-filter_complex","[1:a]volume=1.0[a]","-map","0:v","-map","[a]",
                "-shortest","-c:v","libx264","-preset","veryfast","-crf","22",
                "-pix_fmt","yuv420p","-c:a","aac","-b:a","128k",str(target),
            ]
        else:
            cmd = [
                "ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),
                "-f","lavfi","-i","anullsrc=channel_layout=stereo:sample_rate=44100",
                "-shortest","-c:v","libx264","-preset","veryfast","-crf","22",
                "-pix_fmt","yuv420p","-c:a","aac","-b:a","128k",str(target),
            ]
        await self._run(cmd)

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _run(self, cmd: list[str]) -> None:
        logger.info("ffmpeg: %s", " ".join(shlex.quote(p) for p in cmd))
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(stderr.decode("utf-8", errors="ignore")[-2000:])

    async def _overlay_badge(self, clip: Path, badge_path: Path, w: int, h: int) -> None:
        """Накладывает badge.png поверх готового клипа."""
        tmp = clip.with_suffix('.nobadge.mp4')
        clip.rename(tmp)
        # badge 320x70, позиция: по центру, y=7% от высоты
        bw, bh_px = 320, 70
        bx = (w - bw) // 2
        by = int(h * 0.07)
        await self._run([
            "ffmpeg", "-y",
            "-i", str(tmp),
            "-i", str(badge_path),
            "-filter_complex",
            f"[1:v]scale={bw}:{bh_px}[b];[0:v][b]overlay={bx}:{by}[v]",
            "-map", "[v]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            str(clip),
        ])
        tmp.unlink(missing_ok=True)

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

    @staticmethod
    def _badge() -> Path | None:
        """Возвращает путь к badge.png (создаёт при первом вызове)."""
        try:
            return make_badge()
        except Exception as exc:
            logger.warning("Badge generation failed: %s", exc)
            return None


# ── Utils ─────────────────────────────────────────────────────────────────────

def _hx(c: str) -> tuple[int,int,int]:
    h = c[2:] if c.startswith("0x") else c.lstrip("#")
    return int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)

def _esc(v: str) -> str:
    return (v.replace("\\","\\\\").replace(":","\\:").replace("'","\\'")
             .replace("%","\\%").replace("\n"," ").replace("[","\\[").replace("]","\\]"))[:72]

def _wrap(text: str, n: int = 14) -> list[str]:
    words = text.split(); lines: list[str] = []; cur = ""
    for w in words:
        if len(cur)+len(w)+(1 if cur else 0) <= n: cur = f"{cur} {w}".strip()
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines or [text[:n]]

def _stars(w: int, h: int, seed: int = 1, count: int = 10) -> list[str]:
    import random; rng = random.Random(seed*137+42); boxes = []
    for _ in range(count):
        sx = rng.randint(30, w-30); sy = rng.randint(int(h*0.05), int(h*0.90))
        sz = rng.choice([6,8,10,12]); a = rng.uniform(0.25, 0.55)
        boxes.append(f"drawbox=x={sx}:y={sy}:w={sz}:h={sz}:color=white@{a:.2f}:t=fill")
    return boxes
