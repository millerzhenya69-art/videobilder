import hashlib
import logging

import aiohttp

from config.settings import Settings
from services.models import Asset, Scene

logger = logging.getLogger(__name__)


class AssetProvider:
    """Fetches reusable assets and falls back to deterministic local placeholders."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.download_dir = settings.assets_dir / "downloaded"
        self.generated_dir = settings.assets_dir / "generated"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.generated_dir.mkdir(parents=True, exist_ok=True)

    async def collect_for_scenes(self, scenes: list[Scene]) -> list[Asset]:
        assets: list[Asset] = []
        for scene in scenes:
            asset = await self._find_or_generate(scene)
            assets.append(asset)
        return assets

    async def _find_or_generate(self, scene: Scene) -> Asset:
        if self.settings.pexels_api_key:
            found = await self._download_pexels_video(scene.asset_keywords)
            if found is not None:
                return found
        return self._placeholder_asset(scene)

    async def _download_pexels_video(self, keywords: list[str]) -> Asset | None:
        query = " ".join(keywords[:3]) or "technology phone"
        digest = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
        target = self.download_dir / f"pexels_{digest}.mp4"
        if target.exists():
            return Asset(path=target, source_url="pexels-cache", license="Pexels License", kind="video", keywords=keywords)
        headers = {"Authorization": self.settings.pexels_api_key}
        params = {"query": query, "orientation": "portrait", "per_page": 1}
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get("https://api.pexels.com/videos/search", params=params) as resp:
                    if resp.status != 200:
                        logger.warning("Pexels search failed with status %s", resp.status)
                        return None
                    data = await resp.json()
                videos = data.get("videos") or []
                if not videos:
                    return None
                files = sorted(videos[0].get("video_files", []), key=lambda item: item.get("width", 0), reverse=True)
                link = next((item.get("link") for item in files if item.get("link")), None)
                if not link:
                    return None
                async with session.get(link) as media_resp:
                    if media_resp.status != 200:
                        return None
                    target.write_bytes(await media_resp.read())
                return Asset(path=target, source_url=link, license="Pexels License", kind="video", keywords=keywords)
        except aiohttp.ClientError as exc:
            logger.warning("Pexels download failed: %s", exc)
            return None

    def _placeholder_asset(self, scene: Scene) -> Asset:
        digest = hashlib.sha256(scene.visual_prompt.encode("utf-8")).hexdigest()[:16]
        path = self.generated_dir / f"scene_{scene.index}_{digest}.txt"
        path.write_text(scene.visual_prompt, encoding="utf-8")
        return Asset(path=path, kind="image", keywords=scene.asset_keywords)
