"""아카라이브 랭킹 스크래퍼."""
from __future__ import annotations

from urllib.parse import urljoin

from .base import BaseScraper


class ArcaliveScraper(BaseScraper):
    source = "아카라이브"
    base_url = "https://arca.live/b/live"
    category = "유머/밈"

    def parse(self, html: str) -> list[dict]:
        soup = self.soup(html)
        items: list[dict] = []

        for a in soup.select("a.vrow, a.title"):
            href = a.get("href") or ""
            title_tag = a.select_one("span.title, .vcol.col-title") or a
            title = title_tag.get_text(" ", strip=True)
            if not title or not href:
                continue
            url = urljoin("https://arca.live/", href)

            score = self.to_int((a.select_one("span.vcol.col-rate") or {}).get_text() if a.select_one("span.vcol.col-rate") else "0")
            views = self.to_int((a.select_one("span.vcol.col-view") or {}).get_text() if a.select_one("span.vcol.col-view") else "0")
            cmt = a.select_one("span.comment-count")
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
