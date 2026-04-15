"""한글 폰트 로더 — 워드클라우드/matplotlib 공용.

우선순위:
1) 프로젝트 내 번들된 폰트 (assets/NanumGothic-Regular.ttf)
2) 시스템에 설치된 한글 폰트 (Nanum*, NotoSansCJK*, AppleSDGothic*)
3) Google Fonts CDN에서 다운로드 → 캐시 디렉토리 저장
"""
from __future__ import annotations

import glob
import logging
import os
import tempfile
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

# Google Fonts가 호스팅하는 NanumGothic Regular (안정적, OFL 라이센스)
_FONT_URL = (
    "https://github.com/google/fonts/raw/main/ofl/nanumgothic/"
    "NanumGothic-Regular.ttf"
)

_CACHE_DIR = Path(tempfile.gettempdir()) / "shorts_trend_collector_fonts"
_CACHE_FONT = _CACHE_DIR / "NanumGothic-Regular.ttf"

# 번들 후보 (프로젝트 내에 수동으로 넣을 수도 있게)
_BUNDLE_DIR = Path(__file__).resolve().parent / "assets"
_BUNDLE_FONT = _BUNDLE_DIR / "NanumGothic-Regular.ttf"


def _system_korean_font() -> str | None:
    """시스템에 설치된 한글 폰트 경로 탐색."""
    candidates: list[str] = []
    for pattern in (
        "/usr/share/fonts/**/*Nanum*.ttf",
        "/usr/share/fonts/**/NotoSansCJK*.ttc",
        "/usr/share/fonts/**/NotoSansCJK*.otf",
        "/usr/share/fonts/**/*NotoSansKR*.ttf",
        "/System/Library/Fonts/**/AppleSDGothic*",
        "/Library/Fonts/**/AppleSDGothic*",
        "C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/NanumGothic.ttf",
    ):
        candidates += glob.glob(pattern, recursive=True)
    return candidates[0] if candidates else None


def _download_font() -> str | None:
    """Google Fonts에서 NanumGothic 다운로드 → 캐시."""
    if _CACHE_FONT.exists() and _CACHE_FONT.stat().st_size > 10_000:
        return str(_CACHE_FONT)

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        # Google이 CDN에서 재다이렉트 → github raw → blob
        req = urllib.request.Request(
            _FONT_URL,
            headers={"User-Agent": "Mozilla/5.0 shorts-trend-collector"},
        )
        with urllib.request.urlopen(req, timeout=15) as r, open(_CACHE_FONT, "wb") as out:
            out.write(r.read())
        if _CACHE_FONT.stat().st_size > 10_000:
            logger.info("폰트 다운로드 완료: %s", _CACHE_FONT)
            return str(_CACHE_FONT)
    except Exception as exc:  # noqa: BLE001
        logger.warning("폰트 다운로드 실패: %s", exc)
        try:
            if _CACHE_FONT.exists():
                os.unlink(_CACHE_FONT)
        except Exception:  # noqa: BLE001
            pass
    return None


def get_korean_font_path() -> str | None:
    """우선순위대로 한글 폰트 경로 반환. 없으면 None."""
    # 1) 프로젝트 번들
    if _BUNDLE_FONT.exists():
        return str(_BUNDLE_FONT)
    # 2) 시스템
    sys_font = _system_korean_font()
    if sys_font:
        return sys_font
    # 3) CDN 다운로드
    return _download_font()
