"""Anthropic / Google Gemini API 기반 쇼츠 아이디어 분석기.

우선순위: Anthropic API 키가 있으면 Claude 사용, 없으면 Gemini 사용.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from config import ANALYZE_BATCH_SIZE, ANTHROPIC_MODEL, GEMINI_MODEL, get_anthropic_key, get_gemini_key

logger = logging.getLogger(__name__)


ANALYSIS_SYSTEM = """당신은 YouTube 쇼츠 기획 전문가입니다.
주어진 인기 게시글/콘텐츠 목록을 분석해, 각 항목에 대해 쇼츠로 만들 때
어떻게 활용할지 구체적인 아이디어를 제안합니다.
응답은 반드시 요청된 JSON 스키마만 반환하고, 마크다운 코드블럭 금지입니다."""


BATCH_PROMPT_TEMPLATE = """다음은 여러 커뮤니티/플랫폼에서 수집한 인기 콘텐츠 목록입니다.
각 항목을 쇼츠 제작 관점에서 분석해주세요.

입력 JSON:
{items_json}

각 항목에 대해 아래 스키마의 JSON 배열을 **순서대로 동일한 길이로** 반환하세요.
다른 설명은 금지, JSON만:

[
  {{
    "index": 0,
    "summary": "한글 1-2줄 요약",
    "shorts_idea": "쇼츠 제작 아이디어 (각도·편집 스타일 구체적으로)",
    "target_audience": "예상 타겟 시청자층",
    "hashtags": ["#태그1", "#태그2", "#태그3", "#태그4", "#태그5"],
    "score": 1~5 정수
  }},
  ...
]"""


SINGLE_PROMPT_TEMPLATE = """다음 인기 콘텐츠를 쇼츠 제작 관점에서 분석해줘.

제목: {title}
출처: {source}
참여도: {engagement}
URL: {url}
요약: {summary}

아래 JSON만 반환 (마크다운 금지):
{{
  "summary": "한글 1-2줄 요약",
  "shorts_idea": "쇼츠 제작 아이디어 (각도·편집 스타일 구체적으로)",
  "target_audience": "예상 타겟 시청자층",
  "hashtags": ["#태그1", "#태그2", "#태그3", "#태그4", "#태그5"],
  "score": 1~5 정수
}}"""


class AnalyzerError(Exception):
    pass


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        for prefix in ("json\n", "JSON\n", "json ", "JSON "):
            if text.startswith(prefix):
                text = text[len(prefix):]
                break
    return text.strip()


# ---------------------------------------------------------------------------
# 클라이언트 팩토리
# ---------------------------------------------------------------------------

def _get_client() -> tuple[str, Any] | None:
    """AI 클라이언트 반환. (provider, client) 튜플.
    Anthropic 키 우선, 없으면 Gemini. 둘 다 없으면 None.
    """
    # 1) Anthropic
    api_key = get_anthropic_key()
    if api_key:
        try:
            import anthropic
            return ("anthropic", anthropic.Anthropic(api_key=api_key))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Anthropic 클라이언트 초기화 실패: %s", exc)

    # 2) Gemini
    gemini_key = get_gemini_key()
    if gemini_key:
        try:
            import google.generativeai as genai  # type: ignore
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel(
                model_name=GEMINI_MODEL,
                system_instruction=ANALYSIS_SYSTEM,
            )
            return ("gemini", model)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gemini 클라이언트 초기화 실패: %s", exc)

    return None


def _call_api(client_info: tuple[str, Any], prompt: str, max_tokens: int) -> str:
    """provider에 따라 API 호출 → 텍스트 반환."""
    provider, client = client_info
    if provider == "anthropic":
        resp = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=ANALYSIS_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(
            blk.text for blk in resp.content if getattr(blk, "type", "") == "text"
        )
    else:  # gemini
        resp = client.generate_content(
            prompt,
            generation_config={"max_output_tokens": max_tokens},
        )
        return resp.text


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def analyze_batch(items: list[dict]) -> list[dict]:
    """최대 ANALYZE_BATCH_SIZE개 항목을 한 번에 분석.

    반환: 원본 items와 동일한 순서/길이. 분석 실패 시 원본 그대로.
    """
    if not items:
        return []

    client_info = _get_client()
    if client_info is None:
        return items

    results: list[dict] = []
    for i in range(0, len(items), ANALYZE_BATCH_SIZE):
        chunk = items[i:i + ANALYZE_BATCH_SIZE]
        results.extend(_analyze_chunk(client_info, chunk))
    return results


def _analyze_chunk(client_info: tuple[str, Any], chunk: list[dict]) -> list[dict]:
    compact = [
        {
            "index": idx,
            "title": it.get("title", ""),
            "source": it.get("source", ""),
            "engagement": it.get("engagement", ""),
            "summary": it.get("summary", ""),
        }
        for idx, it in enumerate(chunk)
    ]
    prompt = BATCH_PROMPT_TEMPLATE.format(
        items_json=json.dumps(compact, ensure_ascii=False)
    )

    try:
        text = _call_api(client_info, prompt, max_tokens=4096)
        parsed = json.loads(_strip_code_fence(text))
        if not isinstance(parsed, list):
            raise AnalyzerError("배열이 아님")
    except Exception as exc:  # noqa: BLE001
        logger.warning("배치 분석 실패, 원본 유지: %s", exc)
        return chunk

    by_index = {}
    for row in parsed:
        if isinstance(row, dict) and "index" in row:
            by_index[row["index"]] = row

    enriched: list[dict] = []
    for idx, item in enumerate(chunk):
        analysis = by_index.get(idx)
        if analysis:
            item = {**item, "analysis": {
                "summary": analysis.get("summary", ""),
                "shorts_idea": analysis.get("shorts_idea", ""),
                "target_audience": analysis.get("target_audience", ""),
                "hashtags": analysis.get("hashtags", []) or [],
                "score": int(analysis.get("score", 3) or 3),
            }}
        enriched.append(item)
    return enriched


def analyze_single(item: dict) -> dict:
    """항목 하나만 분석. 실패 시 원본 그대로."""
    client_info = _get_client()
    if client_info is None:
        return item

    prompt = SINGLE_PROMPT_TEMPLATE.format(
        title=item.get("title", ""),
        source=item.get("source", ""),
        engagement=item.get("engagement", ""),
        url=item.get("url", ""),
        summary=item.get("summary", ""),
    )
    try:
        text = _call_api(client_info, prompt, max_tokens=1024)
        data = json.loads(_strip_code_fence(text))
        return {**item, "analysis": {
            "summary": data.get("summary", ""),
            "shorts_idea": data.get("shorts_idea", ""),
            "target_audience": data.get("target_audience", ""),
            "hashtags": data.get("hashtags", []) or [],
            "score": int(data.get("score", 3) or 3),
        }}
    except Exception as exc:  # noqa: BLE001
        logger.warning("단일 분석 실패: %s", exc)
        return item


def is_available() -> bool:
    """Anthropic 또는 Gemini 키가 하나라도 설정돼 있으면 True."""
    return bool(get_anthropic_key() or get_gemini_key())


def active_provider() -> str:
    """현재 사용 중인 AI 제공자 이름 반환 (표시용)."""
    if get_anthropic_key():
        return "Claude (Anthropic)"
    if get_gemini_key():
        return "Gemini (Google)"
    return ""
