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
        # 패턴 1: 일반적인 ytInitialData 구조
        pattern1 = re.compile(
            r'"videoId":"([A-Za-z0-9_-]{11})"[^}]{0,400}?"title":\{"runs":\[\{"text":"([^"]{5,200})"'
        )
        # 패턴 2: simpleText 방식
        pattern2 = re.compile(
            r'"videoId":"([A-Za-z0-9_-]{11})"[^}]{0,400}?"title":\{"simpleText":"([^"]{5,200})"'
        )
        seen: set[str] = set()
        items: list[dict] = []
        for pattern in (pattern1, pattern2):
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
            if items:
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
        """YouTube Data API v3 — mostPopular, regionCode=KR.

        cloudscraper 세션 대신 직접 requests 사용 (Google API는 CF 우회 불필요).
        Referer 헤더도 제거 (API 키에 웹사이트 제한 걸려 있으면 오히려 방해).
        """
        import requests as _rq
        resp = _rq.get(
            self.API_URL,
            params={
                "part": "snippet,statistics",
                "chart": "mostPopular",
                "regionCode": "KR",
                "hl": "ko",
                "maxResults": min(max(limit, 10), 50),
                "key": key,
            },
            headers={
                "Accept": "application/json",
                "User-Agent": "shorts-trend-collector/1.0",
            },
            timeout=15,
        )
        if resp.status_code != 200:
            # 에러 상세 메시지 추출 (Google API 에러는 JSON body 에 정보 많음)
            err_reason = "unknown"
            err_msg = ""
            try:
                err_body = resp.json()
                err_info = err_body.get("error", {})
                err_msg = err_info.get("message", "")
                errors_list = err_info.get("errors") or [{}]
                err_reason = errors_list[0].get("reason", "unknown")
            except Exception:  # noqa: BLE001 — JSON 파싱 실패 시 raw 텍스트
                err_msg = resp.text[:200]
            raise RuntimeError(
                f"HTTP {resp.status_code} [{err_reason}] {err_msg}"
            )

        data = resp.json()
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
