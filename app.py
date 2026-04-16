"""🎬 쇼츠 소재 수집기 — Streamlit 메인 앱."""
from __future__ import annotations

import logging
import os
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import streamlit as st

import analyzer
import storage
from config import (
    CATEGORIES,
    MAX_CACHE_SIZE,
    MAX_ITEMS_PER_SITE,
    SCRAPER_REGISTRY,
    get_platform_color,
)
from scrapers import get_scraper

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# ---------------------------------------------------------------------------
# 페이지 설정
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="🎬 쇼츠 소재 수집기",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed",  # 사이드바 사용 안 함 (모든 컨트롤 메인 영역)
)

# ---------------------------------------------------------------------------
# 커스텀 CSS
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .platform-badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        color: white;
        font-size: 0.75rem;
        font-weight: 600;
        margin-right: 6px;
    }
    .category-tag {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 8px;
        background: #E5E7EB;
        color: #374151;
        font-size: 0.7rem;
        margin-right: 4px;
    }
    .item-card {
        border: 1px solid #E5E7EB;
        border-radius: 12px;
        padding: 14px 16px;
        margin-bottom: 10px;
        background: #FFFFFF;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }
    .item-title {
        font-weight: 700;
        font-size: 1rem;
        margin: 6px 0 4px 0;
        color: var(--text-color, #111827);
        line-height: 1.35;
    }
    .item-title a {
        color: var(--link-color, #2563EB) !important;
    }
    .item-meta {
        font-size: 0.8rem;
        opacity: 0.72;
        color: var(--text-color, #6B7280);
        margin-bottom: 4px;
    }
    .stars { color: #F59E0B; }

    /* 다크모드 가독성 보강 */
    @media (prefers-color-scheme: dark) {
        .item-title { color: #F3F4F6 !important; }
        .item-title a { color: #93C5FD !important; }
        .item-meta { color: #D1D5DB !important; }
        .category-tag {
            background: #374151 !important;
            color: #E5E7EB !important;
        }
        .summary-row {
            background: #1F2937 !important;
            border-color: #374151 !important;
            color: #F3F4F6 !important;
        }
        .summary-row b { color: #F9FAFB !important; }
        .saved-pill {
            background: #064E3B !important;
            color: #A7F3D0 !important;
        }
        .save-pill {
            background: #451A03 !important;
            color: #FED7AA !important;
            border-color: #F59E0B !important;
        }
        .save-pill:hover {
            background: #78350F !important;
            color: #FED7AA !important;
        }
        .link-pill {
            background: #374151 !important;
            color: #E5E7EB !important;
        }
        .link-pill:hover { background: #4B5563 !important; }
        .category-tag.warn {
            background: #78350F !important;
            color: #FEF3C7 !important;
        }
    }

    /* 카드 헤더 한 줄 레이아웃 (모바일 포함) */
    .card-header {
        display: flex;
        flex-wrap: wrap;
        gap: 4px;
        align-items: center;
        margin-bottom: 6px;
    }
    .category-tag.warn {
        background: #FEF3C7 !important;
        color: #92400E !important;
    }
    .saved-pill {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        background: #D1FAE5;
        color: #065F46;
        font-size: 0.75rem;
        font-weight: 600;
        margin-left: auto; /* 오른쪽 끝으로 */
    }
    .save-pill {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        background: #FEF3C7;
        color: #92400E !important;
        font-size: 0.75rem;
        font-weight: 600;
        text-decoration: none !important;
        border: 1px solid #F59E0B;
        margin-left: auto; /* 오른쪽 끝으로 */
    }
    .save-pill:hover { background: #FDE68A; color: #78350F !important; }
    .link-pill {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        background: #E5E7EB;
        color: #374151 !important;
        font-size: 0.75rem;
        font-weight: 500;
        text-decoration: none !important;
        margin-left: auto; /* save-pill 없을 때 오른쪽 정렬 */
    }
    /* save-pill 또는 saved-pill 이 있으면 링크는 그 옆에 바로 붙음 */
    .save-pill + .link-pill,
    .saved-pill + .link-pill {
        margin-left: 4px;
    }
    .link-pill:hover { background: #D1D5DB; }

    /* ★ 카드 헤더 영역 (st.container(key=cardhead_*)) — 좁은 범위 CSS */
    /* 모바일에서도 가로 유지 + 버튼 작게 (다른 버튼 영향 없음) */
    div[class*="st-key-cardhead_"] div[data-testid="stHorizontalBlock"] {
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        align-items: center !important;
        gap: 4px !important;
    }
    div[class*="st-key-cardhead_"] div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
    div[class*="st-key-cardhead_"] div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
        width: auto !important;
        flex: 0 1 auto !important;
        min-width: 0 !important;
    }
    div[class*="st-key-cardhead_"] div[data-testid="stHorizontalBlock"] > div:first-child {
        flex: 1 1 auto !important;
    }
    /* 카드 헤더 우측 컬럼 (★ 아이콘만) — 좁게 */
    div[class*="st-key-cardhead_"] div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:last-child,
    div[class*="st-key-cardhead_"] div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child {
        max-width: 50px !important;
        min-width: 35px !important;
        flex: 0 0 auto !important;
    }
    /* ★ 버튼 본체 — 작았던 버전 (transform scale 트릭) */
    div[class*="st-key-cardhead_"] .stButton {
        transform: scale(0.65);
        transform-origin: right top;
        margin-top: -10px !important;
        margin-bottom: -10px !important;
        margin-right: -6px !important;
    }
    div[class*="st-key-cardhead_"] .stButton button,
    div[class*="st-key-cardhead_"] button[kind],
    div[class*="st-key-cardhead_"] button[data-testid*="baseButton"] {
        min-height: 28px !important;
        height: 28px !important;
        padding: 0 10px !important;
        border-radius: 14px !important;
        font-size: 0.9rem !important;
        line-height: 1 !important;
        font-weight: 700 !important;
        white-space: nowrap !important;
    }

    /* 사이드바 완전 숨김 (모든 컨트롤 메인 영역으로 이동) */
    section[data-testid="stSidebar"] { display: none !important; }
    div[data-testid="collapsedControl"] { display: none !important; }

    /* 상단 네비 래디오 — 탭처럼 보이게 pill 스타일 */
    div[data-testid="stRadio"] > div[role="radiogroup"] {
        gap: 4px;
        flex-wrap: wrap;
    }
    div[data-testid="stRadio"] label[data-baseweb="radio"] {
        background: #F3F4F6;
        padding: 6px 14px !important;
        border-radius: 20px;
        cursor: pointer;
        margin: 2px;
    }
    div[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) {
        background: #3B82F6;
        color: white;
    }
    div[data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child {
        display: none; /* 래디오 동그라미 숨김 */
    }

    /* 수집 요약 한 줄 */
    .summary-row {
        display: flex;
        flex-wrap: wrap;
        gap: 14px;
        padding: 10px 14px;
        background: #F9FAFB;
        border: 1px solid #E5E7EB;
        border-radius: 10px;
        margin-bottom: 12px;
        font-size: 0.9rem;
        white-space: nowrap;
    }
    .summary-row span { display: inline-flex; align-items: center; gap: 3px; }
    .summary-row b { color: #111827; }

    /* 맨 위로 가기 버튼 (floating) */
    .back-to-top {
        position: fixed;
        right: 18px;
        bottom: 72px;
        width: 48px;
        height: 48px;
        border-radius: 50%;
        background: #3B82F6;
        color: white !important;
        font-size: 1.3rem;
        font-weight: 700;
        text-align: center;
        line-height: 48px;
        text-decoration: none;
        box-shadow: 0 4px 14px rgba(0,0,0,0.25);
        z-index: 9999;
        opacity: 0.92;
        transition: background 0.2s, transform 0.2s;
    }
    .back-to-top:hover {
        background: #2563EB;
        transform: scale(1.08);
        color: white !important;
    }

    /* ---------- 📱 모바일 대응 ---------- */
    @media (max-width: 768px) {
        /* 메인 블록 좌우 여백 축소 */
        .block-container {
            padding-left: 0.75rem !important;
            padding-right: 0.75rem !important;
            padding-top: 1rem !important;
        }
        /* 카드 그리드를 세로로 적층 (3열 → 1열) */
        div[data-testid="stHorizontalBlock"] {
            flex-direction: column !important;
            gap: 0.4rem !important;
        }
        div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
        div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
            width: 100% !important;
            flex: 1 1 100% !important;
            min-width: 0 !important;
        }
        /* 카드/제목 약간 축소 */
        .item-title { font-size: 0.95rem; }
        .item-card { padding: 10px 12px; }
        /* 탭 라벨 compact + 가로 스크롤 보장 */
        button[data-baseweb="tab"] {
            padding-left: 8px !important;
            padding-right: 8px !important;
            font-size: 0.85rem !important;
            min-width: unset !important;
            flex: 0 0 auto !important;
        }
        div[data-baseweb="tab-list"] {
            overflow-x: auto !important;
            scrollbar-width: thin;
            -webkit-overflow-scrolling: touch;
        }
        /* 메트릭도 좁은 화면에서 세로 나열되도록 */
        [data-testid="stMetric"] {
            padding: 4px 0;
        }
        /* 사이드바가 열렸을 때 반투명 오버레이 더 어둡게 */
        section[data-testid="stSidebar"] {
            width: 85vw !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session state 초기화
# ---------------------------------------------------------------------------
if "results" not in st.session_state:
    st.session_state.results = []  # type: list[dict]
if "last_summary" not in st.session_state:
    st.session_state.last_summary = {}
if "analysis_cache" not in st.session_state:
    st.session_state.analysis_cache = {}  # url -> analysis dict


# ---------------------------------------------------------------------------
# 수집 로직
# ---------------------------------------------------------------------------
# 캐시 제거 — 매 수집마다 새로 가져오게 (사용자 요청)
def collect_from(keys: tuple[str, ...], limit: int) -> dict:
    """선택된 플랫폼에서 인기글 수집 — 캐시 없음, 매 호출마다 새로."""
    results: list[dict] = []
    success: list[str] = []
    failed: list[dict] = []  # [{"key": ..., "reason": ...}]

    def _run(key: str) -> tuple[str, list[dict], str]:
        scraper = get_scraper(key)
        if scraper is None:
            return key, [], "스크래퍼 구현 없음"
        try:
            items = scraper.get_trending(limit=limit)
            reason = scraper.last_error if not items else ""
            return key, items, reason
        except Exception as exc:  # noqa: BLE001
            return key, [], f"{type(exc).__name__}: {str(exc)[:120]}"

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_run, k): k for k in keys}
        for fut in as_completed(futures):
            key, items, reason = fut.result()
            if items:
                success.append(key)
                results.extend(items)
            else:
                failed.append({"key": key, "reason": reason or "알 수 없는 실패"})

    return {
        "items": results,
        "success": success,
        "failed": failed,
    }


def filter_results(results: list[dict], *, category: str, keyword: str,
                   platforms: list[str] | None, sort: str) -> list[dict]:
    # platforms가 None이 아니면 명시적으로 필터 (빈 리스트면 빈 결과)
    if platforms is not None:
        if len(platforms) == 0:
            return []
        results = [r for r in results if r.get("source") in platforms]

    out = list(results)
    if category and category != "전체":
        out = [r for r in out if r.get("category") == category]
    if keyword:
        kw = keyword.strip().lower()
        out = [r for r in out
               if kw in (r.get("title", "") + " " + r.get("summary", "")).lower()]

    def _num(r: dict, k: str) -> int:
        """메타 필드를 안전하게 정수로."""
        v = r.get(k, 0)
        if isinstance(v, int):
            return v
        try:
            return int(v or 0)
        except (ValueError, TypeError):
            return 0

    key_map = {"추천순": "score", "조회순": "views", "댓글순": "comments"}
    key = key_map.get(sort)
    if key:
        # 메타 있는 항목(값 > 0)을 먼저, 없는 항목은 뒤로 밀고 각각 내림차순
        def _sort_key(r: dict) -> tuple[int, int]:
            v = _num(r, key)
            return (1 if v > 0 else 0, v)  # 있는 것(1)이 먼저, 같은 그룹 내에선 값 내림차순
        out.sort(key=_sort_key, reverse=True)
    elif sort == "인기순":
        # 복합 인기도
        out.sort(
            key=lambda r: _num(r, "score") * 10
                          + _num(r, "views") // 100
                          + _num(r, "comments") * 3,
            reverse=True,
        )
    elif sort == "최신순":
        out.sort(key=lambda r: r.get("collected_at", ""), reverse=True)
    return out


# ---------------------------------------------------------------------------
# 사이드바: 플랫폼 체크박스 세션 상태 초기화 (한 번만)
# ---------------------------------------------------------------------------
for _item in SCRAPER_REGISTRY:
    _k = f"chk_{_item['key']}"
    if _k not in st.session_state:
        st.session_state[_k] = _item["default"]


def _toggle_group(group: str) -> None:
    """'전체 선택/해제' 체크박스 콜백 — 해당 그룹의 개별 체크박스를 일괄 변경."""
    master_key = f"{group}_all"
    new_val = st.session_state.get(master_key, False)
    for it in SCRAPER_REGISTRY:
        if it["group"] == group:
            st.session_state[f"chk_{it['key']}"] = new_val


def _sync_master(group: str) -> None:
    """마스터 체크박스 상태를 개별 체크박스 상태와 동기화.
    모든 개별이 체크됐으면 마스터도 체크, 아니면 해제.
    (마스터 체크박스를 렌더링하기 직전에 호출해야 함)"""
    all_checked = all(
        st.session_state.get(f"chk_{it['key']}", it["default"])
        for it in SCRAPER_REGISTRY if it["group"] == group
    )
    st.session_state[f"{group}_all"] = all_checked


# ---------------------------------------------------------------------------
# 메인 상단: 타이틀 + 네비게이션 + 팝오버 컨트롤
# ---------------------------------------------------------------------------
st.markdown('<div id="page-top"></div>', unsafe_allow_html=True)
st.title("🎬 쇼츠 소재 수집기")
st.caption(
    f"국내외 {len(SCRAPER_REGISTRY)}개 인기 플랫폼에서 바이럴 콘텐츠를 수집합니다."
)

# 네비게이션 (가로 래디오 — tab보다 모바일에 안정적)
_page = st.radio(
    "페이지",
    ["📊 결과", "★ 스크랩", "📈 분석", "⚙️ 설정"],
    horizontal=True,
    label_visibility="collapsed",
    key="page_nav",
)

# 플랫폼/필터/수집 컨트롤은 팝오버 안에
pop_col1, pop_col2 = st.columns([3, 1])
with pop_col1:
    with st.popover("⚙️ 플랫폼 · 필터 · 수집", use_container_width=True):
        st.markdown("### 🇰🇷 국내 커뮤니티")
        _sync_master("kr")  # 개별 체크박스 상태와 동기화
        st.checkbox(
            "전체 선택/해제",
            key="kr_all",
            on_change=_toggle_group,
            args=("kr",),
        )
        kr_cols = st.columns(2)
        kr_keys: list[str] = []
        for i, item in enumerate(SCRAPER_REGISTRY):
            if item["group"] != "kr":
                continue
            with kr_cols[i % 2]:
                if st.checkbox(item["label"], key=f"chk_{item['key']}"):
                    kr_keys.append(item["key"])

        st.markdown("### 🌍 해외 플랫폼")
        _sync_master("global")  # 개별 체크박스 상태와 동기화
        st.checkbox(
            "전체 선택/해제",
            key="global_all",
            on_change=_toggle_group,
            args=("global",),
        )
        gl_cols = st.columns(2)
        gl_keys: list[str] = []
        for i, item in enumerate(SCRAPER_REGISTRY):
            if item["group"] != "global":
                continue
            with gl_cols[i % 2]:
                if st.checkbox(item["label"], key=f"chk_{item['key']}"):
                    gl_keys.append(item["key"])

        st.divider()
        st.markdown("### 🔎 필터")
        genre = st.selectbox("장르", CATEGORIES, index=0, key="genre_filter")
        keyword = st.text_input("추가 키워드 (제목/요약 검색)", "", key="keyword_filter")
        per_site_limit = st.slider(
            "사이트당 수집 건수", 5, 20, MAX_ITEMS_PER_SITE, key="per_site_limit"
        )

        st.divider()
        _ai_provider = analyzer.active_provider()
        ai_on = st.toggle(
            f"🤖 AI 분석 ON{f' ({_ai_provider})' if _ai_provider else ''}",
            value=analyzer.is_available(),
            help="ANTHROPIC_API_KEY 또는 GEMINI_API_KEY 필요 — 설정 탭에서 입력",
            key="ai_on_toggle",
        )
        if ai_on and not analyzer.is_available():
            st.warning("API 키가 없어요. 설정 탭에서 Anthropic 또는 Gemini 키를 입력하세요.")

with pop_col2:
    run_btn = st.button(
        "🔍 수집",
        type="primary",
        use_container_width=True,
        help="선택한 플랫폼에서 인기글 수집",
    )

# 팝오버 안에서 선언된 변수들을 바깥에서도 쓸 수 있도록 세션에 백업
# (팝오버가 닫혀있어도 이전 값 보존)
_genre = st.session_state.get("genre_filter", "전체")
_keyword = st.session_state.get("keyword_filter", "")
_per_site_limit = st.session_state.get("per_site_limit", MAX_ITEMS_PER_SITE)
_ai_on = st.session_state.get("ai_on_toggle", False)
# 체크박스 값도 세션에서 재계산 (팝오버 닫히면 kr_keys/gl_keys가 이전 값이 됨)
kr_keys = [it["key"] for it in SCRAPER_REGISTRY
           if it["group"] == "kr" and st.session_state.get(f"chk_{it['key']}")]
gl_keys = [it["key"] for it in SCRAPER_REGISTRY
           if it["group"] == "global" and st.session_state.get(f"chk_{it['key']}")]
# 호환 유지용 별칭
genre = _genre
keyword = _keyword
per_site_limit = _per_site_limit
ai_on = _ai_on

st.divider()


# ---------------------------------------------------------------------------
# 수집 실행
# ---------------------------------------------------------------------------
if run_btn:
    selected = tuple(kr_keys + gl_keys)
    if not selected:
        st.warning("최소 한 개 이상의 플랫폼을 선택하세요.")
    else:
        t0 = time.time()
        with st.spinner(f"🌐 {len(selected)}개 플랫폼에서 수집 중…"):
            payload = collect_from(selected, per_site_limit)
        elapsed = time.time() - t0

        items = payload["items"]

        # AI 분석 (배치) — analysis_cache로 중복 API 호출 방지
        if ai_on and items and analyzer.is_available():
            cache = st.session_state.analysis_cache
            # 캐시에 없는 항목만 새로 분석
            uncached = [it for it in items if not (it.get("url") and it["url"] in cache)]
            cached_urls = {it["url"] for it in items if it.get("url") and it["url"] in cache}

            if uncached:
                with st.spinner(f"🤖 AI가 쇼츠 아이디어를 분석하는 중… ({len(uncached)}건 신규)"):
                    analyzed = analyzer.analyze_batch(uncached)
                # 새 분석 결과를 캐시에 저장
                for it in analyzed:
                    if it.get("url") and it.get("analysis"):
                        cache[it["url"]] = it["analysis"]
                # uncached → analyzed 로 교체
                url_to_analyzed = {it.get("url"): it for it in analyzed if it.get("url")}
                items = [
                    url_to_analyzed.get(it.get("url"), it) if it.get("url") not in cached_urls
                    else it
                    for it in items
                ]

            # 캐시된 항목에 분석 결과 적용
            items = [
                {**it, "analysis": cache[it["url"]]} if (it.get("url") in cache and not it.get("analysis"))
                else it
                for it in items
            ]

            # 캐시 크기 상한 초과 시 오래된 항목부터 제거
            if len(cache) > MAX_CACHE_SIZE:
                excess = len(cache) - MAX_CACHE_SIZE
                for old_key in list(cache.keys())[:excess]:
                    del cache[old_key]

        st.session_state.results = items
        # 플랫폼 뱃지 선택 초기화: 이전 수집과 소스 목록이 달라지면 Streamlit이
        # 이전 상태와 새 options를 비교해 빈 선택으로 만드는 현상 방지
        st.session_state.pop("platform_pills", None)
        st.session_state.last_summary = {
            "total": len(items),
            "elapsed": elapsed,
            "success": payload["success"],
            "failed": payload["failed"],
            "selected": selected,
        }


# ---------------------------------------------------------------------------
# 카드 렌더링 헬퍼
# ---------------------------------------------------------------------------
def render_card(item: dict, *, key_prefix: str, show_save: bool = True) -> None:
    source = item.get("source", "")
    color = get_platform_color(source)
    category = item.get("category", "기타")

    # 메타데이터(조회/추천/댓글) 유무 확인 — 인기글 진위 판단 근거
    has_meta = any(int(item.get(k, 0) or 0) > 0 for k in ("score", "views", "comments"))

    title = item.get("title", "(제목 없음)")
    engagement = item.get("engagement", "")
    url = item.get("url", "")
    is_saved = storage.is_saved(url) if url else False

    with st.container(border=True):
        # 헤더: 좌측 뱃지 row + 우측 ★/✅ 버튼 (key로 CSS scope)
        with st.container(key=f"cardhead_{key_prefix}"):
            head_l, head_r = st.columns([4, 1])
            with head_l:
                header_bits = [
                    f'<span class="platform-badge" style="background:{color};">{source}</span>',
                    f'<span class="category-tag">{category}</span>',
                ]
                if not has_meta:
                    header_bits.append(
                        '<span class="category-tag warn" title="조회/추천/댓글 수치 없음">'
                        '⚠️ 메타없음</span>'
                    )
                st.markdown(
                    '<div class="card-header">' + "".join(header_bits) + '</div>',
                    unsafe_allow_html=True,
                )
            with head_r:
                if show_save and url:
                    if is_saved:
                        st.markdown(
                            "<div style='text-align:right;font-size:1.1rem;"
                            "padding-top:2px;'>✅</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        try:
                            clicked = st.button(
                                "★", key=f"{key_prefix}_save",
                                help="스크랩", type="tertiary",
                            )
                        except (TypeError, ValueError):
                            clicked = st.button(
                                "★", key=f"{key_prefix}_save", help="스크랩",
                            )
                        if clicked:
                            if storage.add_item(item):
                                st.toast("스크랩됨", icon="⭐")
                                st.rerun()

        if url:
            st.markdown(f'<div class="item-title"><a href="{url}" target="_blank">{title}</a></div>',
                        unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="item-title">{title}</div>', unsafe_allow_html=True)
        if engagement:
            st.markdown(f'<div class="item-meta">📊 {engagement}</div>', unsafe_allow_html=True)
        elif not has_meta:
            st.markdown(
                '<div class="item-meta" style="color:#92400E;" '
                'title="사이트 목록에서 숫자가 표시되지 않거나, 스크래퍼가 셀렉터를 못 찾았거나, '
                '아이콘만 사용해 텍스트로 추출 불가한 경우입니다.">'
                '⚠️ 추천/조회/댓글 수치 없음 — 원문 확인 권장</div>',
                unsafe_allow_html=True,
            )
        if item.get("thumbnail"):
            st.image(item["thumbnail"], use_container_width=True)

        analysis = item.get("analysis")
        if analysis:
            with st.expander("💡 AI 분석 결과", expanded=False):
                if analysis.get("summary"):
                    st.markdown(f"**요약**: {analysis['summary']}")
                if analysis.get("shorts_idea"):
                    st.markdown(f"**💡 쇼츠 아이디어**: {analysis['shorts_idea']}")
                if analysis.get("target_audience"):
                    st.markdown(f"**🎯 타겟 시청자**: {analysis['target_audience']}")
                if analysis.get("hashtags"):
                    tags = " ".join(analysis["hashtags"])
                    st.markdown(f"**#️⃣ 해시태그**: {tags}")
                score = int(analysis.get("score", 0) or 0)
                if score:
                    stars = "⭐" * score + "☆" * (5 - score)
                    st.markdown(f"**활용도 점수**: <span class='stars'>{stars}</span> ({score}/5)",
                                unsafe_allow_html=True)
        elif analyzer.is_available():
            if st.button("🤖 AI 분석", key=f"{key_prefix}_single"):
                with st.spinner("분석 중…"):
                    analyzed = analyzer.analyze_single(item)
                    # 캐시에 저장
                    if analyzed.get("analysis") and item.get("url"):
                        cache = st.session_state.analysis_cache
                        cache[item["url"]] = analyzed["analysis"]
                        if len(cache) > MAX_CACHE_SIZE:
                            excess = len(cache) - MAX_CACHE_SIZE
                            for old_key in list(cache.keys())[:excess]:
                                del cache[old_key]
                    for i, r in enumerate(st.session_state.results):
                        if r.get("url") == item.get("url"):
                            st.session_state.results[i] = analyzed
                            break
                st.rerun()


# ---------------------------------------------------------------------------
# 메인 — 페이지 분기 (_page 래디오 값에 따라)
# ---------------------------------------------------------------------------

# ===== 📊 수집 결과 =====
if _page == "📊 결과":
    summary = st.session_state.last_summary
    if summary:
        # 메타데이터 있는 항목 비율 (인기글 진위 판단)
        with_meta = sum(
            1 for r in st.session_state.results
            if any(int(r.get(k, 0) or 0) > 0 for k in ("score", "views", "comments"))
        )
        total_items = len(st.session_state.results) or 1
        meta_pct = int(with_meta / total_items * 100)

        # 수집 요약 — 모바일까지 한 줄로 compact
        summary_html = f"""
<div class="summary-row" title="수집 요약">
    <span>📦 <b>{summary['total']}</b>건</span>
    <span>⏱ <b>{summary['elapsed']:.1f}</b>s</span>
    <span>✅ <b>{len(summary['success'])}</b>성공</span>
    <span>❌ <b>{len(summary['failed'])}</b>실패</span>
    <span>📊 메타 <b>{meta_pct}</b>%</span>
</div>
"""
        st.markdown(summary_html, unsafe_allow_html=True)

        if summary["failed"]:
            # {key: label} 룩업
            label_map = {r["key"]: r["label"] for r in SCRAPER_REGISTRY}

            # 모두 실패 / 대부분 실패일 때 상단에 눈에 띄는 도움말
            total_selected = len(summary["selected"])
            fail_count = len(summary["failed"])
            if fail_count == total_selected:
                st.error(
                    "**🚨 선택한 모든 플랫폼이 실패했어요.**\n\n"
                    "가능성 높은 원인:\n"
                    "1. **IP 차단** — 실행 환경(Streamlit Cloud 공용 IP 등)이 봇으로 감지돼 차단됨\n"
                    "2. **사이트 레이아웃 변경** — 스크래퍼 셀렉터 업데이트 필요\n"
                    "3. **일시적 장애 / 레이트 리밋** — 잠시 후 재시도\n\n"
                    "**시도해볼 것**: 로컬 PC에서 실행, 수집 건수를 줄여서 재시도, "
                    "Reddit · YouTube 같은 공개 API 기반 소스만 선택"
                )
            elif fail_count >= total_selected * 0.5:
                st.warning(
                    f"⚠️ 선택한 {total_selected}개 중 **{fail_count}개가 실패**했어요. "
                    "아래 사유 확인 후 실패한 플랫폼은 해제하고 다시 시도해보세요."
                )

            with st.expander(
                f"⚠️ 수집 실패 {fail_count}개 플랫폼 — 사유 보기",
                expanded=(fail_count == total_selected),
            ):
                st.markdown(
                    "| 플랫폼 | 실패 사유 |\n|---|---|\n" +
                    "\n".join(
                        f"| **{label_map.get(f['key'], f['key'])}** | {f['reason']} |"
                        for f in summary["failed"]
                    )
                )
                st.caption(
                    "💡 **실패 유형별 원인**\n\n"
                    "• `HTTP 403/429/430` — **사이트가 Streamlit Cloud IP를 봇으로 차단**. "
                    "아카라이브·더쿠·에펨코리아 등 Cloudflare/자체 방화벽 적용 사이트. "
                    "로컬 PC에서 실행하면 대부분 해결. 공식 API 없음.\n\n"
                    "• `연결 실패` — 사이트 자체 다운 또는 DNS 일시 오류. 잠시 후 재시도.\n\n"
                    "• `파싱 결과 0건` — 사이트 접근은 되나 HTML 구조 변경으로 게시글 못 찾음. "
                    "해당 스크래퍼 셀렉터 업데이트 필요 (GitHub 이슈 남겨주시면 반영)."
                )

    results = st.session_state.results
    if not results:
        st.info(
            "상단의 **⚙️ 플랫폼·필터·수집** 팝오버에서 플랫폼을 확인하고 "
            "**🔍 수집** 버튼을 눌러주세요."
        )
    else:
        all_sources = sorted({r.get("source", "") for r in results if r.get("source")})
        st.markdown("##### 플랫폼 (탭하여 켜기/끄기 — 모두 끄면 결과 숨김)")
        # st.pills (1.36+) — 뱃지 토글 형태. 없으면 multiselect로 폴백
        try:
            selected_platforms = st.pills(
                label="플랫폼 필터",
                options=all_sources,
                selection_mode="multi",
                default=all_sources,
                label_visibility="collapsed",
                key="platform_pills",
            )
        except (AttributeError, TypeError):
            selected_platforms = st.multiselect(
                "플랫폼 필터",
                options=all_sources,
                default=all_sources,
                label_visibility="collapsed",
            )

        sort_by = st.selectbox(
            "정렬",
            ["인기순", "추천순", "조회순", "댓글순", "최신순"],
            help="기본은 인기순(추천·조회·댓글 종합). 메타 없는 항목은 자동으로 뒤로 밀립니다.",
        )

        filtered = filter_results(
            results,
            category=genre,
            keyword=keyword,
            platforms=selected_platforms,
            sort=sort_by,
        )

        # 정렬 검증 힌트 — top 5의 정렬 기준 값을 보여줌
        st.caption(f"필터링 결과: {len(filtered)}건")
        if filtered and sort_by in ("추천순", "조회순", "댓글순"):
            _field_map = {"추천순": ("score", "추천"), "조회순": ("views", "조회"), "댓글순": ("comments", "댓글")}
            fld, label = _field_map[sort_by]
            top_values = []
            for r in filtered[:5]:
                v = r.get(fld, 0)
                try:
                    top_values.append(int(v or 0))
                except (ValueError, TypeError):
                    top_values.append(0)
            st.caption(
                f"🔎 정렬 검증 (상위 5개 {label}수): "
                + " → ".join(f"{v:,}" for v in top_values)
            )

        # 카드 3열 그리드
        cols = st.columns(3)
        for idx, item in enumerate(filtered):
            with cols[idx % 3]:
                render_card(item, key_prefix=f"res_{idx}")

# ===== ★ 스크랩 =====
elif _page == "★ 스크랩":
    saved_items = storage.load_all()
    sc1, sc2, sc3 = st.columns([2, 1, 1])
    sc1.markdown(f"### 스크랩된 소재 ({len(saved_items)}건)")

    if saved_items:
        sc2.download_button(
            "📥 전체 CSV 다운로드",
            data=storage.to_csv_bytes(),
            file_name="saved_shorts_ideas.csv",
            mime="text/csv",
            use_container_width=True,
        )
        if sc3.button("🗑️ 전체 삭제", use_container_width=True):
            st.session_state["_confirm_clear"] = True

        if st.session_state.get("_confirm_clear"):
            st.error("정말로 모두 삭제할까요?")
            c1, c2 = st.columns(2)
            if c1.button("✅ 확인"):
                storage.clear_all()
                st.session_state["_confirm_clear"] = False
                st.rerun()
            if c2.button("❌ 취소"):
                st.session_state["_confirm_clear"] = False
                st.rerun()

        st.divider()
        for idx, item in enumerate(saved_items):
            with st.container(border=True):
                col_a, col_b = st.columns([4, 1])
                with col_a:
                    source = item.get("source", "")
                    color = get_platform_color(source)
                    st.markdown(
                        f'<span class="platform-badge" style="background:{color};">{source}</span>'
                        f'<span class="category-tag">{item.get("category", "")}</span>',
                        unsafe_allow_html=True,
                    )
                    title = item.get("title", "")
                    url = item.get("url", "")
                    if url:
                        st.markdown(f'**[{title}]({url})**')
                    else:
                        st.markdown(f'**{title}**')
                    if item.get("engagement"):
                        st.caption(f"📊 {item['engagement']}")
                    if item.get("saved_at"):
                        st.caption(f"💾 스크랩: {item['saved_at'][:19]}")

                    analysis = item.get("analysis")
                    if analysis:
                        with st.expander("💡 AI 분석"):
                            if analysis.get("shorts_idea"):
                                st.markdown(f"**쇼츠 아이디어**: {analysis['shorts_idea']}")
                            if analysis.get("target_audience"):
                                st.markdown(f"**타겟**: {analysis['target_audience']}")
                            if analysis.get("hashtags"):
                                st.markdown(f"**해시태그**: {' '.join(analysis['hashtags'])}")

                    new_note = st.text_area(
                        "📝 메모",
                        value=item.get("note", ""),
                        key=f"note_{idx}",
                        height=70,
                    )
                    if new_note != item.get("note", ""):
                        if st.button("💾 메모 저장", key=f"note_save_{idx}"):
                            storage.update_note(url, new_note)
                            st.toast("메모 저장", icon="💾")
                            st.rerun()
                with col_b:
                    if st.button("🗑 삭제", key=f"del_{idx}"):
                        storage.remove_item(url)
                        st.rerun()
    else:
        st.info("아직 스크랩한 소재가 없어요. 수집 결과에서 **★ 스크랩** 버튼을 눌러 담아보세요.")

# ===== 📈 트렌드 분석 =====
elif _page == "📈 분석":
    results = st.session_state.results
    if not results:
        st.info("먼저 수집을 실행해야 분석을 볼 수 있어요.")
    else:
        # 플랫폼별 수집 건수
        st.subheader("📊 플랫폼별 수집 건수")
        src_counts = Counter(r.get("source", "") for r in results)
        src_df = pd.DataFrame(
            {"플랫폼": list(src_counts.keys()), "건수": list(src_counts.values())}
        ).sort_values("건수", ascending=False)
        st.bar_chart(src_df.set_index("플랫폼"))

        # 카테고리 분포 (Plotly 파이차트)
        st.subheader("🥧 카테고리 분포")
        try:
            import plotly.express as px
            cat_counts = Counter(r.get("category", "기타") for r in results)
            cat_df = pd.DataFrame(
                {"카테고리": list(cat_counts.keys()), "건수": list(cat_counts.values())}
            )
            fig = px.pie(cat_df, names="카테고리", values="건수", hole=0.35)
            st.plotly_chart(fig, use_container_width=True)
        except Exception:  # noqa: BLE001
            st.bar_chart(pd.DataFrame(
                {"카테고리": list(cat_counts.keys()), "건수": list(cat_counts.values())}
            ).set_index("카테고리"))

        # TOP 10 참여도
        st.subheader("🏆 참여도 TOP 10")
        top = sorted(results, key=lambda r: (r.get("score", 0) or 0) + (r.get("views", 0) or 0) // 100,
                     reverse=True)[:10]
        top_df = pd.DataFrame([
            {
                "제목": r.get("title", "")[:60],
                "플랫폼": r.get("source", ""),
                "추천": r.get("score", 0),
                "조회": r.get("views", 0),
                "댓글": r.get("comments", 0),
                "링크": r.get("url", ""),
            }
            for r in top
        ])
        st.dataframe(
            top_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "링크": st.column_config.LinkColumn(display_text="열기"),
            },
        )

        # 워드클라우드
        st.subheader("☁️ 키워드 워드클라우드")
        try:
            from wordcloud import WordCloud
            import matplotlib.pyplot as plt
            import matplotlib
            matplotlib.rcParams["axes.unicode_minus"] = False

            from fonts import get_korean_font_path

            text = " ".join(r.get("title", "") for r in results)

            with st.spinner("한글 폰트 준비 중…"):
                font_path = get_korean_font_path()

            if not font_path:
                st.warning(
                    "한글 폰트를 찾거나 받지 못했어요. "
                    "인터넷 제한 환경이면 `assets/NanumGothic-Regular.ttf`로 수동 배치하세요."
                )
            else:
                wc = WordCloud(
                    font_path=font_path,
                    background_color="white",
                    width=800,
                    height=400,
                    max_words=80,
                    colormap="tab10",
                    prefer_horizontal=0.9,
                )
                img = wc.generate(text)
                fig, ax = plt.subplots(figsize=(10, 5))
                ax.imshow(img, interpolation="bilinear")
                ax.axis("off")
                st.pyplot(fig)
                st.caption(f"📝 폰트 경로: `{font_path}`")
        except Exception as exc:  # noqa: BLE001
            st.warning(f"워드클라우드 생성 실패: {type(exc).__name__}: {exc}")


# ===== ⚙️ 설정 =====
elif _page == "⚙️ 설정":
    from config import (
        get_anthropic_key, get_gemini_key, get_youtube_key,
        get_reddit_creds, get_naver_creds, get_scrapecreators_key,
    )

    st.header("⚙️ 설정")
    st.caption(
        "**API 키는 모두 필수입니다.** 키가 없으면 해당 플랫폼 수집이 안 되거나 "
        "차단으로 실패할 확률이 높아요. 아래 가이드대로 발급받고 "
        "**Streamlit Cloud Secrets** 또는 **로컬 `.env`** 에 저장하세요."
    )

    # 각 키 상태 — 에러 안전하게 조회 (st.secrets 미존재 대비)
    def _safe_call(fn):
        try:
            return bool(fn())
        except Exception:  # noqa: BLE001
            return False

    status_items = [
        ("🧠 Anthropic", _safe_call(get_anthropic_key)),
        ("✨ Gemini", _safe_call(get_gemini_key)),
        ("📺 YouTube API", _safe_call(get_youtube_key)),
        ("👽 Reddit", _safe_call(get_reddit_creds)),
        ("🟢 Naver", _safe_call(get_naver_creds)),
        ("🎬 ScrapeCreators", _safe_call(get_scrapecreators_key)),
    ]

    st.markdown("### 🔑 현재 키 상태")
    # 모바일 대비 3+2 분할
    for row in (status_items[:3], status_items[3:]):
        if not row:
            continue
        cols = st.columns(len(row))
        for i, (name, ok) in enumerate(row):
            with cols[i]:
                if ok:
                    st.success(f"✅ {name}")
                else:
                    st.error(f"❌ {name}")

    st.divider()

    # -----------------------------------------------------------------------
    # Anthropic
    # -----------------------------------------------------------------------
    with st.expander("🧠 ANTHROPIC_API_KEY — Claude AI 분석 (선택)", expanded=False):
        st.markdown(
            """
**사용 범위**
- 🤖 쇼츠 아이디어 AI 분석 (요약·해시태그·활용도 점수)
- 🧵 Threads 인기 포스트 수집
- 🎵 TikTok 트렌드 수집

> ℹ️ **Gemini API 키가 있으면 Anthropic 없이도 AI 분석이 가능합니다.**
> Anthropic 키가 있으면 Anthropic을 우선 사용합니다.

**키 형식**: `sk-ant-api03-XXXXXXXXX…` (약 108자)

### 📝 발급 단계 (3분)
1. <https://console.anthropic.com> 접속 → 계정 생성/로그인
2. 왼쪽 메뉴 **API Keys** → **Create Key**
3. 표시된 `sk-ant-api03-…` 키를 **즉시 복사** (창 닫으면 다시 못 봐요)

### ☁️ Streamlit Cloud에 등록
```toml
ANTHROPIC_API_KEY = "sk-ant-api03-XXXXX..."
```

### 💻 로컬 `.env`
```
ANTHROPIC_API_KEY=sk-ant-api03-XXXXX...
```
            """
        )

    # -----------------------------------------------------------------------
    # Gemini
    # -----------------------------------------------------------------------
    with st.expander("✨ GEMINI_API_KEY — Google Gemini AI 분석 (Anthropic 대체)", expanded=True):
        st.markdown(
            """
**사용 범위**
- 🤖 쇼츠 아이디어 AI 분석 (Anthropic Claude 대체)
- Anthropic API 키가 없을 때 자동으로 Gemini를 사용

> ⚠️ **Google AI Studio 키 ≠ YouTube API 키**
> Google AI Studio (`aistudio.google.com`) 에서 발급한 키가 바로 이 Gemini 키입니다.
> YouTube 수집에는 별도의 `YOUTUBE_API_KEY`가 필요합니다.

**키 형식**: `AIzaSy...` (39자) — Google AI Studio에서 발급

### 📝 발급 단계 (1분)
1. <https://aistudio.google.com> 접속 → Google 로그인
2. 상단 **Get API key** 또는 왼쪽 메뉴 **API keys** 클릭
3. **Create API key** → 키 복사 (`AIzaSy…`)

💡 **무료 할당량**: Gemini 2.0 Flash 기준 분당 15회 / 일 1,500회 (이 앱에 충분)

### ☁️ Streamlit Cloud에 등록
```toml
GEMINI_API_KEY = "AIzaSy..."
```

### 💻 로컬 `.env`
```
GEMINI_API_KEY=AIzaSy...
```

> 💡 `GOOGLE_API_KEY` 라는 이름으로 저장해도 자동 인식됩니다.
            """
        )

    # -----------------------------------------------------------------------
    # YouTube Data API
    # -----------------------------------------------------------------------
    with st.expander("📺 YOUTUBE_API_KEY — YouTube Data API v3 (YouTube 수집 전용)", expanded=True):
        st.markdown(
            """
**사용 범위**
- 📺 YouTube 한국 인기 급상승 영상 수집 (공식 API, 가장 정확)
- 영상별 조회수·좋아요·댓글수 수집

> ⚠️ **이 키는 YouTube 수집 전용입니다. AI 분석에는 사용되지 않습니다.**
> AI 분석에는 `GEMINI_API_KEY` 또는 `ANTHROPIC_API_KEY`를 사용하세요.

**키 형식**: `AIzaSy...` (39자) — Google Cloud Console에서 발급
(AI Studio 키와 형식은 같지만 **다른 키**입니다)

### 📝 발급 단계 (5분)
1. <https://console.cloud.google.com> 접속 (Google 계정 필요)
2. 상단 드롭다운 → **New Project** → 프로젝트 생성
3. 왼쪽 메뉴 → **APIs & Services → Library**
4. 검색창에 `YouTube Data API v3` → 클릭 → **Enable**
5. 왼쪽 메뉴 → **APIs & Services → Credentials**
6. **+ CREATE CREDENTIALS → API key** 클릭 → 키 복사
7. (권장) 키 **Edit** → **API restrictions: YouTube Data API v3** 만 체크 → Save

💡 YouTube Data API는 **무료 할당량 하루 10,000 유닛**
→ 이 앱 기준 수백~수천 번 호출 가능

### ☁️ Streamlit Cloud에 등록
```toml
YOUTUBE_API_KEY = "AIzaSy..."
```

### 💻 로컬 `.env`
```
YOUTUBE_API_KEY=AIzaSy...
```
            """
        )

    # -----------------------------------------------------------------------
    # Reddit
    # -----------------------------------------------------------------------
    with st.expander("👽 REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET — Reddit OAuth", expanded=True):
        st.markdown(
            """
**사용 범위**
- 🌐 Reddit r/popular + r/korea + r/hanguk 수집 (OAuth 인증)
- 공개 `.json` 엔드포인트는 Streamlit Cloud 공용 IP에서 자주 차단됨
- OAuth 인증 시 **분당 60회 → 600회**로 레이트 리밋 10배 상승

**키 형식**: `client_id` (14자), `client_secret` (27자) — 무료

### 📝 발급 단계 (3분)
1. <https://www.reddit.com/prefs/apps> 접속 (Reddit 계정 필요)
2. 맨 아래 **create another app…** 또는 **create app...** 클릭
3. 폼 작성:
   - **name**: `shorts-collector`
   - **type**: 🔘 **script** 선택 (중요)
   - **description**: (비워둬도 됨)
   - **about url**: (비워둬도 됨)
   - **redirect uri**: `http://localhost:8080` (쓰이진 않지만 필수)
4. **create app** 클릭
5. 생성된 앱에서:
   - 앱 이름 바로 아래 **`personal use script`** 글자 위의 문자열 = `CLIENT_ID`
   - **`secret`** 옆의 문자열 = `CLIENT_SECRET`

### ☁️ Streamlit Cloud에 등록
```toml
REDDIT_CLIENT_ID = "xxxxxxxxxxxxxx"
REDDIT_CLIENT_SECRET = "xxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

### 💻 로컬 `.env`
```
REDDIT_CLIENT_ID=xxxxxxxxxxxxxx
REDDIT_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxx
```
            """
        )

    # -----------------------------------------------------------------------
    # Naver
    # -----------------------------------------------------------------------
    with st.expander("🟢 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET — 네이버 개발자 API", expanded=True):
        st.markdown(
            """
**사용 범위**
- 📰 네이버 뉴스 검색 API (오늘의 핫 이슈 실시간 수집)
- HTML 스크래핑 대비 훨씬 안정적 (차단 없음)

**키 형식**: `CLIENT_ID` (20자), `CLIENT_SECRET` (10자) — 무료

### 📝 발급 단계 (5분)
1. <https://developers.naver.com/apps/#/register> 접속 (네이버 로그인 필요)
2. **애플리케이션 이름**: `shorts-collector`
3. **사용 API 선택**: **검색** (Search) 체크 ✅
4. **환경 추가**:
   - 🔘 **WEB 설정** 선택
   - 서비스 URL: `http://localhost:8501` (Streamlit 배포 URL로 바꿔도 OK)
5. **이용약관 동의** → **등록** 클릭
6. 생성된 앱 상세 화면에 표시됨:
   - **Client ID** 복사
   - **Client Secret** → **보기** 클릭 후 복사

💡 **하루 25,000회** 무료 호출 제공

### ☁️ Streamlit Cloud에 등록
```toml
NAVER_CLIENT_ID = "XXXXXXXXXXXXXXXXXXXX"
NAVER_CLIENT_SECRET = "XXXXXXXXXX"
```

### 💻 로컬 `.env`
```
NAVER_CLIENT_ID=XXXXXXXXXXXXXXXXXXXX
NAVER_CLIENT_SECRET=XXXXXXXXXX
```
            """
        )

    # -----------------------------------------------------------------------
    # ScrapeCreators (선택)
    # -----------------------------------------------------------------------
    with st.expander("✨ SCRAPECREATORS_API_KEY — Threads/TikTok 정식 데이터 (유료, 선택)", expanded=False):
        st.markdown(
            """
**사용 범위**
- 🧵 Threads 실제 포스트 / 좋아요 수 / 작성자
- 🎵 TikTok 실제 영상 / 조회수 / 해시태그

> ⚠️ **이 키가 없으면** Threads/TikTok은 Anthropic 기반 AI 추정으로 동작 (정확도 낮음)

**키 형식**: `sk_…`

### 📝 발급 단계
1. <https://scrapecreators.com> 접속
2. **Sign Up** → 이메일 가입
3. Dashboard → **API Keys** → **Generate**
4. 복사

💡 **무료 플랜: 월 100회 호출** / 유료 플랜 $29~

### ☁️ Streamlit Cloud에 등록
```toml
SCRAPECREATORS_API_KEY = "sk_..."
```

### 💻 로컬 `.env`
```
SCRAPECREATORS_API_KEY=sk_...
```
            """
        )

    st.divider()

    # -----------------------------------------------------------------------
    # 수집 동작 원리
    # -----------------------------------------------------------------------
    st.subheader("⚙️ 수집 동작 원리")
    st.markdown(
        """
**캐시 없음 (항상 재수집)**
- 수집 버튼을 누를 때마다 **캐시 없이 모든 플랫폼을 새로 호출**
- 장점: 항상 최신 데이터 / 단점: 버튼 연타 시 사이트에 부담 → 약간 기다려주세요

**실패 자동 재시도**
- 스크래퍼가 실패하면 최대 **2회 재시도** (지수 백오프: 1s → 2s)
- 각 시도마다 User-Agent 로테이션 + curl_cffi fallback
- 일시적 레이트 리미팅 / 네트워크 변동에 자동 대응

**'됐다 안됐다' 남은 원인**
1. **Streamlit Cloud 공용 IP** — 일부 사이트가 특정 IP 대역 차단
2. **curl_cffi TLS fingerprint 변동** — 재시도마다 미세하게 다름
3. **사이트 HTML A/B 테스트** — 일부 사용자에게 다른 HTML 제공

**대처 순서**
1. 수집 건수 슬라이더 줄여서 (5건) 재시도
2. 잠시 후 (1-5분) 재시도 (사이트 레이트 리미팅 해제 대기)
3. 로컬 PC에서 실행 (공용 IP 블랙리스트 회피)
        """
    )

    st.divider()

    # -----------------------------------------------------------------------
    # 수집 대상 URL (투명성)
    # -----------------------------------------------------------------------
    st.subheader("🔍 수집 대상 URL (데이터 출처)")
    st.caption(
        "각 플랫폼이 **실제로 어느 페이지에서** 글을 가져오는지 확인하세요. "
        "링크를 직접 열어보고 '인기글'인지 검증할 수 있습니다."
    )

    from scrapers import SCRAPER_CLASSES
    url_rows = []
    for reg in SCRAPER_REGISTRY:
        key = reg["key"]
        cls = SCRAPER_CLASSES.get(key)
        if cls is None:
            continue
        base_url = getattr(cls, "base_url", "")
        extra = ""
        if key == "ppomppu":
            extra = " + 자유게시판 베스트"
        elif key == "reddit":
            extra = " + r/korea, r/hanguk"
        elif key == "youtube_trends":
            extra = " (또는 YouTube Data API)"
        elif key == "naver_trends":
            extra = " (또는 Naver Open API)"
        url_rows.append({
            "그룹": "🇰🇷" if reg["group"] == "kr" else "🌍",
            "플랫폼": reg["label"],
            "수집 페이지": base_url + extra,
        })

    import pandas as _pd
    url_df = _pd.DataFrame(url_rows)
    try:
        st.dataframe(
            url_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "수집 페이지": st.column_config.LinkColumn(
                    "수집 페이지 (클릭해서 원본 확인)",
                ),
            },
        )
    except Exception as _df_exc:  # noqa: BLE001
        st.warning(f"데이터프레임 표시 실패: {_df_exc}")
        st.table(url_df)

    st.info(
        "💡 **'메타없음' 배지가 많이 보이면** 해당 사이트가 차단·레이아웃 변경됐을 가능성이 높아요. "
        "위 API 키들을 설정하면 차단 문제 대부분 해결됩니다."
    )


# ===== ⬆ 맨 위로 가기 플로팅 버튼 (모든 페이지 공통, 항상 우측 하단 표시) =====
st.markdown(
    '<a href="#page-top" class="back-to-top" title="맨 위로">⬆</a>',
    unsafe_allow_html=True,
)
