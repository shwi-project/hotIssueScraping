"""TikTok 한국 트렌드 (AI 기반 대체 수집)."""
from __future__ import annotations

import json
import logging

from config import GEMINI_MODEL, get_gemini_key

from .base import BaseScraper

logger = logging.getLogger(__name__)


class TiktokTrendsScraper(BaseScraper):
    source = "TikTok"
    base_url = "https://www.tiktok.com/discover"
    category = "연예"

    def parse(self, html: str) -> list[dict]:
        return []

    def get_trending(self, limit: int = 10) -> list[dict]:
        self.last_error = ""
        if not get_gemini_key():
            self.last_error = "GEMINI_API_KEY 없음 (TikTok은 AI 기반 수집만 지원)"
            return []
        items = self._fetch_via_gemini(limit)
        if not items and not self.last_error:
            self.last_error = "Gemini 응답 파싱 실패"
        return items

    def _fetch_via_gemini(self, limit: int) -> list[dict]:
        try:
            import requests as _rq
            prompt = (
                f"지금 한국 TikTok에서 유행하는 해시태그/챌린지/밈 {limit}개를 찾아줘. "
                "JSON 배열로만 답하고 각 항목은 "
                '{"title": "해시태그 또는 트렌드명", "summary": "무엇인지 1-2줄", '
                '"url": "https://www.tiktok.com/tag/..." (없으면 빈 문자열), '
                '"engagement": "대략적 인기"} '
                "필드를 포함해. 다른 설명 없이 JSON만."
            )
            resp = _rq.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
                headers={"Content-Type": "application/json", "x-goog-api-key": get_gemini_key()},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": 2048},
                },
                timeout=60,
            )
            if not resp.ok:
                self.last_error = f"Gemini API {resp.status_code}"
                return []
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            import re
            fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
            if fence:
                text = fence.group(1).strip()
            else:
                m = re.search(r"(\[[\s\S]*\])", text)
                if m:
                    text = m.group(1).strip()
            data = json.loads(text)
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
            logger.info("TikTok AI fallback 실패: %s", exc)
            return []
