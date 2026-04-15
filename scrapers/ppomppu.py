"""뽐뿌 핫딜 + 자유게시판 베스트 스크래퍼 (EUC-KR 인코딩)."""
from __future__ import annotations

from urllib.parse import urljoin

from .base import BaseScraper


class PpomppuScraper(BaseScraper):
    source = "뽐뿌"
    # 기본 URL은 핫딜 — 자유게시판 베스트는 get_trending에서 병합
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

        # 뽐뿌 게시판 테이블: <tr class="list0" ~ "list1">
        for tr in soup.select("tr.list0, tr.list1, tr.baseList"):
            a = tr.select_one("a.baseList-title, font.list_title a, td.list_vspace a, a[href*='view.php']")
            if not a:
                a = tr.find("a", href=True)
            if not a:
                continue
            title = a.get_text(strip=True)
            href = a.get("href") or ""
            if not title or not href:
                continue
            url = urljoin("https://www.ppomppu.co.kr/zboard/", href.lstrip("./"))

            # 추천/조회
            score = views = comments = 0
            tds = tr.find_all("td")
            texts = [td.get_text(strip=True) for td in tds]
            # 마지막 숫자들이 조회/추천
            nums = [self.to_int(t) for t in texts if t and t.replace(",", "").replace("-", "0").isdigit()]
            if len(nums) >= 2:
                score, views = nums[-2], nums[-1]
            # 댓글: 제목 옆 (숫자)
            cmt = tr.select_one("span.list_comment2, .baseList-c")
            if cmt:
                comments = self.to_int(cmt.get_text())

            items.append({
                "title": title,
                "url": url,
                "score": score,
                "views": views,
                "comments": comments,
                "engagement": self.format_engagement(score=score, views=views, comments=comments),
            })

            if len(items) >= 30:
                break
        return items

    def get_trending(self, limit: int = 10) -> list[dict]:
        """핫딜 + 자유게시판 베스트를 섞어서 반환."""
        half = max(1, limit // 2)
        # 1) 핫딜
        hot_deals = super().get_trending(limit=half)
        deal_error = self.last_error
        for it in hot_deals:
            it["category"] = "핫딜"

        # 2) 자유게시판 베스트
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
