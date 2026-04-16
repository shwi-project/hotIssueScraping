"""Threads 인기 포스트 스크래퍼.

우선순위:
1) SCRAPECREATORS_API_KEY → 실제 Threads 포스트 수집 (권장)
2) Gemini → AI 추정 트렌드 (fallback)
"""
from __future__ import annotations

import json
import logging

from config import get_scrapecreators_key

from .base import BaseScraper

logger = logging.getLogger(__name__)

# 한국 관련 검색 키워드 (ScrapeCreators 검색용)
KR_KEYWORDS = ["한국", "이슈", "핫이슈", "트렌드"]


class ThreadsScraper(BaseScraper):
    source = "Threads"
    base_url = "https://www.threads.net/"
    category = "연예"

    SCRAPECREATORS_URL = "https://api.scrapecreators.com/v1/threads/search"

    def parse(self, html: str) -> list[dict]:
        return []

    def get_trending(self, limit: int = 10) -> list[dict]:
        self.last_error = ""

        # 1) ScrapeCreators — 실제 Threads 포스트
        sc_key = get_scrapecreators_key()
        if sc_key:
            items = self._fetch_via_scrapecreators(sc_key, limit)
            if items:
                return items

        # 2) Gemini
        items = self._fetch_via_gemini(limit)
        if items:
            return items

        if not self.last_error:
            self.last_error = "SCRAPECREATORS_API_KEY 또는 GEMINI_API_KEY 필요"
        return []

    # ------------------------------------------------------------------
    def _fetch_via_scrapecreators(self, api_key: str, limit: int) -> list[dict]:
        try:
            import requests as _rq
            seen: set[str] = set()
            items: list[dict] = []

            for kw in KR_KEYWORDS:
                if len(items) >= limit:
                    break
                try:
                    resp = _rq.get(
                        self.SCRAPECREATORS_URL,
                        params={"query": kw},
                        headers={"x-api-key": api_key},
                        timeout=20,
                    )
                    if not resp.ok:
                        self.last_error = f"ScrapeCreators API {resp.status_code}: {resp.text[:100]}"
                        continue
                    data = resp.json()
                    posts = data.get("data", data.get("posts", []))
                    for post in posts:
                        if len(items) >= limit:
                            break
                        # 포스트 텍스트
                        caption = post.get("caption") or {}
                        if isinstance(caption, dict):
                            text = caption.get("text", "")
                        else:
                            text = str(caption)
                        if not text:
                            text = post.get("text", "")
                        if not text or len(text) < 5:
                            continue
                        # URL 구성 — permalink > code > 유저 프로필 순 우선순위
                        # (pk/id는 숫자 내부 ID라 Threads URL에 사용 불가)
                        username = (post.get("user") or {}).get("username", "")
                        permalink = post.get("permalink") or post.get("link") or ""
                        code = post.get("code") or post.get("shortcode") or ""
                        if permalink and permalink.startswith("http"):
                            url = permalink
                        elif code and username:
                            url = f"https://www.threads.net/@{username}/post/{code}"
                        elif username:
                            url = f"https://www.threads.net/@{username}"
                        else:
                            url = "https://www.threads.net/"
                        if url in seen:
                            continue
                        seen.add(url)
                        likes = int(post.get("like_count", 0) or 0)
                        comments = int(post.get("reply_count", post.get("text_post_app_info", {}).get("direct_reply_count", 0)) or 0)
                        title = text[:80] + ("…" if len(text) > 80 else "")
                        items.append(self._normalize({
                            "title": title,
                            "summary": text[:200],
                            "url": url,
                            "score": likes,
                            "views": 0,
                            "comments": comments,
                            "engagement": self.format_engagement(score=likes, views=0, comments=comments),
                        }))
                except Exception as exc:  # noqa: BLE001
                    logger.info("ScrapeCreators '%s' 실패: %s", kw, exc)
                    continue

            if items:
                self.last_error = ""
            return items
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"ScrapeCreators 실패: {type(exc).__name__}: {str(exc)[:100]}"
            logger.warning("Threads ScrapeCreators 실패: %s", exc)
            return []

    # ------------------------------------------------------------------
    def _prompt(self, limit: int) -> str:
        return (
            f"지금 한국 Threads(스레드)에서 가장 많이 언급되는 인기 주제/포스트 "
            f"{limit}개를 찾아줘. JSON 배열로만 답하고 각 항목은 "
            '{"title": "...", "summary": "1-2줄 요약", '
            '"url": "https://..." (없으면 빈 문자열), "engagement": "대략적 반응"} '
            "필드를 포함해. 다른 설명 없이 JSON만."
        )

    @staticmethod
    def _extract_json(text: str) -> str:
        import re
        text = text.strip()
        fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
        if fence:
            return fence.group(1).strip()
        m = re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", text)
        return m.group(1).strip() if m else text

    @staticmethod
    def _repair_json(text: str) -> str:
        import re
        text = re.sub(r',(\s*[}\]])', r'\1', text)
        depth_c = depth_s = 0
        in_str = esc = False
        for ch in text:
            if esc:
                esc = False; continue
            if ch == "\\" and in_str:
                esc = True; continue
            if ch == '"':
                in_str = not in_str; continue
            if not in_str:
                if ch == "{": depth_c += 1
                elif ch == "}": depth_c -= 1
                elif ch == "[": depth_s += 1
                elif ch == "]": depth_s -= 1
        if in_str: text += '"'
        text += "}" * max(depth_c, 0)
        text += "]" * max(depth_s, 0)
        return text

    def _parse_response(self, text: str, limit: int) -> list[dict]:
        logger.info("Threads Gemini raw: %s", text[:200])
        parsed = None
        # json_mode=True 응답은 바로 파싱 가능; 혹시 실패하면 extract/repair 시도
        extracted = self._extract_json(text)
        for candidate in (text, extracted, self._repair_json(extracted)):
            try:
                parsed = json.loads(candidate)
                break
            except (json.JSONDecodeError, ValueError):
                continue
        if not isinstance(parsed, list):
            logger.warning("Threads Gemini JSON 파싱 실패, raw: %s", text[:300])
            self.last_error = "Gemini 응답 파싱 실패 (JSON 아님)"
            return []
        items: list[dict] = []
        for row in parsed[:limit]:
            if not isinstance(row, dict):
                continue
            items.append(self._normalize({
                "title": row.get("title", ""),
                "summary": row.get("summary", ""),
                "url": row.get("url") or "https://www.threads.net/",
                "engagement": row.get("engagement", "AI 추정"),
            }))
        return items

    def _fetch_via_gemini(self, limit: int) -> list[dict]:
        raw_text = self.gemini_call(self._prompt(limit), json_mode=True)
        if not raw_text:
            return []
        return self._parse_response(raw_text, limit)
