"""더쿠 핫이슈 스크래퍼."""
from __future__ import annotations

from urllib.parse import urljoin

from .base import BaseScraper


class TheqooScraper(BaseScraper):
    source = "더쿠"
    base_url = "https://theqoo.net/hot"
    category = "연예"

    def parse(self, html: str) -> list[dict]:
        soup = self.soup(html)
        items: list[dict] = []

        for tr in soup.select("table.hide_notice tr, table tr"):
            a = tr.select_one("td.title a, a.hx")
            if not a:
                a = tr.find("a", href=True)
            if not a:
                continue
            title = a.get_text(" ", strip=True)
            href = a.get("href") or ""
            if not title or not href:
                continue
            url = urljoin("https://theqoo.net/", href.lstrip("/"))

            # 댓글수: 제목 옆 [숫자]
            cmt_tag = tr.select_one("a.replyNum, span.cmt_count")
            comments = self.to_int(cmt_tag.get_text()) if cmt_tag else 0

            # 조회수 / 추천
            views = score = 0
            tds = tr.find_all("td")
            nums = [self.to_int(td.get_text(strip=True)) for td in tds if td.get_text(strip=True)]
            nums = [n for n in nums if n]
            if len(nums) >= 2:
                # 더쿠는 보통 [날짜, 조회, 추천]
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
