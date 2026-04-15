"""YouTube 한국 인기 급상승.

우선순위:
1) GOOGLE_API_KEY (또는 YOUTUBE_API_KEY) → YouTube Data API v3 (권장)
2) HTML 페이지 파싱 (fallback)

※ 과거엔 RSS `chart=trending` 을 시도했으나 YouTube가 공식적으로 비활성화해서
   `not well-formed` 파싱 오류가 잦으므로 제거.
"""
from __future__ import annotations

import logging
import re

from config import get_google_key

from .base import BaseScraper

logger = logging.getLogger(__name__)


class YoutubeTrendsScraper(BaseScraper):
    source = "YouTube 인기"
    base_url = "https://www.youtube.com/feed/trending?gl=KR&hl=ko"
    category = "연예"

    API_URL = "https://www.googleapis.com/youtube/v3/videos"

    def parse(self, html: str) -> list[dict]:
        """HTML fallback — JSON-in-HTML 에서 videoId/title 추출."""
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
            items.append({
                "title": title,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                "engagement": "YouTube 급상승",
            })
            if len(items) >= 50:
                break
        return items

    def get_trending(self, limit: int = 10) -> list[dict]:
        self.last_error = ""

        # 1) Google API (권장)
        google_key = get_google_key()
        if google_key:
            try:
                items = self._fetch_via_api(google_key, limit)
                if items:
                    return items
                self.last_error = "YouTube API 응답 없음"
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"YouTube Data API 실패: {type(exc).__name__}: {str(exc)[:100]}"
                logger.warning(self.last_error)

        # 2) HTML fallback
        fallback = super().get_trending(limit=limit)
        if fallback:
            return fallback

        if not self.last_error:
            self.last_error = (
                "GOOGLE_API_KEY 설정 권장. HTML fallback도 실패 "
                "(YouTube가 봇으로 감지하는 중)"
            )
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
