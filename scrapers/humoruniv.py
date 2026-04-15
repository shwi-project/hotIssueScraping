"""웃긴대학 베스트 — 데스크톱 + 모바일 fallback."""
from __future__ import annotations

import re
from urllib.parse import urljoin

from .base import BaseScraper


class HumorunivScraper(BaseScraper):
    source = "웃긴대학"
    base_url = "https://web.humoruniv.com/board/humor/list.html?table=pds&st=day"
    category = "유머/밈"
    encoding = "euc-kr"

    FALLBACK_URLS = [
        "https://m.humoruniv.com/",
        "https://m.humoruniv.com/board/humor/list.html?table=pds&st=day",
        "https://web.humoruniv.com/",
        "https://web.humoruniv.com/board/humor/list.html?table=pds",
    ]

    def parse(self, html: str) -> list[dict]:
        soup = self.soup(html)
        items: list[dict] = []

        # 데스크톱 table
        for row in soup.select(
            "tr.tb, tr.list_tr, table.board_list tr, "
            "table#board_list tr, tbody tr"
        ):
            parsed = self._extract_from_tr(row)
            if parsed:
                items.append(parsed)

        # 모바일 li
        if len(items) < 3:
            for li in soup.select("ul.list li, div.list li, article li, section li"):
                parsed = self._extract_from_li(li)
                if parsed:
                    items.append(parsed)

        return items

    def _extract_from_tr(self, row) -> dict | None:
        cls = " ".join(row.get("class", [])).lower()
        if "notice" in cls or "noti" in cls:
            return None

        a = row.select_one("td.li_sbj a, a.li_sbj, a.subject, td.subject a") \
            or row.find("a", href=True)
        if not a:
            return None
        title = a.get_text(" ", strip=True)
        href = a.get("href") or ""
        if not title or not href or len(title) < 5:
            return None
        url = href if href.startswith("http") else urljoin(
            "https://web.humoruniv.com/board/humor/", href
        )

        score = views = 0
        tds = [td.get_text(" ", strip=True) for td in row.find_all("td")]
        nums = [self.to_int(t) for t in tds if t and any(c.isdigit() for c in t)]
        nums = [n for n in nums if 0 < n < 10_000_000]
        if len(nums) >= 2:
            views, score = nums[-2], nums[-1]

        return {
            "title": title,
            "url": url,
            "score": score,
            "views": views,
            "comments": 0,
            "engagement": self.format_engagement(score=score, views=views),
        }

    def _extract_from_li(self, li) -> dict | None:
        a = li.find("a", href=True)
        if not a:
            return None
        title = a.get_text(" ", strip=True)
        href = a.get("href") or ""
        if not title or len(title) < 5 or not href:
            return None
        url = href if href.startswith("http") else urljoin(
            "https://m.humoruniv.com/", href
        )

        text = li.get_text(" ", strip=True)
        m_s = re.search(r"(?:추천|\u25B2)[\s:]*([\d,]+)", text)
        m_v = re.search(r"(?:조회|hit|view)[\s:]*([\d,]+)", text, re.I)
        score = self.to_int(m_s.group(1)) if m_s else 0
        views = self.to_int(m_v.group(1)) if m_v else 0

        return {
            "title": title,
            "url": url,
            "score": score,
            "views": views,
            "comments": 0,
            "engagement": self.format_engagement(score=score, views=views),
        }

    def get_trending(self, limit: int = 10) -> list[dict]:
        self.last_error = ""
        items = super().get_trending(limit)
        if items:
            return items
        fb_items = self._try_urls(self.FALLBACK_URLS, limit)
        if fb_items:
            return [self._normalize(it) for it in fb_items[:limit]]
        if not self.last_error:
            self.last_error = "데스크톱/모바일 모두 실패"
        return []
