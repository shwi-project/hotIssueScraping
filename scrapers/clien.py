"""클리앙 모두의공원 + 인기글 스크래퍼."""
from __future__ import annotations

from urllib.parse import urljoin

from .base import BaseScraper


class ClienScraper(BaseScraper):
    source = "클리앙"
    base_url = "https://www.clien.net/service/board/park"
    category = "라이프"

    def parse(self, html: str) -> list[dict]:
        soup = self.soup(html)
        items: list[dict] = []

        for row in soup.select("div.list_item, div.list-item"):
            a = row.select_one("a.list_subject, a.subject_fixed")
            if not a:
                a = row.find("a", href=True)
            if not a:
                continue
            title_tag = a.select_one("span.subject_fixed") or a
            title = title_tag.get_text(" ", strip=True)
            href = a.get("href") or ""
            if not title or not href:
                continue
            url = urljoin("https://www.clien.net/", href)

            score_tag = row.select_one("div.list_symph, span.symph_count")
            views_tag = row.select_one("div.list_hit, span.hit")
            cmt_tag = row.select_one("a.list_reply, span.rSymph05")

            score = self.to_int(score_tag.get_text()) if score_tag else 0
            views = self.to_int(views_tag.get_text()) if views_tag else 0
            comments = self.to_int(cmt_tag.get_text()) if cmt_tag else 0

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
