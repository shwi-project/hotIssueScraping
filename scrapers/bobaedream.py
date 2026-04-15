"""보배드림 베스트 게시판 스크래퍼."""
from __future__ import annotations

from urllib.parse import urljoin

from .base import BaseScraper


class BobaedreamScraper(BaseScraper):
    source = "보배드림"
    base_url = "https://www.bobaedream.co.kr/list?code=best"
    category = "이슈/뉴스"

    def parse(self, html: str) -> list[dict]:
        soup = self.soup(html)
        items: list[dict] = []

        for row in soup.select("table.basic_table tbody tr, table.boardlist tbody tr"):
            a = row.select_one("a.bsubject, td.pl14 a, a.list_title")
            if not a:
                a = row.find("a", href=True)
            if not a:
                continue
            title = a.get_text(" ", strip=True)
            href = a.get("href") or ""
            if not title or not href:
                continue
            url = href if href.startswith("http") else urljoin("https://www.bobaedream.co.kr/", href)

            score = views = comments = 0
            for td in row.find_all("td"):
                cls = " ".join(td.get("class", []))
                t = td.get_text(strip=True)
                if "count" in cls or "hit" in cls:
                    views = views or self.to_int(t)
                elif "recom" in cls or "up" in cls:
                    score = score or self.to_int(t)

            cmt = row.select_one("span.commentNum, em.cr")
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
