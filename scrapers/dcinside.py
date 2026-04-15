"""디시인사이드 실시간 베스트 스크래퍼.

모바일 dcbest 페이지의 레이아웃이 자주 변경되기 때문에 여러 셀렉터
패턴을 순차 시도하고, 실패 시 link-heuristic 방식으로 복구.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from .base import BaseScraper

_HREF_PATTERN = re.compile(r"/board/[^/]+/\d+")


class DcinsideScraper(BaseScraper):
    source = "디시인사이드"
    base_url = "https://m.dcinside.com/board/dcbest"
    category = "유머/밈"

    def parse(self, html: str) -> list[dict]:
        soup = self.soup(html)
        items: list[dict] = []

        # 1차 — 다양한 CSS 셀렉터 시도
        for li in soup.select(
            "ul.gall-list > li, ul.list-skin > li, li.gall-li, "
            "ul.gl-list > li, div.gallery-list > li, "
            "div.gall_list li, .gall-list li, .list_block li"
        ):
            parsed = self._extract_from_li(li)
            if parsed:
                items.append(parsed)

        # 2차 — link-heuristic: dcbest/정규식에 매칭되는 앵커 탐색
        if not items:
            seen_hrefs: set[str] = set()
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if not _HREF_PATTERN.search(href):
                    continue
                if href in seen_hrefs:
                    continue
                title = a.get_text(" ", strip=True)
                if not title or len(title) < 4:
                    continue
                seen_hrefs.add(href)
                url = urljoin("https://m.dcinside.com", href)
                items.append({
                    "title": title,
                    "url": url,
                    "score": 0,
                    "views": 0,
                    "comments": 0,
                    "engagement": "",
                })
        return items

    def _extract_from_li(self, li) -> dict | None:
        # 공지 li 제외
        li_classes = " ".join(li.get("class", [])).lower()
        if any(k in li_classes for k in ("notice", "noti", "top-notice", "best-notice")):
            return None

        a = li.find("a", href=True)
        if not a:
            return None
        href = a["href"]
        title_tag = (
            a.find(class_=re.compile("subject|sub|title", re.I))
            or li.find(class_=re.compile("subject|sub|title", re.I))
            or a
        )
        title = title_tag.get_text(" ", strip=True)
        if not title or len(title) < 3:
            return None
        url = urljoin("https://m.dcinside.com", href)

        views = score = comments = 0
        for info in li.select(".info span, .gall-info span, .ginfo span, .meta span, em, strong"):
            t = info.get_text(" ", strip=True)
            if "추천" in t or "♥" in t or "👍" in t:
                score = score or self.to_int(t)
            elif "조회" in t or "👁" in t:
                views = views or self.to_int(t)
            elif "댓글" in t or "💬" in t or t.startswith("[") and t.endswith("]"):
                comments = comments or self.to_int(t)

        return {
            "title": title,
            "url": url,
            "score": score,
            "views": views,
            "comments": comments,
            "engagement": self.format_engagement(score=score, views=views, comments=comments),
        }
