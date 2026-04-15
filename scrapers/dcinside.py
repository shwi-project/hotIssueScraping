"""디시인사이드 실시간 베스트 스크래퍼 (모바일 페이지)."""
from __future__ import annotations

import re
from urllib.parse import urljoin

from .base import BaseScraper


class DcinsideScraper(BaseScraper):
    source = "디시인사이드"
    base_url = "https://m.dcinside.com/board/dcbest"
    category = "유머/밈"

    def parse(self, html: str) -> list[dict]:
        soup = self.soup(html)
        items: list[dict] = []

        # 모바일 dcbest 목록은 <ul class="gall-list"> 내 <li>
        for li in soup.select("ul.gall-list li, ul.list-skin li, li.gall-li"):
            a = li.find("a", href=True)
            if not a:
                continue
            title_tag = a.find(class_=re.compile("subject|sub")) or a
            title = title_tag.get_text(strip=True)
            if not title:
                continue
            url = urljoin("https://m.dcinside.com", a["href"])

            # 추천/조회/댓글
            views = score = comments = 0
            for info in li.select(".info span, .gall-info span, .ginfo span"):
                t = info.get_text(strip=True)
                if "추천" in t or "♥" in t:
                    score = self.to_int(t)
                elif "조회" in t or "👁" in t:
                    views = self.to_int(t)
                elif "댓글" in t or "💬" in t:
                    comments = self.to_int(t)

            # 숫자 아이콘 클래스 기반 fallback
            if not (score or views or comments):
                nums = [self.to_int(s.get_text()) for s in li.select("em, strong")]
                nums = [n for n in nums if n]
                if len(nums) >= 3:
                    views, score, comments = nums[:3]

            items.append({
                "title": title,
                "url": url,
                "score": score,
                "views": views,
                "comments": comments,
                "engagement": self.format_engagement(score=score, views=views, comments=comments),
            })
        return items
