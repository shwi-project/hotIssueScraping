"""스크래퍼 공통 기반 클래스."""
from __future__ import annotations

import logging
import random
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup

from config import REQUEST_DELAY, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

# 대표적인 User-Agent 풀 — fake_useragent 오프라인 실패 대비용으로 하드코딩 동봉
USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; SM-G991N) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]


def random_user_agent() -> str:
    """User-Agent 하나를 랜덤 반환."""
    return random.choice(USER_AGENTS)


class BaseScraper(ABC):
    """모든 스크래퍼의 공통 추상 클래스.

    서브클래스는 `source`, `base_url`, `category` 클래스 변수와
    `parse(html_or_text)` 메서드를 구현하면 된다.
    RSS/JSON 기반 스크래퍼는 `get_trending()`을 직접 오버라이드해도 무방.
    """

    #: 플랫폼 표시 이름 (예: "디시인사이드")
    source: str = ""
    #: 기본 수집 URL
    base_url: str = ""
    #: 기본 카테고리 (각 아이템에서 override 가능)
    category: str = "기타"
    #: 응답 인코딩 명시가 필요한 경우 (예: 뽐뿌 = "euc-kr")
    encoding: str | None = None

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(self._default_headers())
        #: 마지막 수집에서 발생한 에러 메시지 (비어있으면 성공/미실행)
        self.last_error: str = ""

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------
    def _default_headers(self) -> dict[str, str]:
        return {
            "User-Agent": random_user_agent(),
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

    def fetch(self, url: str | None = None, *, params: dict | None = None,
              headers: dict | None = None) -> str:
        """HTTP GET. 실패 시 예외를 상위로 올린다."""
        target = url or self.base_url
        merged_headers = dict(self.session.headers)
        merged_headers["User-Agent"] = random_user_agent()
        if headers:
            merged_headers.update(headers)

        response = self.session.get(
            target,
            params=params,
            headers=merged_headers,
            timeout=REQUEST_TIMEOUT,
        )
        if self.encoding:
            response.encoding = self.encoding
        else:
            response.encoding = response.apparent_encoding or "utf-8"
        response.raise_for_status()
        time.sleep(REQUEST_DELAY)
        return response.text

    def fetch_json(self, url: str | None = None, *, params: dict | None = None,
                   headers: dict | None = None) -> Any:
        """HTTP GET → JSON."""
        target = url or self.base_url
        merged_headers = dict(self.session.headers)
        merged_headers["User-Agent"] = random_user_agent()
        merged_headers["Accept"] = "application/json"
        if headers:
            merged_headers.update(headers)

        response = self.session.get(
            target,
            params=params,
            headers=merged_headers,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        time.sleep(REQUEST_DELAY)
        return response.json()

    @staticmethod
    def soup(html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    # ------------------------------------------------------------------
    # 파이프라인
    # ------------------------------------------------------------------
    @abstractmethod
    def parse(self, html: str) -> list[dict]:
        """HTML/JSON 문자열을 받아 아이템 리스트(dict)를 반환."""

    def get_trending(self, limit: int = 10) -> list[dict]:
        """스크래퍼 엔트리 포인트. 예외 발생 시 빈 리스트 반환."""
        self.last_error = ""
        try:
            html = self.fetch()
            items = self.parse(html)
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else "?"
            self.last_error = f"HTTP {code} ({exc.request.url if exc.request else self.base_url})"
            logger.warning("[%s] %s", self.source, self.last_error)
            return []
        except requests.ConnectionError:
            self.last_error = "연결 실패 (차단/네트워크/DNS)"
            logger.warning("[%s] %s", self.source, self.last_error)
            return []
        except requests.Timeout:
            self.last_error = f"타임아웃 ({REQUEST_TIMEOUT}s 초과)"
            logger.warning("[%s] %s", self.source, self.last_error)
            return []
        except Exception as exc:  # noqa: BLE001 — 의도적 광역 캐치
            self.last_error = f"{type(exc).__name__}: {str(exc)[:120]}"
            logger.warning("[%s] 수집 실패: %s", self.source, exc)
            return []

        if not items:
            self.last_error = "파싱 결과 0건 (레이아웃 변경 가능성)"

        out: list[dict] = []
        for it in items[:limit]:
            out.append(self._normalize(it))
        return out

    # ------------------------------------------------------------------
    # 반환 포맷 정규화
    # ------------------------------------------------------------------
    def _normalize(self, item: dict) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "title": (item.get("title") or "").strip(),
            "summary": (item.get("summary") or "").strip(),
            "url": item.get("url", ""),
            "source": item.get("source", self.source),
            "category": item.get("category", self.category),
            "engagement": item.get("engagement", ""),
            "thumbnail": item.get("thumbnail", ""),
            "collected_at": item.get("collected_at", now),
            # 정렬/분석에 쓰이는 숫자 필드 (있으면 채워짐)
            "score": int(item.get("score") or 0),
            "views": int(item.get("views") or 0),
            "comments": int(item.get("comments") or 0),
        }

    # ------------------------------------------------------------------
    # 편의 유틸
    # ------------------------------------------------------------------
    @staticmethod
    def to_int(text: str | None) -> int:
        """'1.2K', '3,456', '조회 789' 같은 문자열을 정수로 변환."""
        if text is None:
            return 0
        s = str(text).strip().lower().replace(",", "")
        # 숫자 앞 한글/기호 제거
        import re
        m = re.search(r"([\d.]+)\s*([km万])?", s)
        if not m:
            return 0
        num = float(m.group(1))
        suf = m.group(2)
        if suf == "k":
            num *= 1_000
        elif suf == "m":
            num *= 1_000_000
        elif suf == "万":
            num *= 10_000
        return int(num)

    @staticmethod
    def format_engagement(*, score: int | None = None, views: int | None = None,
                          comments: int | None = None) -> str:
        parts = []
        if score:
            parts.append(f"추천 {score:,}")
        if views:
            parts.append(f"조회 {views:,}")
        if comments:
            parts.append(f"댓글 {comments:,}")
        return " / ".join(parts)
