"""인스티즈 이슈/포털 스크래퍼 — 모바일 fallback + 다중 셀렉터."""
from __future__ import annotations

import re
from urllib.parse import urljoin

from .base import BaseScraper


class InstizScraper(BaseScraper):
    source = "인스티즈"
    base_url = "https://www.instiz.net/pt"
    category = "연예"

    # 모바일 / 대체 페이지
    FALLBACK_URLS = [
        "https://m.instiz.net/pt",
        "https://www.instiz.net/pt_issue",
    ]

    def parse(self, html: str) -> list[dict]:
        soup = self.soup(html)
        items: list[dict] = []

        # 데스크톱 tr
        for row in soup.select(
            "table#mainTb tbody tr, table.listTable tbody tr, "
            "tr.listBtn, table.list tbody tr"
        ):
            parsed = self._extract_from_tr(row)
            if parsed:
                items.append(parsed)

        # 모바일 li
        if len(items) < 3:
            for li in soup.select(
                "ul.mobile-list li, ul.pt-list li, "
                "div.board-list li, section li"
            ):
                parsed = self._extract_from_li(li)
                if parsed:
                    items.append(parsed)

        return items

    def _extract_from_tr(self, row) -> dict | None:
        cls = " ".join(row.get("class", [])).lower()
        if "notice" in cls or "noti" in cls:
            return None

        a = row.select_one("td.listSubject a, td.subject a, a.subject") \
            or row.find("a", href=True)
        if not a:
            return None
        title = a.get_text(" ", strip=True)
        href = a.get("href") or ""
        if not title or not href or len(title) < 5:
            return None
        url = href if href.startswith("http") else urljoin(
            "https://www.instiz.net/", href
        )

        score = views = comments = 0
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
            "comments": comments,
            "engagement": self.format_engagement(
                score=score, views=views, comments=comments
            ),
        }

    def _extract_from_li(self, li) -> dict | None:
        a = li.find("a", href=True)
        if not a:
            return None
        title_el = li.select_one(".title, .subject, .sbj, strong") or a
        title = title_el.get_text(" ", strip=True)
        href = a.get("href") or ""
        if not title or len(title) < 5:
            return None
        url = href if href.startswith("http") else urljoin(
            "https://m.instiz.net/", href
        )

        text = li.get_text(" ", strip=True)
        m_s = re.search(r"(?:추천|좋아요)[\s:]*([\d,]+)", text)
        m_v = re.search(r"(?:조회|hit)[\s:]*([\d,]+)", text, re.I)
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
        # 1) 기본 URL
        items = super().get_trending(limit)
        if items:
            return items
        # 2) 모바일 fallback
        fb_items = self._try_urls(self.FALLBACK_URLS, limit)
        if fb_items:
            return [self._normalize(it) for it in fb_items[:limit]]
        if not self.last_error:
            self.last_error = "데스크톱/모바일 모두 실패"
        return []
