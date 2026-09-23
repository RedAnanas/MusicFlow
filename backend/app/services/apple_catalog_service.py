import html
import json
import re
import unicodedata
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


class AppleCatalogService:
    """通过 Apple Music 公开网页查询曲库候选。"""

    BASE_URL = "https://music.apple.com"

    def search(self, query: str, country: str = "cn", limit: int = 10) -> list[dict]:
        keyword = query.strip()
        if not keyword:
            return []

        countries = list(dict.fromkeys((country.lower(), "tw", "hk")))
        merged: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for storefront in countries:
            if len(merged) >= limit:
                break
            for item in self._search_storefront(keyword, storefront):
                identity = (
                    self._normalize(item["title"]),
                    self._normalize(item["artist"]),
                )
                if identity in seen:
                    continue
                seen.add(identity)
                merged.append(item)

        normalized_keyword = self._normalize(keyword)
        merged.sort(
            key=lambda item: self._normalize(item["title"]) != normalized_keyword
        )
        return merged[: min(max(limit, 1), 25)]

    def _search_storefront(self, keyword: str, country: str) -> list[dict]:
        parameters = urlencode({"term": keyword})
        request = Request(
            f"{self.BASE_URL}/{country.lower()}/search?{parameters}",
            headers={"User-Agent": "MusicFlow/0.7"},
        )
        try:
            with urlopen(request, timeout=10) as response:
                page = response.read().decode("utf-8")
        except Exception as exc:
            raise OSError(f"Apple 曲库搜索失败：{exc}") from exc
        return self._extract_results(page, country)

    def _extract_results(self, page: str, country: str) -> list[dict]:
        match = re.search(
            r'<script[^>]+id="serialized-server-data"[^>]*>(.*?)</script>',
            page,
            re.DOTALL,
        )
        if not match:
            return []
        try:
            payload = json.loads(html.unescape(match.group(1)))
        except json.JSONDecodeError as exc:
            raise OSError("Apple 曲库搜索结果格式异常") from exc

        results: list[dict] = []
        albums: dict[str, str] = {}

        def collect_albums(value) -> None:
            if isinstance(value, list):
                for item in value:
                    collect_albums(item)
                return
            if not isinstance(value, dict):
                return
            item_id = str(value.get("id") or "")
            title_links = value.get("titleLinks") or []
            if "square-section - album - " in item_id and title_links:
                album_id = item_id.rsplit(" - ", 1)[-1]
                album_title = str((title_links[0] or {}).get("title") or "")
                if album_id and album_title:
                    albums[album_id] = album_title
            descriptor = value.get("contentDescriptor") or {}
            identifiers = descriptor.get("identifiers") or {}
            if descriptor.get("kind") == "album" and value.get("title"):
                album_id = str(identifiers.get("storeAdamID") or "")
                if album_id:
                    albums.setdefault(album_id, str(value["title"]))
            for child in value.values():
                collect_albums(child)

        collect_albums(payload)

        def visit(value) -> None:
            if isinstance(value, list):
                for item in value:
                    visit(item)
                return
            if not isinstance(value, dict):
                return

            descriptor = value.get("contentDescriptor") or {}
            if (
                value.get("itemKind") == "songs"
                and descriptor.get("kind") == "song"
                and value.get("title")
            ):
                identifiers = descriptor.get("identifiers") or {}
                subtitle = str(value.get("subtitle") or "")
                artist = subtitle.split("·", 1)[-1].strip() if "·" in subtitle else subtitle
                artwork = ((value.get("artwork") or {}).get("dictionary") or {}).get("url", "")
                artwork = (
                    str(artwork)
                    .replace("{w}", "200")
                    .replace("{h}", "200")
                    .replace("{f}", "jpg")
                    .replace("{c}", "bb")
                )
                track_url = str(descriptor.get("url") or "")
                results.append({
                    "apple_id": str(identifiers.get("storeAdamID") or ""),
                    "title": str(value["title"]),
                    "artist": artist,
                    "album": self._album_from_url(track_url, albums),
                    "duration_ms": 0,
                    "artwork_url": artwork,
                    "track_url": track_url,
                    "country": country.lower(),
                })

            for child in value.values():
                visit(child)

        visit(payload)
        return results

    @staticmethod
    def _album_from_url(track_url: str, albums: dict[str, str]) -> str:
        parts = urlparse(track_url).path.strip("/").split("/")
        return albums.get(parts[-1], "") if parts else ""

    @staticmethod
    def _normalize(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).casefold()
        return re.sub(r"[^\w\u3400-\u9fff]+", "", normalized)


apple_catalog_service = AppleCatalogService()
