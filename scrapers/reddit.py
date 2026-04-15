"""Reddit r/popular (+ 한국 관련 서브) 스크래퍼."""
from __future__ import annotations

from urllib.parse import urljoin

from .base import BaseScraper


class RedditScraper(BaseScraper):
    source = "Reddit"
    base_url = "https://www.reddit.com/r/popular.json"
    category = "이슈/뉴스"

    # 한국 관련 서브레딧 병합
    KOREA_SUBS = [
        "https://www.reddit.com/r/korea/hot.json",
        "https://www.reddit.com/r/hanguk/hot.json",
    ]

    def parse(self, html_or_json: str) -> list[dict]:
        # Reddit은 fetch_json 사용하므로 보통 이 경로 안 탐
        return []

    def _parse_json(self, data: dict) -> list[dict]:
        items: list[dict] = []
        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            title = post.get("title", "")
            if not title:
                continue
            subreddit = post.get("subreddit", "")
            permalink = post.get("permalink", "")
            url = f"https://www.reddit.com{permalink}" if permalink else post.get("url", "")
            score = int(post.get("score", 0) or 0)
            comments = int(post.get("num_comments", 0) or 0)
            thumb = post.get("thumbnail", "")
            if thumb and not thumb.startswith("http"):
                thumb = ""

            items.append({
                "title": title,
                "summary": f"r/{subreddit}",
                "url": url,
                "thumbnail": thumb,
                "score": score,
                "views": 0,
                "comments": comments,
                "engagement": self.format_engagement(score=score, comments=comments),
            })
        return items

    def get_trending(self, limit: int = 10) -> list[dict]:
        all_items: list[dict] = []
        urls = [self.base_url] + self.KOREA_SUBS
        per = max(1, limit // len(urls))

        for url in urls:
            try:
                data = self.fetch_json(url, params={"limit": per * 2})
                parsed = self._parse_json(data)
                for it in parsed[:per]:
                    all_items.append(self._normalize(it))
            except Exception:  # noqa: BLE001
                continue
            if len(all_items) >= limit:
                break
        return all_items[:limit]
