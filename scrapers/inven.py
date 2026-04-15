"""인벤 이슈게시판 스크래퍼."""
from __future__ import annotations

from urllib.parse import urljoin

from .base import BaseScraper


class InvenScraper(BaseScraper):
    source = "인벤"
    base_url = "https://www.inven.co.kr/board/webzine/2097"
    category = "게임"

    def parse(self, html: str) -> list[dict]:
        soup = self.soup(html)
        items: list[dict] = []

        for row in soup.select("table.board_list tbody tr, tbody tr.list_tr"):
            a = row.select_one("a.subject-link, td.tit a")
            if not a:
                a = row.find("a", href=True)
            if not a:
                continue
            title = a.get_text(strip=True)
            href = a.get("href") or ""
            if not title or not href:
                continue
            url = href if href.startswith("http") else urljoin("https://www.inven.co.kr/", href)

            views = self.to_int((row.select_one("td.view, td.hit") or {}).get_text() if row.select_one("td.view, td.hit") else "0")
            score = self.to_int((row.select_one("td.reco, td.recomm") or {}).get_text() if row.select_one("td.reco, td.recomm") else "0")
            cmt = row.select_one("span.con, span.comment")
            comments = self.to_int(cmt.get_text()) if cmt else 0

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
