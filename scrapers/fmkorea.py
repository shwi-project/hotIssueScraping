"""에펨코리아 인기글(베스트) 스크래퍼."""
from __future__ import annotations

from urllib.parse import urljoin

from .base import BaseScraper


class FmkoreaScraper(BaseScraper):
    source = "에펨코리아"
    base_url = "https://www.fmkorea.com/index.php?mid=best"
    category = "유머/밈"

    def parse(self, html: str) -> list[dict]:
        soup = self.soup(html)
        items: list[dict] = []

        # 게시판 레이아웃: <div class="fm_best_widget"> 또는 리스트 테이블
        for row in soup.select("li.li_best2_pop0, li.li, tr.notice_pop1, tbody tr"):
            a = row.select_one("a.hx, a[href*='/best/'], h3.title a, td.title a")
            if not a:
                a = row.find("a", href=True)
            if not a:
                continue
            title = a.get_text(strip=True)
            href = a.get("href") or ""
            if not title or not href:
                continue
            url = urljoin("https://www.fmkorea.com/", href)

            # 추천수/조회수
            score = views = comments = 0
            for span in row.select("span.count, span.m_no, td.m_no"):
                t = span.get_text(strip=True)
                if "추천" in t:
                    score = self.to_int(t)
                elif "조회" in t or "views" in t.lower():
                    views = self.to_int(t)

            # 댓글은 제목 끝의 [숫자] 패턴
            cmt = row.select_one("span.comment_count, a.replyNum")
            if cmt:
                comments = self.to_int(cmt.get_text())

            # 숫자 td들이 나란히 있는 경우 fallback
            if not (score or views):
                tds = [td.get_text(strip=True) for td in row.find_all("td")]
                nums = [self.to_int(x) for x in tds if x and any(c.isdigit() for c in x)]
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

            if len(items) >= 50:
                break
        return items
