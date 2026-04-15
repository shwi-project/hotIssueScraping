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


def get_anthropic_key() -> str | None:
    """현재 유효한 Anthropic API 키를 반환. 우선순위:
    1) os.environ["ANTHROPIC_API_KEY"] (앱 실행 중 UI에서 입력 시 여기에 저장)
    2) Streamlit secrets (배포 환경)
    3) .env 파일 값 (import 시점에 로드됨)
    """
    env_val = os.getenv("ANTHROPIC_API_KEY")
    if env_val:
        return env_val
    # Streamlit secrets (있을 때만)
    try:
        import streamlit as st
        if "ANTHROPIC_API_KEY" in st.secrets:
            return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:  # noqa: BLE001
        pass
    return ANTHROPIC_API_KEY

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
ANALYZE_BATCH_SIZE: int = int(os.getenv("ANALYZE_BATCH_SIZE", "20"))

# ---------------------------------------------------------------------------
# 저장 경로
# ---------------------------------------------------------------------------
SAVED_IDEAS_PATH: Path = BASE_DIR / "saved_ideas.json"

# ---------------------------------------------------------------------------
# 스크래퍼 레지스트리 — (key, 라벨, 카테고리, 기본 ON 여부, 컬러)
# ---------------------------------------------------------------------------
SCRAPER_REGISTRY: list[dict] = [
    # 🇰🇷 국내 커뮤니티
    {"key": "dcinside",   "label": "디시인사이드",  "group": "kr", "default": True,  "color": "#1D5A8E"},
    {"key": "fmkorea",    "label": "에펨코리아",    "group": "kr", "default": True,  "color": "#2563EB"},
    {"key": "ppomppu",    "label": "뽐뿌",          "group": "kr", "default": True,  "color": "#FF6B00"},
    {"key": "ruliweb",    "label": "루리웹",        "group": "kr", "default": False, "color": "#0066CC"},
    {"key": "theqoo",     "label": "더쿠",          "group": "kr", "default": True,  "color": "#7B2FF7"},
    {"key": "inven",      "label": "인벤",          "group": "kr", "default": False, "color": "#00A651"},
    {"key": "natepan",    "label": "네이트판",      "group": "kr", "default": True,  "color": "#EC2028"},
    {"key": "arcalive",   "label": "아카라이브",    "group": "kr", "default": False, "color": "#5AC8FA"},
    {"key": "clien",      "label": "클리앙",        "group": "kr", "default": True,  "color": "#3B82F6"},
    {"key": "instiz",     "label": "인스티즈",      "group": "kr", "default": False, "color": "#FF69B4"},
    {"key": "bobaedream", "label": "보배드림",      "group": "kr", "default": False, "color": "#333333"},
    {"key": "mlbpark",    "label": "MLB파크",       "group": "kr", "default": False, "color": "#003DA5"},
    {"key": "humoruniv",  "label": "웃긴대학",      "group": "kr", "default": False, "color": "#FFD700"},
    {"key": "naver_trends", "label": "네이버 트렌드", "group": "kr", "default": True, "color": "#03C75A"},
    # 🌍 해외
    {"key": "reddit",        "label": "Reddit",       "group": "global", "default": True,  "color": "#FF4500"},
    {"key": "hackernews",    "label": "Hacker News",  "group": "global", "default": False, "color": "#FF6600"},
    {"key": "threads",       "label": "Threads",      "group": "global", "default": False, "color": "#000000"},
    {"key": "youtube_trends","label": "YouTube 인기", "group": "global", "default": True,  "color": "#FF0000"},
    {"key": "tiktok_trends", "label": "TikTok",       "group": "global", "default": False, "color": "#010101"},
]


def get_platform_color(source: str) -> str:
    """플랫폼명(label 또는 key)으로 컬러 HEX 반환."""
    for item in SCRAPER_REGISTRY:
        if source in (item["key"], item["label"]):
            return item["color"]
    return "#6B7280"


CATEGORIES = ["전체", "유머/밈", "이슈/뉴스", "IT/테크", "게임", "라이프", "연예", "핫딜"]
