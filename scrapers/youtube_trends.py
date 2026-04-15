"""YouTube 한국 인기 급상승 (RSS + HTML fallback)."""
from __future__ import annotations

import logging

import feedparser

from .base import BaseScraper

logger = logging.getLogger(__name__)


class YoutubeTrendsScraper(BaseScraper):
    source = "YouTube 인기"
    base_url = "https://www.youtube.com/feeds/videos.xml?chart=trending&geo=KR"
    category = "연예"

    def parse(self, html: str) -> list[dict]:
        return []

    def get_trending(self, limit: int = 10) -> list[dict]:
        self.last_error = ""
        items: list[dict] = []
        last_exc: str = ""

        # 1) RSS 시도
        try:
            feed = feedparser.parse(self.base_url)
            if getattr(feed, "bozo", 0) and not feed.entries:
                last_exc = f"RSS 파싱 실패: {getattr(feed, 'bozo_exception', 'unknown')}"
            for entry in feed.entries[:limit]:
                title = entry.get("title", "")
                url = entry.get("link", "")
                summary = entry.get("summary", "") or entry.get("author", "")
                if not title:
                    continue
                # 썸네일
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
        except Exception as exc:  # noqa: BLE001
            last_exc = f"RSS 예외: {type(exc).__name__}: {str(exc)[:80]}"
            logger.info("YouTube RSS 실패: %s", exc)

        if items:
            return items[:limit]

        # 2) HTML fallback — 한국 인기 페이지
        try:
            html = self.fetch("https://www.youtube.com/feed/trending?gl=KR&hl=ko")
            # YouTube는 JSON-in-HTML 이므로 정교 파싱 대신
            # 제목/링크만 대충 추출
            import re
            pattern = re.compile(
                r'"videoId":"([^"]+)"[^}]{0,200}?"title":\{"runs":\[\{"text":"([^"]{5,200})"'
            )
            seen = set()
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
        except Exception as exc:  # noqa: BLE001
            last_exc = f"HTML fallback 실패: {type(exc).__name__}: {str(exc)[:80]}"
            logger.warning("YouTube HTML fallback 실패: %s", exc)

        if not items:
            self.last_error = last_exc or "RSS/HTML 모두 결과 없음"
        return items[:limit]
