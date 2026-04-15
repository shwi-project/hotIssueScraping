"""네이트판 톡톡 랭킹 스크래퍼."""
from __future__ import annotations

from urllib.parse import urljoin

from .base import BaseScraper


class NatepanScraper(BaseScraper):
    source = "네이트판"
    base_url = "https://pann.nate.com/talk/ranking"
    category = "이슈/뉴스"

    def parse(self, html: str) -> list[dict]:
        soup = self.soup(html)
        items: list[dict] = []

        for li in soup.select("ul.post_wrap li, ol.wrapList li, div.post_list li"):
            a = li.select_one("a.tit, a.subject, dt a")
            if not a:
                a = li.find("a", href=True)
            if not a:
                continue
            title = a.get_text(strip=True)
            href = a.get("href") or ""
            if not title:
                continue
            url = urljoin("https://pann.nate.com/", href)

            # 공감/조회/댓글
            info = li.select_one(".info, .postInfo, dd.etc") or li
            text = info.get_text(" ", strip=True)

            score = views = comments = 0
            # '공감 123 조회 4567 댓글 89'
            for part in text.split():
                pass
            # 클래스 기반
            for el in li.select("span, em, dd"):
                t = el.get_text(strip=True)
                if "공감" in t:
                    score = self.to_int(t)
                elif "조회" in t:
                    views = self.to_int(t)
                elif "댓글" in t:
                    comments = self.to_int(t)

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
