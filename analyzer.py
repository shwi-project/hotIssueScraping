"""Google Gemini API 기반 쇼츠 아이디어 분석기."""
from __future__ import annotations

import json
import logging
from typing import Any

from config import ANALYZE_BATCH_SIZE, GEMINI_MODEL, get_gemini_key

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


# 마지막 단일 분석 오류 메시지 (app.py 에서 읽어 사용자에게 표시)
last_error: str = ""


def _repair_json(text: str) -> str:
    """잘린 JSON 문자열 복구 시도.

    토큰 한도로 응답이 중간에 끊겼을 때 열린 따옴표·괄호를 닫아준다.
    완벽한 복구는 불가능하지만 JSONDecodeError를 줄여준다.
    """
    import re
    # 트레일링 콤마 제거
    text = re.sub(r',(\s*[}\]])', r'\1', text)
    # 열린 문자열(홀수 개 비이스케이프 따옴표) → 닫기
    depth_curly = 0
    depth_square = 0
    in_string = False
    escape_next = False
    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch == "{":
                depth_curly += 1
            elif ch == "}":
                depth_curly -= 1
            elif ch == "[":
                depth_square += 1
            elif ch == "]":
                depth_square -= 1
    # 열린 문자열 닫기
    if in_string:
        text += '"'
    # 열린 괄호 닫기
    text += "}" * max(depth_curly, 0)
    text += "]" * max(depth_square, 0)
    return text


def _extract_json(text: str) -> str:
    """AI 응답에서 JSON 부분만 추출. 코드 펜스·앞뒤 텍스트 제거."""
    import re
    text = text.strip()
    # 코드 펜스 제거
    fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if fence:
        return fence.group(1).strip()
    # 코드 펜스 없이 JSON만 있는 경우: 첫 [ 또는 { 부터 끝까지 추출
    m = re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", text)
    if m:
        return m.group(1).strip()
    return text


# ---------------------------------------------------------------------------
# 클라이언트 팩토리
# ---------------------------------------------------------------------------

def _get_client() -> tuple[str, Any] | None:
    """Gemini REST API 키 반환. 없으면 None."""
    gemini_key = get_gemini_key()
    if gemini_key:
        return ("gemini", gemini_key)
    return None


def _call_api(client_info: tuple[str, Any], prompt: str, max_tokens: int) -> str:
    """Gemini REST API 호출 → 텍스트 반환."""
    _provider, client = client_info  # provider는 항상 "gemini"
    import requests as _rq
    import time as _time
    api_key = client  # _get_client에서 키 문자열을 그대로 전달
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    # 시스템 프롬프트를 user 메시지 앞에 삽입 (system_instruction 호환성 문제 우회)
    full_prompt = f"{ANALYSIS_SYSTEM}\n\n{prompt}"
    body = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens},
    }
    last_err = ""
    for attempt in range(3):
        resp = _rq.post(url, headers=headers, json=body, timeout=120)
        if resp.status_code == 429:
            last_err = resp.text[:200]
            _time.sleep((attempt + 1) * 10)
            continue
        if not resp.ok:
            try:
                err = resp.json().get("error", {})
                msg = err.get("message", resp.text[:300])
            except Exception:
                msg = resp.text[:300]
            raise AnalyzerError(f"Gemini API {resp.status_code}: {msg}")
        data = resp.json()
        try:
            # thinking 모드 대응: 모든 parts의 text를 합침
            parts = data["candidates"][0]["content"].get("parts", [])
            text = "\n".join(p.get("text", "") for p in parts if p.get("text"))
            if not text:
                raise AnalyzerError(f"Gemini 응답 비어있음: {data}")
            return text
        except (KeyError, IndexError) as exc:
            raise AnalyzerError(f"Gemini 응답 파싱 실패: {data}") from exc
    raise AnalyzerError(f"Gemini 429 한도 초과: {last_err}")


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
        extracted = _extract_json(text)
        try:
            parsed = json.loads(extracted)
        except json.JSONDecodeError:
            parsed = json.loads(_repair_json(extracted))
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
    """항목 하나만 분석. 실패 시 원본 그대로.

    실패 이유는 모듈 수준 `last_error` 에 기록 (app.py 에서 표시용).
    """
    global last_error
    last_error = ""

    client_info = _get_client()
    if client_info is None:
        last_error = "API 키 없음 — 설정 탭에서 GEMINI_API_KEY를 등록하세요."
        logger.warning("analyze_single: %s", last_error)
        return item

    prompt = SINGLE_PROMPT_TEMPLATE.format(
        title=item.get("title", ""),
        source=item.get("source", ""),
        engagement=item.get("engagement", ""),
        url=item.get("url", ""),
        summary=item.get("summary", ""),
    )
    try:
        text = _call_api(client_info, prompt, max_tokens=2048)
        extracted = _extract_json(text)
        try:
            data = json.loads(extracted)
        except json.JSONDecodeError:
            data = json.loads(_repair_json(extracted))
        return {**item, "analysis": {
            "summary": data.get("summary", ""),
            "shorts_idea": data.get("shorts_idea", ""),
            "target_audience": data.get("target_audience", ""),
            "hashtags": data.get("hashtags", []) or [],
            "score": int(data.get("score", 3) or 3),
        }}
    except Exception as exc:  # noqa: BLE001
        last_error = f"{type(exc).__name__}: {str(exc)[:200]}"
        logger.warning("단일 분석 실패: %s", last_error)
        return item


def is_available() -> bool:
    """Gemini 키가 설정돼 있으면 True."""
    return bool(get_gemini_key())


def active_provider() -> str:
    """현재 사용 중인 AI 제공자 이름 반환 (표시용)."""
    if get_gemini_key():
        return "Gemini (Google)"
    return ""
