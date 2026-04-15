"""네이버 트렌드 — 모바일 뉴스 많이 본 기사 기반 (실검 공식 종료됨)."""
from __future__ import annotations

import re
from urllib.parse import quote, urljoin

from .base import BaseScraper


class NaverTrendsScraper(BaseScraper):
    source = "네이버 트렌드"
    # 네이버 실시간검색어는 공식 종료됐기 때문에
    # 대체재로 네이버뉴스 '많이 본 뉴스'를 사용
    base_url = "https://news.naver.com/main/ranking/popularDay.naver"
    category = "이슈/뉴스"

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
