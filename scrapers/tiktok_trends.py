"""TikTok 한국 트렌드 스크래퍼.

우선순위:
1) SCRAPECREATORS_API_KEY → 실제 TikTok 영상 수집 (권장)
2) Gemini → AI 추정 트렌드 (fallback)
"""
from __future__ import annotations

import json
import logging
import re

from config import GEMINI_MODEL, get_gemini_key, get_scrapecreators_key

from .base import BaseScraper

logger = logging.getLogger(__name__)

KR_KEYWORDS = ["한국", "한국이슈", "핫이슈", "한국트렌드"]


class TiktokTrendsScraper(BaseScraper):
    source = "TikTok"
    base_url = "https://www.tiktok.com/discover"
    category = "연예"

    SCRAPECREATORS_URL = "https://api.scrapecreators.com/v1/tiktok/search"

    def parse(self, html: str) -> list[dict]:
        return []

    def get_trending(self, limit: int = 10) -> list[dict]:
        self.last_error = ""

        # 1) ScrapeCreators — 실제 TikTok 영상
        sc_key = get_scrapecreators_key()
        if sc_key:
            items = self._fetch_via_scrapecreators(sc_key, limit)
            if items:
                return items

        # 2) Gemini — AI 추정
        if get_gemini_key():
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
                    videos = data.get("data", data.get("videos", data.get("items", [])))
                    if not isinstance(videos, list):
                        continue
                    for video in videos:
                        if len(items) >= limit:
                            break
                        # 영상 설명 텍스트
                        desc = (
                            video.get("desc")
                            or video.get("description")
                            or video.get("text")
                            or video.get("title")
                            or ""
                        )
                        if not desc or len(desc) < 3:
                            continue
                        # 작성자
                        author = (
                            (video.get("author") or {}).get("uniqueId")
                            or (video.get("author") or {}).get("nickname")
                            or video.get("authorMeta", {}).get("id")
                            or ""
                        )
                        # URL
                        video_id = video.get("id") or video.get("video_id") or ""
                        if video.get("webVideoUrl") or video.get("url"):
                            url = video.get("webVideoUrl") or video.get("url")
                        elif author and video_id:
                            url = f"https://www.tiktok.com/@{author}/video/{video_id}"
                        elif author:
                            url = f"https://www.tiktok.com/@{author}"
                        else:
                            url = "https://www.tiktok.com/discover"
                        if url in seen:
                            continue
                        seen.add(url)
                        # 통계
                        stats = video.get("stats") or video.get("statsV2") or {}
                        likes = int(stats.get("diggCount", stats.get("likeCount", 0)) or 0)
                        views = int(stats.get("playCount", stats.get("viewCount", 0)) or 0)
                        comments = int(stats.get("commentCount", 0) or 0)
                        title = desc[:80] + ("…" if len(desc) > 80 else "")
                        items.append(self._normalize({
                            "title": title,
                            "summary": desc[:200],
                            "url": url,
                            "score": likes,
                            "views": views,
                            "comments": comments,
                            "engagement": self.format_engagement(score=likes, views=views, comments=comments),
                        }))
                except Exception as exc:  # noqa: BLE001
                    logger.info("ScrapeCreators TikTok '%s' 실패: %s", kw, exc)
                    continue

            if items:
                self.last_error = ""
            return items
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"ScrapeCreators 실패: {type(exc).__name__}: {str(exc)[:100]}"
            logger.warning("TikTok ScrapeCreators 실패: %s", exc)
            return []

    # ------------------------------------------------------------------
    @staticmethod
    def _extract_json(text: str) -> str:
        text = text.strip()
        fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
        if fence:
            return fence.group(1).strip()
        m = re.search(r"(\[[\s\S]*\])", text)
        return m.group(1).strip() if m else text

    @staticmethod
    def _repair_json(text: str) -> str:
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
        if in_str:
            text += '"'
        text += "}" * max(depth_c, 0)
        text += "]" * max(depth_s, 0)
        return text

    def _fetch_via_gemini(self, limit: int) -> list[dict]:
        try:
            import requests as _rq
            import time as _time
            prompt = (
                f"지금 한국 TikTok에서 유행하는 해시태그/챌린지/밈 {limit}개를 찾아줘. "
                "JSON 배열로만 답하고 각 항목은 "
                '{"title": "해시태그 또는 트렌드명", "summary": "무엇인지 1-2줄", '
                '"url": "https://www.tiktok.com/tag/..." (없으면 빈 문자열), '
                '"engagement": "대략적 인기"} '
                "필드를 포함해. 다른 설명 없이 JSON만."
            )
            body = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 2048},
            }
            resp = None
            for attempt in range(3):
                resp = _rq.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
                    headers={"Content-Type": "application/json", "x-goog-api-key": get_gemini_key()},
                    json=body,
                    timeout=60,
                )
                if resp.status_code in (429, 503, 529):
                    _time.sleep((attempt + 1) * 5)
                    continue
                break
            if not resp.ok:
                self.last_error = f"Gemini API {resp.status_code}: {resp.text[:100]}"
                return []
            # thinking 모드 대응: 모든 parts의 text를 합침
            parts = resp.json()["candidates"][0]["content"].get("parts", [])
            text = "\n".join(p.get("text", "") for p in parts if p.get("text") and not p.get("thought"))
            extracted = self._extract_json(text)
            try:
                data = json.loads(extracted)
            except json.JSONDecodeError:
                data = json.loads(self._repair_json(extracted))
            items: list[dict] = []
            for row in data[:limit]:
                items.append(self._normalize({
                    "title": row.get("title", ""),
                    "summary": row.get("summary", ""),
                    "url": row.get("url") or "https://www.tiktok.com/discover",
                    "engagement": row.get("engagement", "AI 추정"),
                }))
            return items
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"Gemini 호출 실패: {type(exc).__name__}: {str(exc)[:100]}"
            logger.info("TikTok Gemini fallback 실패: %s", exc)
            return []
