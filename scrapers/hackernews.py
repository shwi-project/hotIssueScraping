"""Hacker News top stories 스크래퍼 (Firebase API)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from .base import BaseScraper


class HackerNewsScraper(BaseScraper):
    source = "Hacker News"
    base_url = "https://hacker-news.firebaseio.com/v0/topstories.json"
    category = "IT/테크"

    ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{}.json"

    def parse(self, html: str) -> list[dict]:
        return []  # 사용하지 않음

    def get_trending(self, limit: int = 10) -> list[dict]:
        try:
            ids = self.fetch_json(self.base_url) or []
        except Exception:  # noqa: BLE001
            return []

        ids = ids[: max(limit * 2, 20)]
        items: list[dict] = []

        # 병렬로 개별 스토리 조회
        def _load(story_id: int) -> dict | None:
            try:
                data = self.fetch_json(self.ITEM_URL.format(story_id))
                if not data or data.get("type") != "story":
                    return None
                title = data.get("title", "")
                if not title:
                    return None
                url = data.get("url") or f"https://news.ycombinator.com/item?id={story_id}"
                return {
                    "title": title,
                    "url": url,
                    "score": int(data.get("score", 0) or 0),
                    "comments": int(data.get("descendants", 0) or 0),
                    "engagement": self.format_engagement(
                        score=int(data.get("score", 0) or 0),
                        comments=int(data.get("descendants", 0) or 0),
                    ),
                }
            except Exception:  # noqa: BLE001
                return None

        with ThreadPoolExecutor(max_workers=8) as ex:
            for fut in as_completed([ex.submit(_load, sid) for sid in ids]):
                r = fut.result()
                if r:
                    items.append(self._normalize(r))
                if len(items) >= limit:
                    break

        items.sort(key=lambda x: x["score"], reverse=True)
        return items[:limit]
