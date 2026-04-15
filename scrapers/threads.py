"""Threads 인기 포스트 스크래퍼.

Threads는 공식 공개 API가 없고 직접 스크래핑도 어려움. 본 구현은
`ANTHROPIC_API_KEY`가 있는 경우 웹검색 기반으로 최신 트렌드 키워드를
요청하고, 실패 시 정적 fallback을 반환한다.
"""
from __future__ import annotations

import json
import logging

from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL

from .base import BaseScraper

logger = logging.getLogger(__name__)


class ThreadsScraper(BaseScraper):
    source = "Threads"
    base_url = "https://www.threads.net/"
    category = "연예"

    def parse(self, html: str) -> list[dict]:
        return []

    def get_trending(self, limit: int = 10) -> list[dict]:
        if ANTHROPIC_API_KEY:
            items = self._fetch_via_claude(limit)
            if items:
                return items
        return self._fallback(limit)

    # ------------------------------------------------------------------
    def _fetch_via_claude(self, limit: int) -> list[dict]:
        try:
            import anthropic
        except ImportError:
            return []

        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            prompt = (
                f"지금 한국 Threads(스레드)에서 가장 많이 언급되는 인기 주제/포스트 "
                f"{limit}개를 찾아줘. JSON 배열로만 답하고 각 항목은 "
                '{"title": "...", "summary": "1-2줄 요약", "url": "https://..." (없으면 빈 문자열), "engagement": "대략적 반응"} '
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
            # 코드블럭 감싸진 경우 제거
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
                    "url": row.get("url") or "https://www.threads.net/",
                    "engagement": row.get("engagement", "AI 추정"),
                }))
            return items
        except Exception as exc:  # noqa: BLE001
            logger.info("Threads AI fallback 실패: %s", exc)
            return []

    def _fallback(self, limit: int) -> list[dict]:
        placeholders = [
            "Threads에서 급상승 중인 주제 (API 키 미설정 시 빈 결과)",
        ]
        return [self._normalize({
            "title": t,
            "url": "https://www.threads.net/",
            "summary": "ANTHROPIC_API_KEY 설정 시 AI 기반 트렌드 수집 가능",
        }) for t in placeholders[:limit]]
