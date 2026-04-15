"""Reddit r/popular (+ 한국 관련 서브) 스크래퍼.

REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET가 설정돼 있으면 OAuth로 접근
(레이트 리밋이 훨씬 높고, Streamlit Cloud 공유 IP 차단 회피).
없으면 공개 .json 엔드포인트로 fallback.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from config import get_reddit_creds

from .base import BaseScraper

logger = logging.getLogger(__name__)


class RedditScraper(BaseScraper):
    source = "Reddit"
    base_url = "https://www.reddit.com/r/popular.json"
    category = "이슈/뉴스"

    KOREA_SUBS_UNAUTH = [
        "https://www.reddit.com/r/popular.json",
        "https://www.reddit.com/r/korea/hot.json",
        "https://www.reddit.com/r/hanguk/hot.json",
    ]
    KOREA_SUBS_OAUTH = [
        "https://oauth.reddit.com/r/popular",
        "https://oauth.reddit.com/r/korea/hot",
        "https://oauth.reddit.com/r/hanguk/hot",
    ]

    _token: str = ""
    _token_expires_at: float = 0

    USER_AGENT = "shorts-trend-collector/0.1 by anonymous"

    def parse(self, html_or_json: str) -> list[dict]:
        return []

    # ------------------------------------------------------------------
    def _get_oauth_token(self) -> str | None:
        """OAuth client_credentials 토큰 발급 및 캐시."""
        creds = get_reddit_creds()
        if not creds:
            return None
        if self._token and self._token_expires_at > time.time() + 60:
            return self._token
        cid, sec = creds
        try:
            resp = requests.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=(cid, sec),
                data={"grant_type": "client_credentials"},
                headers={"User-Agent": self.USER_AGENT},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data.get("access_token", "")
            expires_in = int(data.get("expires_in", 3600))
            self._token_expires_at = time.time() + expires_in
            return self._token or None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Reddit OAuth 토큰 실패: %s", exc)
            return None

    # ------------------------------------------------------------------
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

    def _fetch_oauth(self, url: str, token: str, limit: int) -> Any:
        resp = requests.get(
            url,
            params={"limit": limit * 2},
            headers={
                "Authorization": f"bearer {token}",
                "User-Agent": self.USER_AGENT,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    def get_trending(self, limit: int = 10) -> list[dict]:
        self.last_error = ""
        all_items: list[dict] = []
        last_exc = ""

        # 1) OAuth 경로 (creds 있으면)
        token = self._get_oauth_token()
        if token:
            per = max(1, limit // len(self.KOREA_SUBS_OAUTH))
            for url in self.KOREA_SUBS_OAUTH:
                try:
                    data = self._fetch_oauth(url, token, per)
                    for it in self._parse_json(data)[:per]:
                        all_items.append(self._normalize(it))
                except Exception as exc:  # noqa: BLE001
                    last_exc = f"OAuth {url.rsplit('/', 2)[-2]}: {type(exc).__name__}"
                    continue
                if len(all_items) >= limit:
                    break
            if all_items:
                return all_items[:limit]

        # 2) 비인증 JSON 경로
        per = max(1, limit // len(self.KOREA_SUBS_UNAUTH))
        for url in self.KOREA_SUBS_UNAUTH:
            try:
                data = self.fetch_json(url, params={"limit": per * 2})
                for it in self._parse_json(data)[:per]:
                    all_items.append(self._normalize(it))
            except Exception as exc:  # noqa: BLE001
                last_exc = f"{type(exc).__name__}: {str(exc)[:80]}"
                continue
            if len(all_items) >= limit:
                break

        if not all_items:
            self.last_error = last_exc or (
                "Reddit 차단 가능성. REDDIT_CLIENT_ID/SECRET 설정 권장"
            )
        return all_items[:limit]
