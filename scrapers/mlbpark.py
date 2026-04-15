"""MLB파크 불펜 추천순 스크래퍼."""
from __future__ import annotations

from urllib.parse import urljoin

from .base import BaseScraper


class MlbparkScraper(BaseScraper):
    source = "MLB파크"
    base_url = "https://mlbpark.donga.com/mp/b.php?b=bullpen&m=bbs&p=1&s=2"
    category = "이슈/뉴스"

    def parse(self, html: str) -> list[dict]:
        soup = self.soup(html)
        items: list[dict] = []

        for row in soup.select("table.tbl_type01 tbody tr, table tbody tr"):
            a = row.select_one("td.t_left a, a.bulletlink, td.title a")
            if not a:
                a = row.find("a", href=True)
            if not a:
                continue
            title = a.get_text(" ", strip=True)
            href = a.get("href") or ""
            if not title or not href:
                continue
            url = urljoin("https://mlbpark.donga.com/mp/", href)

            score = views = comments = 0
            tds = [td.get_text(strip=True) for td in row.find_all("td")]
            nums = [self.to_int(t) for t in tds if t and any(c.isdigit() for c in t)]
            nums = [n for n in nums if n]
            if len(nums) >= 2:
                views, score = nums[-2], nums[-1]

            cmt = row.select_one("span.replycnt, span.cmtCnt")
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

            if len(items) >= 40:
                break
        return items
