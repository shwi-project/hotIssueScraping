"""전역 설정값 및 환경변수 로더."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# 프로젝트 루트
BASE_DIR = Path(__file__).resolve().parent

# .env 로드 (있으면)
load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# API 키
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")


def _get_key(*names: str) -> str | None:
    """여러 이름 중 하나라도 찾으면 반환. os.environ → st.secrets 우선순위.

    Streamlit 환경이 아니거나 secrets.toml이 없어도 안전하게 None 반환.
    """
    # 1) os.environ
    for name in names:
        v = os.getenv(name)
        if v:
            return v

    # 2) Streamlit secrets — 전체를 광역 try/except로 감싸서 어떠한 오류도 회피
    # 찾은 값은 os.environ에도 캐싱: ThreadPoolExecutor 스레드에서 st.secrets 접근이
    # 불안정할 때 다음 호출부터 os.getenv()로 바로 반환되도록 보장
    try:
        import streamlit as st  # type: ignore
        # st.secrets 접근 자체가 secrets.toml 없을 때 예외 던질 수 있음
        secrets = st.secrets
        for name in names:
            try:
                # KeyError / StreamlitSecretNotFoundError 모두 try로 흡수
                v = secrets.get(name) if hasattr(secrets, "get") else None
                if v:
                    v = str(v)
                    os.environ[name] = v  # 스레드에서도 os.getenv()로 접근 가능하도록 캐싱
                    return v
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        # streamlit 미설치 / secrets.toml 없음 / 기타 어떤 예외든 OK
        pass
    return None


def get_anthropic_key() -> str | None:
    """Anthropic Claude AI 분석용 키."""
    return _get_key("ANTHROPIC_API_KEY") or ANTHROPIC_API_KEY


def get_gemini_key() -> str | None:
    """Google Gemini AI 분석용 키 — GEMINI_API_KEY 전용 (YouTube 키와 혼용 방지)."""
    return _get_key("GEMINI_API_KEY")


def get_youtube_key() -> str | None:
    """YouTube Data API v3 전용 키. GOOGLE_API_KEY는 하위 호환 폴백."""
    return _get_key("YOUTUBE_API_KEY", "GOOGLE_API_KEY")


def get_reddit_creds() -> tuple[str, str] | None:
    """Reddit OAuth (script type) — 레이트 리밋 상향. (client_id, client_secret)."""
    cid = _get_key("REDDIT_CLIENT_ID")
    sec = _get_key("REDDIT_CLIENT_SECRET")
    if cid and sec:
        return cid, sec
    return None


def get_naver_creds() -> tuple[str, str] | None:
    """네이버 개발자 오픈 API. (client_id, client_secret)."""
    cid = _get_key("NAVER_CLIENT_ID")
    sec = _get_key("NAVER_CLIENT_SECRET")
    if cid and sec:
        return cid, sec
    return None


def get_scrapecreators_key() -> str | None:
    """Threads/TikTok 정식 스크래핑 API (유료)."""
    return _get_key("SCRAPECREATORS_API_KEY")

# ---------------------------------------------------------------------------
# 스크래핑 파라미터
# ---------------------------------------------------------------------------
REQUEST_DELAY: float = float(os.getenv("REQUEST_DELAY", "0.5"))
CACHE_TTL: int = int(os.getenv("CACHE_TTL", "300"))  # 5분
MAX_ITEMS_PER_SITE: int = int(os.getenv("MAX_ITEMS_PER_SITE", "15"))
REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "10"))

# ---------------------------------------------------------------------------
# AI 분석
# ---------------------------------------------------------------------------
ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
ANALYZE_BATCH_SIZE: int = int(os.getenv("ANALYZE_BATCH_SIZE", "20"))
MAX_CACHE_SIZE: int = int(os.getenv("MAX_CACHE_SIZE", "500"))  # analysis_cache 최대 항목 수

# ---------------------------------------------------------------------------
# 저장 경로
# ---------------------------------------------------------------------------
SAVED_IDEAS_PATH: Path = BASE_DIR / "saved_ideas.json"

# ---------------------------------------------------------------------------
# 스크래퍼 레지스트리 — (key, 라벨, 카테고리, 기본 ON 여부, 컬러)
# ---------------------------------------------------------------------------
SCRAPER_REGISTRY: list[dict] = [
    # 🇰🇷 국내 커뮤니티 — 모두 기본 ON
    # (제거된 플랫폼:
    #   - 아카라이브/더쿠/에펨코리아: Cloudflare/자체 방화벽으로 Streamlit Cloud 접근 불가
    #   - 루리웹/인스티즈: HTML 구조 파악 불가로 지속적 파싱 실패)
    {"key": "dcinside",   "label": "디시인사이드",  "group": "kr", "default": True, "color": "#1D5A8E"},
    {"key": "ppomppu",    "label": "뽐뿌",          "group": "kr", "default": True, "color": "#FF6B00"},
    {"key": "inven",      "label": "인벤",          "group": "kr", "default": True, "color": "#00A651"},
    {"key": "natepan",    "label": "네이트판",      "group": "kr", "default": True, "color": "#EC2028"},
    {"key": "clien",      "label": "클리앙",        "group": "kr", "default": True, "color": "#3B82F6"},
    {"key": "bobaedream", "label": "보배드림",      "group": "kr", "default": True, "color": "#333333"},
    {"key": "mlbpark",    "label": "MLB파크",       "group": "kr", "default": True, "color": "#003DA5"},
    {"key": "humoruniv",  "label": "웃긴대학",      "group": "kr", "default": True, "color": "#FFD700"},
    {"key": "naver_trends", "label": "네이버 트렌드", "group": "kr", "default": True, "color": "#03C75A"},
    # 🌍 해외 — 모두 기본 OFF (필요 시 수동으로 켜기)
    {"key": "reddit",        "label": "Reddit",       "group": "global", "default": False, "color": "#FF4500"},
    {"key": "threads",       "label": "Threads",      "group": "global", "default": False, "color": "#000000"},
    {"key": "youtube_trends","label": "YouTube 인기", "group": "global", "default": False, "color": "#FF0000"},
    {"key": "tiktok_trends", "label": "TikTok",       "group": "global", "default": False, "color": "#010101"},
]


def get_platform_color(source: str) -> str:
    """플랫폼명(label 또는 key)으로 컬러 HEX 반환."""
    for item in SCRAPER_REGISTRY:
        if source in (item["key"], item["label"]):
            return item["color"]
    return "#6B7280"


CATEGORIES = ["전체", "유머/밈", "이슈/뉴스", "IT/테크", "게임", "라이프", "연예", "핫딜"]
