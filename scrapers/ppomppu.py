"""뽐뿌 핫딜 + 자유게시판 베스트 스크래퍼 (EUC-KR)."""
from __future__ import annotations

import re
from urllib.parse import urljoin

from .base import BaseScraper

_VIEW_PATTERN = re.compile(r"view\.php|zboard\.php")


class PpomppuScraper(BaseScraper):
    source = "뽐뿌"
    base_url = "https://www.ppomppu.co.kr/zboard/zboard.php?id=ppomppu"
    category = "핫딜"
    encoding = "euc-kr"

    FREE_BEST_URL = (
        "https://www.ppomppu.co.kr/zboard/zboard.php"
        "?id=freeboard&page=1&category=999"
    )

    def parse(self, html: str) -> list[dict]:
        soup = self.soup(html)
        items: list[dict] = []

        # 1차 — 기존 테이블 row 셀렉터 전수 시도
        rows = soup.select(
            "tr.list0, tr.list1, tr.baseList, "
            "table.board_table tr, table#revolution_main_table tr"
        )
        for tr in rows:
            parsed = self._extract_from_tr(tr)
            if parsed:
                items.append(parsed)

        # 2차 — link-heuristic
        if not items:
            seen: set[str] = set()
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if not _VIEW_PATTERN.search(href):
                    continue
                # 페이지 네비게이션 제외
                if "page=" in href and "no=" not in href:
                    continue
                title = a.get_text(" ", strip=True)
                if not title or len(title) < 5:
                    continue
                if href in seen:
                    continue
                seen.add(href)
                url = href if href.startswith("http") else urljoin(
                    "https://www.ppomppu.co.kr/zboard/", href.lstrip("./")
                )
                items.append({
                    "title": title,
                    "url": url,
                    "score": 0,
                    "views": 0,
                    "comments": 0,
                    "engagement": "",
                })
                if len(items) >= 30:
                    break
        return items

    def _extract_from_tr(self, tr) -> dict | None:
        a = tr.select_one(
            "a.baseList-title, font.list_title a, td.list_vspace a, "
            "a[href*='view.php'], a[href*='no=']"
        )
        if not a:
            a = tr.find("a", href=True)
        if not a:
            return None
        title = a.get_text(" ", strip=True)
        href = a.get("href") or ""
        if not title or not href or len(title) < 3:
            return None
        url = href if href.startswith("http") else urljoin(
            "https://www.ppomppu.co.kr/zboard/", href.lstrip("./")
        )

        score = views = comments = 0
        tds = tr.find_all("td")
        texts = [td.get_text(" ", strip=True) for td in tds]
        nums = [self.to_int(t) for t in texts if t and t.replace(",", "").replace("-", "0").isdigit()]
        nums = [n for n in nums if n]
        if len(nums) >= 2:
            score, views = nums[-2], nums[-1]
        cmt = tr.select_one("span.list_comment2, .baseList-c")
        if cmt:
            comments = self.to_int(cmt.get_text())

        return {
            "title": title,
            "url": url,
            "score": score,
            "views": views,
            "comments": comments,
            "engagement": self.format_engagement(score=score, views=views, comments=comments),
        }

    def get_trending(self, limit: int = 10) -> list[dict]:
        """핫딜 + 자유게시판 베스트 결합."""
        half = max(1, limit // 2)
        hot_deals = super().get_trending(limit=half)
        deal_error = self.last_error
        for it in hot_deals:
            it["category"] = "핫딜"

        free_items: list[dict] = []
        free_error = ""
        try:
            html = self.fetch(self.FREE_BEST_URL)
            parsed = self.parse(html)
            for it in parsed[:limit - len(hot_deals)]:
                norm = self._normalize({**it, "category": "유머/밈"})
                free_items.append(norm)
        except Exception as exc:  # noqa: BLE001
            free_error = f"{type(exc).__name__}: {str(exc)[:80]}"

        combined = (hot_deals + free_items)[:limit]
        if combined:
            self.last_error = ""
        else:
            self.last_error = deal_error or free_error or "핫딜/자유베스트 모두 0건"
        return combined
