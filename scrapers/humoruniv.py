"""웃긴대학 오늘의 베스트 스크래퍼."""
from __future__ import annotations

from urllib.parse import urljoin

from .base import BaseScraper


class HumorunivScraper(BaseScraper):
    source = "웃긴대학"
    base_url = "https://web.humoruniv.com/board/humor/list.html?table=pds&st=day"
    category = "유머/밈"
    encoding = "euc-kr"

    def parse(self, html: str) -> list[dict]:
        soup = self.soup(html)
        items: list[dict] = []

        for row in soup.select("tr.tb, tr.list_tr, table.board_list tr"):
            a = row.select_one("td.li_sbj a, a.li_sbj, a.subject")
            if not a:
                a = row.find("a", href=True)
            if not a:
                continue
            title = a.get_text(" ", strip=True)
            href = a.get("href") or ""
            if not title or not href:
                continue
            url = href if href.startswith("http") else urljoin("https://web.humoruniv.com/board/humor/", href)

            score = views = comments = 0
            tds = [td.get_text(strip=True) for td in row.find_all("td")]
            nums = [self.to_int(t) for t in tds if t and any(c.isdigit() for c in t)]
            nums = [n for n in nums if n]
            if len(nums) >= 2:
                views, score = nums[-2], nums[-1]

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
