"""네이버 트렌드.

- NAVER_CLIENT_ID/SECRET 설정 시 Naver Open API로 오늘자 핫 뉴스 수집
- 없으면 네이버뉴스 '많이 본 뉴스' 페이지 HTML 파싱
"""
from __future__ import annotations

import logging
from urllib.parse import urljoin

import requests

from config import get_naver_creds

from .base import BaseScraper

logger = logging.getLogger(__name__)

# 네이버 뉴스 검색 쿼리에 쓸 '오늘의 핫 이슈' 키워드들 (여러 개 병합)
HOT_QUERIES = ["오늘 속보", "실시간 이슈", "화제", "인기"]


class NaverTrendsScraper(BaseScraper):
    source = "네이버 트렌드"
    # 실검 공식 종료됐기에 대체재로 네이버뉴스 '많이 본 뉴스' 사용
    base_url = "https://news.naver.com/main/ranking/popularDay.naver"
    category = "이슈/뉴스"

    API_URL = "https://openapi.naver.com/v1/search/news.json"

    def parse(self, html: str) -> list[dict]:
        soup = self.soup(html)
        items: list[dict] = []

        for li in soup.select("ul.rankingnews_list li, div.rankingnews_box li"):
            a = li.select_one("a.list_title") or li.find("a", href=True)
            if not a:
                continue
            title = a.get_text(" ", strip=True)
            href = a.get("href") or ""
            if not title or not href:
                continue
            url = href if href.startswith("http") else urljoin("https://news.naver.com/", href)

            press = li.select_one("em.list_press, .list_press")
            summary = press.get_text(strip=True) if press else ""

            views_tag = li.select_one("span.list_view, .list_view")
            views = self.to_int(views_tag.get_text()) if views_tag else 0

            thumb_tag = li.select_one("img")
            thumb = thumb_tag.get("src", "") if thumb_tag else ""

            items.append({
                "title": title,
                "summary": summary,
                "url": url,
                "thumbnail": thumb,
                "score": 0,
                "views": views,
                "comments": 0,
                "engagement": self.format_engagement(views=views),
            })

            if len(items) >= 40:
                break
        return items

    # ------------------------------------------------------------------
    def get_trending(self, limit: int = 10) -> list[dict]:
        self.last_error = ""

        # 1) Naver Open API 시도
        creds = get_naver_creds()
        if creds:
            try:
                items = self._fetch_via_api(creds, limit)
                if items:
                    return items
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"Naver API 실패: {type(exc).__name__}: {str(exc)[:100]}"
                logger.warning(self.last_error)

        # 2) HTML fallback
        return super().get_trending(limit)

    def _fetch_via_api(self, creds: tuple[str, str], limit: int) -> list[dict]:
        """네이버 검색 API로 최신/인기 뉴스 집계."""
        cid, sec = creds
        headers = {
            "X-Naver-Client-Id": cid,
            "X-Naver-Client-Secret": sec,
            "User-Agent": "shorts-trend-collector/0.1",
        }
        seen_links: set[str] = set()
        items: list[dict] = []

        for q in HOT_QUERIES:
            if len(items) >= limit:
                break
            try:
                resp = requests.get(
                    self.API_URL,
                    params={"query": q, "display": 20, "sort": "sim"},
                    headers=headers,
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:  # noqa: BLE001
                logger.info("Naver API 쿼리 '%s' 실패: %s", q, exc)
                continue

            for row in data.get("items", []):
                link = row.get("originallink") or row.get("link", "")
                if not link or link in seen_links:
                    continue
                seen_links.add(link)
                title = _strip_html(row.get("title", ""))
                summary = _strip_html(row.get("description", ""))
                items.append(self._normalize({
                    "title": title,
                    "summary": summary,
                    "url": link,
                    "score": 0,
                    "views": 0,
                    "comments": 0,
                    "engagement": f"📰 {q}",
                }))
                if len(items) >= limit:
                    break
        return items


def _strip_html(text: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", text).replace("&quot;", '"').replace("&amp;", "&").strip()
