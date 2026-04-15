"""뽐뿌 핫딜 + 자유게시판 베스트 스크래퍼 (EUC-KR)."""
from __future__ import annotations

import re
from urllib.parse import urljoin

from .base import BaseScraper

_VIEW_PATTERN = re.compile(r"view\.php|zboard\.php")


class PpomppuScraper(BaseScraper):
    source = "뽐뿌"
    # 뽐뿌 통합 HOT 핫딜 (실제 인기만 올라옴)
    base_url = "https://www.ppomppu.co.kr/hot.php"
    category = "핫딜"
    encoding = "euc-kr"

    # fallback 후보들
    FALLBACK_URLS = [
        "https://www.ppomppu.co.kr/zboard/zboard.php?id=ppomppu",
        "https://www.ppomppu.co.kr/zboard/zboard.php?id=ppomppu_4",
    ]

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
        # 공지 row 제외 — 클래스 / 이미지 / 배경색 기반
        tr_classes = " ".join(tr.get("class", [])).lower()
        if any(k in tr_classes for k in ("notice", "noti", "board_notice", "top_notice")):
            return None
        # 공지 이미지가 있는 행도 스킵 (ppomppu는 /img/icons/notice.gif 등 사용)
        if tr.find("img", src=re.compile(r"notice|공지", re.I)):
            return None

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
        """핫딜 HOT + 자유게시판 베스트 결합."""
        half = max(1, limit // 2)

        # 1) HOT 페이지 시도 → 실패 시 fallback URL 순차 시도
        hot_deals = super().get_trending(limit=half)
        deal_error = self.last_error
        if not hot_deals:
            for fb_url in self.FALLBACK_URLS:
                try:
                    html = self.fetch(fb_url)
                    parsed = self.parse(html)
                    # _is_notice_or_ad 필터와 정렬은 get_trending에서만 되니 수동 적용
                    parsed = [it for it in parsed if not self._is_notice_or_ad(it)]
                    if parsed:
                        hot_deals = [self._normalize(it) for it in parsed[:half]]
                        deal_error = ""
                        break
                except Exception as exc:  # noqa: BLE001
                    deal_error = f"{type(exc).__name__}: {str(exc)[:80]}"
        for it in hot_deals:
            it["category"] = "핫딜"

        # 2) 자유게시판 베스트
        free_items: list[dict] = []
        free_error = ""
        try:
            html = self.fetch(self.FREE_BEST_URL)
            parsed = self.parse(html)
            parsed = [it for it in parsed if not self._is_notice_or_ad(it)]
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
