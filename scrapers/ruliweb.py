"""루리웹 베스트 히트 — RSS 우선, 실패 시 모바일/데스크톱 순차 시도."""
from __future__ import annotations

import re
from urllib.parse import urljoin

from .base import BaseScraper


class RuliwebScraper(BaseScraper):
    source = "루리웹"
    base_url = "https://bbs.ruliweb.com/best/hit"
    category = "게임"

    # RSS 피드 후보 (루리웹은 여러 보드에 RSS 제공)
    RSS_URLS = [
        "https://bbs.ruliweb.com/best/rss.xml",
        "https://bbs.ruliweb.com/best/rss",
        "https://bbs.ruliweb.com/rss.xml",
    ]
    # 모바일/데스크톱 fallback
    FALLBACK_URLS = [
        "https://m.ruliweb.com/best/hit",
        "https://bbs.ruliweb.com/best",
    ]

    def parse(self, html: str) -> list[dict]:
        soup = self.soup(html)
        items: list[dict] = []

        # 데스크톱 테이블 기반
        for row in soup.select(
            "table.board_list_table tbody tr, tr.table_body, "
            "table.board_list tbody tr"
        ):
            parsed = self._extract_from_row(row)
            if parsed:
                items.append(parsed)

        # 모바일 li 기반 (fallback 에서 주로 매칭)
        if len(items) < 3:
            for li in soup.select(
                "ul.best-list li, ul.list-body li, li.mlist, div.board-list li"
            ):
                parsed = self._extract_from_li(li)
                if parsed:
                    items.append(parsed)

        # 공지 제거
        items = [it for it in items if it.get("title")]
        return items

    def _extract_from_row(self, row) -> dict | None:
        cls = " ".join(row.get("class", [])).lower()
        if "notice" in cls:
            return None

        a = row.select_one("a.deco, td.subject a, td.title a, a.link") \
            or row.find("a", href=True)
        if not a:
            return None
        title = a.get_text(" ", strip=True)
        if not title or len(title) < 5:
            return None
        href = a.get("href") or ""
        url = href if href.startswith("http") else urljoin(
            "https://bbs.ruliweb.com/", href
        )

        cat = row.select_one("td.divsn, .category")
        cat_text = cat.get_text(strip=True) if cat else self.category

        def _td_num(selector: str) -> int:
            tag = row.select_one(selector)
            return self.to_int(tag.get_text()) if tag else 0

        score = _td_num("td.recomd, .recomd, td.like")
        views = _td_num("td.hit, .hit, td.view")
        cmt_tag = row.select_one("span.num_reply, .num_reply, .reply-count")
        comments = self.to_int(cmt_tag.get_text()) if cmt_tag else 0

        return {
            "title": title,
            "url": url,
            "category": cat_text or self.category,
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
        if not title or len(title) < 5:
            return None
        href = a.get("href") or ""
        url = href if href.startswith("http") else urljoin(
            "https://m.ruliweb.com/", href
        )

        text = li.get_text(" ", strip=True)
        m_s = re.search(r"(?:추천|좋아요)[\s:]*([\d,]+)", text)
        m_v = re.search(r"(?:조회|view|hit)[\s:]*([\d,]+)", text, re.I)
        m_c = re.search(r"(?:댓글|reply)[\s:]*([\d,]+)", text, re.I)
        score = self.to_int(m_s.group(1)) if m_s else 0
        views = self.to_int(m_v.group(1)) if m_v else 0
        comments = self.to_int(m_c.group(1)) if m_c else 0

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

    def get_trending(self, limit: int = 10) -> list[dict]:
        self.last_error = ""
        # 1) RSS 시도 (가장 안정적)
        for rss in self.RSS_URLS:
            rss_items = self._fetch_rss(rss, limit, self.source)
            if rss_items:
                return [self._normalize(it) for it in rss_items]
        # 2) 데스크톱 기본 URL
        try:
            parent_items = super().get_trending(limit)
            if parent_items:
                return parent_items
        except Exception:  # noqa: BLE001
            pass
        # 3) fallback URLs
        fb_items = self._try_urls(self.FALLBACK_URLS, limit)
        if fb_items:
            return [self._normalize(it) for it in fb_items[:limit]]
        if not self.last_error:
            self.last_error = "RSS/모바일/데스크톱 모두 실패"
        return []
