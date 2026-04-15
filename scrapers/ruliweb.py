"""루리웹 베스트 히트 스크래퍼."""
from __future__ import annotations

from urllib.parse import urljoin

from .base import BaseScraper


class RuliwebScraper(BaseScraper):
    source = "루리웹"
    base_url = "https://bbs.ruliweb.com/best/hit"
    category = "게임"

    def parse(self, html: str) -> list[dict]:
        soup = self.soup(html)
        items: list[dict] = []

        for row in soup.select("table.board_list_table tbody tr, tr.table_body"):
            a = row.select_one("a.deco, td.subject a")
            if not a:
                a = row.find("a", href=True)
            if not a:
                continue
            title = a.get_text(strip=True)
            if not title:
                continue
            href = a.get("href") or ""
            url = urljoin("https://bbs.ruliweb.com/", href)

            cat_tag = row.select_one("td.divsn, .category")
            cat_text = cat_tag.get_text(strip=True) if cat_tag else self.category

            score = self.to_int((row.select_one("td.recomd") or row.select_one(".recomd")).get_text() if row.select_one("td.recomd, .recomd") else "0")
            views = self.to_int((row.select_one("td.hit") or row.select_one(".hit")).get_text() if row.select_one("td.hit, .hit") else "0")
            comments_tag = row.select_one("span.num_reply, .num_reply")
            comments = self.to_int(comments_tag.get_text()) if comments_tag else 0

            items.append({
                "title": title,
                "url": url,
                "category": cat_text or self.category,
                "score": score,
                "views": views,
                "comments": comments,
                "engagement": self.format_engagement(score=score, views=views, comments=comments),
            })

            if len(items) >= 40:
                break
        return items
