"""인스티즈 인티포털 이슈 스크래퍼."""
from __future__ import annotations

from urllib.parse import urljoin

from .base import BaseScraper


class InstizScraper(BaseScraper):
    source = "인스티즈"
    base_url = "https://www.instiz.net/pt"
    category = "연예"

    def parse(self, html: str) -> list[dict]:
        soup = self.soup(html)
        items: list[dict] = []

        for row in soup.select("table#mainTb tbody tr, table.listTable tbody tr, tr.listBtn"):
            a = row.select_one("td.listSubject a, td.subject a, a.subject")
            if not a:
                a = row.find("a", href=True)
            if not a:
                continue
            title = a.get_text(" ", strip=True)
            href = a.get("href") or ""
            if not title or not href:
                continue
            url = urljoin("https://www.instiz.net/", href)

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
