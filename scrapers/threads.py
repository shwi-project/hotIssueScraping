"""Threads 인기 포스트 스크래퍼.

Threads는 공식 공개 API가 없고 직접 스크래핑도 어려움. 본 구현은
Anthropic 또는 Gemini AI를 이용해 최신 트렌드 키워드를 추정한다.
"""
from __future__ import annotations

import json
import logging

from config import ANTHROPIC_MODEL, GEMINI_MODEL, get_anthropic_key, get_gemini_key

from .base import BaseScraper

logger = logging.getLogger(__name__)


class ThreadsScraper(BaseScraper):
    source = "Threads"
    base_url = "https://www.threads.net/"
    category = "연예"

    def parse(self, html: str) -> list[dict]:
        return []

    def get_trending(self, limit: int = 10) -> list[dict]:
        self.last_error = ""

        # 1) Anthropic 우선
        if get_anthropic_key():
            items = self._fetch_via_anthropic(limit)
            if items:
                return items

        # 2) Gemini fallback
        if get_gemini_key():
            items = self._fetch_via_gemini(limit)
            if items:
                return items

        if not self.last_error:
            self.last_error = "ANTHROPIC_API_KEY 또는 GEMINI_API_KEY 필요"
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

    def _parse_response(self, text: str, limit: int) -> list[dict]:
        text = text.strip()
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

    def _fetch_via_anthropic(self, limit: int) -> list[dict]:
        try:
            import anthropic
        except ImportError:
            self.last_error = "anthropic 패키지 미설치"
            return []
        try:
            client = anthropic.Anthropic(api_key=get_anthropic_key())
            resp = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=2048,
                messages=[{"role": "user", "content": self._prompt(limit)}],
            )
            text = "".join(
                blk.text for blk in resp.content if getattr(blk, "type", "") == "text"
            )
            return self._parse_response(text, limit)
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"Anthropic 호출 실패: {type(exc).__name__}: {str(exc)[:100]}"
            logger.info("Threads Anthropic 실패: %s", exc)
            return []

    def _fetch_via_gemini(self, limit: int) -> list[dict]:
        try:
            import requests as _rq
            api_key = get_gemini_key()
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{GEMINI_MODEL}:generateContent"
            )
            resp = _rq.post(
                url,
                headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
                json={
                    "contents": [{"parts": [{"text": self._prompt(limit)}]}],
                    "generationConfig": {"maxOutputTokens": 2048},
                },
                timeout=60,
            )
            if not resp.ok:
                self.last_error = f"Gemini API {resp.status_code}"
                return []
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            return self._parse_response(text, limit)
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"Gemini 호출 실패: {type(exc).__name__}: {str(exc)[:100]}"
            logger.info("Threads Gemini 실패: %s", exc)
            return []
