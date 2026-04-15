"""YouTube 한국 인기 급상승.

우선순위:
1) GOOGLE_API_KEY 설정 → YouTube Data API v3 (공식, 정확)
2) RSS 피드 시도
3) HTML fallback
"""
from __future__ import annotations

import logging

import feedparser

from config import get_google_key

from .base import BaseScraper

logger = logging.getLogger(__name__)


class YoutubeTrendsScraper(BaseScraper):
    source = "YouTube 인기"
    base_url = "https://www.youtube.com/feeds/videos.xml?chart=trending&geo=KR"
    category = "연예"

    API_URL = "https://www.googleapis.com/youtube/v3/videos"

    def parse(self, html: str) -> list[dict]:
        return []

    def get_trending(self, limit: int = 10) -> list[dict]:
        self.last_error = ""
        last_exc = ""

        # 1) Google API 시도
        google_key = get_google_key()
        if google_key:
            try:
                items = self._fetch_via_api(google_key, limit)
                if items:
                    return items
            except Exception as exc:  # noqa: BLE001
                last_exc = f"YouTube Data API 실패: {type(exc).__name__}: {str(exc)[:100]}"
                logger.warning(last_exc)

        # 2) RSS 시도
        try:
            feed = feedparser.parse(self.base_url)
            items = self._parse_rss_entries(feed.entries, limit)
            if items:
                return items
            if getattr(feed, "bozo", 0):
                last_exc = last_exc or f"RSS 파싱 실패: {getattr(feed, 'bozo_exception', 'unknown')}"
        except Exception as exc:  # noqa: BLE001
            last_exc = last_exc or f"RSS 예외: {type(exc).__name__}: {str(exc)[:80]}"

        # 3) HTML fallback
        try:
            html = self.fetch("https://www.youtube.com/feed/trending?gl=KR&hl=ko")
            import re
            pattern = re.compile(
                r'"videoId":"([^"]+)"[^}]{0,200}?"title":\{"runs":\[\{"text":"([^"]{5,200})"'
            )
            seen: set[str] = set()
            items: list[dict] = []
            for m in pattern.finditer(html):
                vid, title = m.group(1), m.group(2)
                if vid in seen:
                    continue
                seen.add(vid)
                items.append(self._normalize({
                    "title": title,
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                    "engagement": "YouTube 급상승",
                }))
                if len(items) >= limit:
                    break
            if items:
                return items
        except Exception as exc:  # noqa: BLE001
            last_exc = last_exc or f"HTML fallback: {type(exc).__name__}: {str(exc)[:80]}"
            logger.warning("YouTube HTML fallback 실패: %s", exc)

        self.last_error = last_exc or "모든 경로 수집 실패. GOOGLE_API_KEY 설정 권장"
        return []

    # ------------------------------------------------------------------
    def _fetch_via_api(self, key: str, limit: int) -> list[dict]:
        """YouTube Data API v3 — mostPopular, regionCode=KR."""
        data = self.fetch_json(
            self.API_URL,
            params={
                "part": "snippet,statistics",
                "chart": "mostPopular",
                "regionCode": "KR",
                "maxResults": min(limit, 50),
                "key": key,
            },
            headers={"Referer": "https://www.youtube.com/"},
        )
        items: list[dict] = []
        for v in data.get("items", [])[:limit]:
            vid = v.get("id", "")
            sn = v.get("snippet", {}) or {}
            stats = v.get("statistics", {}) or {}
            views = int(stats.get("viewCount", 0) or 0)
            likes = int(stats.get("likeCount", 0) or 0)
            comments = int(stats.get("commentCount", 0) or 0)
            thumbs = sn.get("thumbnails", {}) or {}
            thumb = (
                (thumbs.get("medium") or thumbs.get("default") or {}).get("url", "")
            )
            items.append(self._normalize({
                "title": sn.get("title", ""),
                "url": f"https://www.youtube.com/watch?v={vid}",
                "summary": sn.get("channelTitle", ""),
                "thumbnail": thumb,
                "score": likes,
                "views": views,
                "comments": comments,
                "engagement": self.format_engagement(
                    score=likes, views=views, comments=comments
                ),
            }))
        return items

    def _parse_rss_entries(self, entries, limit: int) -> list[dict]:
        items: list[dict] = []
        for entry in entries[:limit]:
            title = entry.get("title", "")
            url = entry.get("link", "")
            summary = entry.get("summary", "") or entry.get("author", "")
            if not title:
                continue
            thumb = ""
            media = entry.get("media_thumbnail") or []
            if media:
                thumb = media[0].get("url", "")
            items.append(self._normalize({
                "title": title,
                "url": url,
                "summary": summary,
                "thumbnail": thumb,
                "engagement": "YouTube 급상승",
            }))
        return items
