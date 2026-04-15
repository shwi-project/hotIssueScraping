"""TikTok 한국 트렌드 (AI 기반 대체 수집)."""
from __future__ import annotations

import json
import logging

from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL

from .base import BaseScraper

logger = logging.getLogger(__name__)


class TiktokTrendsScraper(BaseScraper):
    source = "TikTok"
    base_url = "https://www.tiktok.com/discover"
    category = "연예"

    def parse(self, html: str) -> list[dict]:
        return []

    def get_trending(self, limit: int = 10) -> list[dict]:
        if ANTHROPIC_API_KEY:
            items = self._fetch_via_claude(limit)
            if items:
                return items
        return self._fallback(limit)

    def _fetch_via_claude(self, limit: int) -> list[dict]:
        try:
            import anthropic
        except ImportError:
            return []

        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            prompt = (
                f"지금 한국 TikTok에서 유행하는 해시태그/챌린지/밈 {limit}개를 찾아줘. "
                "JSON 배열로만 답하고 각 항목은 "
                '{"title": "해시태그 또는 트렌드명", "summary": "무엇인지 1-2줄", '
                '"url": "https://www.tiktok.com/tag/..." (없으면 빈 문자열), '
                '"engagement": "대략적 인기"} '
                "필드를 포함해. 다른 설명 없이 JSON만."
            )
            resp = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(
                blk.text for blk in resp.content if getattr(blk, "type", "") == "text"
            ).strip()
            if text.startswith("```"):
                text = text.strip("`")
                if text.lower().startswith("json"):
                    text = text[4:]
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
            logger.info("TikTok AI fallback 실패: %s", exc)
            return []

    def _fallback(self, limit: int) -> list[dict]:
        return [self._normalize({
            "title": "TikTok 한국 트렌드 (API 키 필요)",
            "url": "https://www.tiktok.com/discover",
            "summary": "ANTHROPIC_API_KEY 설정 시 AI 기반 트렌드 수집 가능",
        })][:limit]
