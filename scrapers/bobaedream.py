"""보배드림 베스트 게시판 스크래퍼."""
from __future__ import annotations

from urllib.parse import urljoin

from .base import BaseScraper


class BobaedreamScraper(BaseScraper):
    source = "보배드림"
    base_url = "https://www.bobaedream.co.kr/list?code=best"
    category = "이슈/뉴스"
    # 보배드림은 Cloudflare 보호로 응답이 느림 → 타임아웃 넉넉하게
    scraper_timeout = 30

    FALLBACK_URLS = [
        "https://m.bobaedream.co.kr/list?code=best",
        "https://www.bobaedream.co.kr/best",
    ]

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

    def get_trending(self, limit: int = 10) -> list[dict]:
        """메인 URL 시도 → Cloudflare 리다이렉트 감지 시 폴백 URL 순서로 시도."""
        urls = [self.base_url] + self.FALLBACK_URLS
        for url in urls:
            try:
                html = self.fetch(url)
                # cure.se / Cloudflare 챌린지 리다이렉트 감지
                if "cure.se" in html or "cf-browser-verification" in html or \
                   "Just a moment" in html or len(html) < 500:
                    self.last_error = f"Cloudflare 차단 감지 ({url}), 다음 URL 시도"
                    continue
                items = self.parse(html)
                if items:
                    self.last_error = ""
                    return [self._normalize(it) for it in items[:limit]]
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"{type(exc).__name__}: {str(exc)[:100]}"
                continue
        return []
