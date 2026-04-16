"""웃긴대학 오늘의 베스트 스크래퍼."""
from __future__ import annotations

from urllib.parse import urljoin

from .base import BaseScraper


class HumorunivScraper(BaseScraper):
    source = "웃긴대학"
    base_url = "https://web.humoruniv.com/board/humor/list.html?table=pds&st=day"
    category = "유머/밈"
    encoding = "euc-kr"

    _BASE = "https://web.humoruniv.com"

    def parse(self, html: str) -> list[dict]:
        soup = self.soup(html)
        items: list[dict] = []

        # 다양한 HTML 구조 대응
        rows = (
            soup.select("tr.tb")
            or soup.select("tr.list_tr")
            or soup.select("table.board_list tr")
            or soup.select("table tr")
        )

        for row in rows:
            # 제목 링크 - 우선순위 순으로 시도
            a = (row.select_one("td.li_sbj a")
                 or row.select_one("a.li_sbj")
                 or row.select_one("td.subject a")
                 or row.select_one("a.subject"))
            if not a:
                continue
            title = a.get_text(" ", strip=True)
            href = a.get("href") or ""
            if not title or not href:
                continue

            # URL 정규화 — 절대/상대/루트 상대 모두 처리
            if href.startswith("http"):
                url = href
            elif href.startswith("/"):
                url = self._BASE + href
            else:
                url = urljoin("https://web.humoruniv.com/board/humor/", href)

            score = views = comments = 0
            tds = [td.get_text(strip=True) for td in row.find_all("td")]
            nums = [self.to_int(t) for t in tds if t and any(c.isdigit() for c in t)]
            nums = [n for n in nums if n]
            if len(nums) >= 2:
                views, score = nums[-2], nums[-1]
            elif len(nums) == 1:
                views = nums[0]

            items.append({
                "title": title,
                "url": url,
                "score": score,
                "views": views,
                "comments": comments,
                "engagement": self.format_engagement(score=score, views=views, comments=comments),
            })

            if len(items) >= 40:
                break
        return items
