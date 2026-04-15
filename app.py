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
    CACHE_TTL,
    CATEGORIES,
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
    initial_sidebar_state="auto",  # 모바일에서는 자동으로 접힘
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
        color: #111827;
        line-height: 1.35;
    }
    .item-meta {
        font-size: 0.8rem;
        color: #6B7280;
        margin-bottom: 4px;
    }
    .stars { color: #F59E0B; }

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
        /* 탭 라벨 compact */
        button[data-baseweb="tab"] {
            padding-left: 10px !important;
            padding-right: 10px !important;
            font-size: 0.9rem !important;
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
@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def collect_from(keys: tuple[str, ...], limit: int) -> dict:
    """선택된 플랫폼에서 인기글 수집 (캐시)."""
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
                   platforms: list[str], sort: str) -> list[dict]:
    out = list(results)
    if category and category != "전체":
        out = [r for r in out if r.get("category") == category]
    if keyword:
        kw = keyword.strip().lower()
        out = [r for r in out
               if kw in (r.get("title", "") + " " + r.get("summary", "")).lower()]
    if platforms:
        out = [r for r in out if r.get("source") in platforms]

    key = {"추천순": "score", "조회순": "views", "댓글순": "comments"}.get(sort)
    if key:
        out.sort(key=lambda r: r.get(key, 0) or 0, reverse=True)
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


# ---------------------------------------------------------------------------
# 사이드바
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("🎬 쇼츠 소재 수집기")
    st.caption("국내외 18개 인기 플랫폼에서 바이럴 콘텐츠 수집")

    # --- 플랫폼 선택 ---
    st.subheader("🇰🇷 국내 커뮤니티")
    st.checkbox(
        "전체 선택/해제",
        key="kr_all",
        on_change=_toggle_group,
        args=("kr",),
    )
    kr_keys: list[str] = []
    for item in SCRAPER_REGISTRY:
        if item["group"] != "kr":
            continue
        if st.checkbox(item["label"], key=f"chk_{item['key']}"):
            kr_keys.append(item["key"])

    st.divider()
    st.subheader("🌍 해외 플랫폼")
    st.checkbox(
        "전체 선택/해제",
        key="global_all",
        on_change=_toggle_group,
        args=("global",),
    )
    gl_keys: list[str] = []
    for item in SCRAPER_REGISTRY:
        if item["group"] != "global":
            continue
        if st.checkbox(item["label"], key=f"chk_{item['key']}"):
            gl_keys.append(item["key"])

    st.divider()
    st.subheader("🔎 필터")
    genre = st.selectbox("장르", CATEGORIES, index=0)
    keyword = st.text_input("추가 키워드 (제목/요약 검색)", "")
    per_site_limit = st.slider("사이트당 수집 건수", 5, 20, MAX_ITEMS_PER_SITE)

    st.divider()
    ai_on = st.toggle(
        "🤖 AI 분석 ON",
        value=analyzer.is_available(),
        help="ANTHROPIC_API_KEY 필요",
    )
    if ai_on and not analyzer.is_available():
        st.warning(".env에 ANTHROPIC_API_KEY가 없어요")

    run_btn = st.button("🔍 인기글 수집", type="primary", use_container_width=True)

    st.divider()
    st.caption("⚙️ API 키 / 데이터 출처는 **메인 화면의 '설정' 탭**을 확인하세요.")


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

        # AI 분석 (배치)
        if ai_on and items and analyzer.is_available():
            with st.spinner("🤖 AI가 쇼츠 아이디어를 분석하는 중…"):
                items = analyzer.analyze_batch(items)

        st.session_state.results = items
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

    badge_parts = [
        f'<span class="platform-badge" style="background:{color};">{source}</span>',
        f'<span class="category-tag">{category}</span>',
    ]
    if not has_meta:
        badge_parts.append(
            '<span class="category-tag" style="background:#FEF3C7;color:#92400E;" '
            'title="조회/추천/댓글 수치를 못 가져와서 실제 인기글 여부가 불확실해요">'
            '⚠️ 메타없음</span>'
        )
    badge = "".join(badge_parts)

    title = item.get("title", "(제목 없음)")
    engagement = item.get("engagement", "")
    url = item.get("url", "")

    with st.container(border=True):
        st.markdown(badge, unsafe_allow_html=True)
        if url:
            st.markdown(f'<div class="item-title"><a href="{url}" target="_blank">{title}</a></div>',
                        unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="item-title">{title}</div>', unsafe_allow_html=True)
        if engagement:
            st.markdown(f'<div class="item-meta">📊 {engagement}</div>', unsafe_allow_html=True)
        elif not has_meta:
            st.markdown(
                '<div class="item-meta" style="color:#92400E;">'
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
            # 개별 분석 버튼
            if st.button("🤖 이 항목만 AI 분석", key=f"{key_prefix}_single"):
                with st.spinner("분석 중…"):
                    analyzed = analyzer.analyze_single(item)
                    # 세션 결과 갱신
                    for i, r in enumerate(st.session_state.results):
                        if r.get("url") == item.get("url"):
                            st.session_state.results[i] = analyzed
                            break
                st.rerun()

        cols = st.columns([1, 1, 3])
        if show_save:
            already = storage.is_saved(url)
            if already:
                cols[0].markdown("✅ 저장됨")
            else:
                if cols[0].button("★ 저장", key=f"{key_prefix}_save"):
                    if storage.add_item(item):
                        st.toast("저장됨", icon="⭐")
                        st.rerun()
        if url:
            cols[1].markdown(f"[🔗 원문]({url})")


# ---------------------------------------------------------------------------
# 메인 — 탭 구성
# ---------------------------------------------------------------------------
tab_results, tab_saved, tab_analysis, tab_settings = st.tabs(
    ["📊 수집 결과", "★ 저장된 소재", "📈 트렌드 분석", "⚙️ 설정"]
)

# ===== 📊 수집 결과 =====
with tab_results:
    summary = st.session_state.last_summary
    if summary:
        # 메타데이터 있는 항목 비율 (인기글 진위 판단)
        with_meta = sum(
            1 for r in st.session_state.results
            if any(int(r.get(k, 0) or 0) > 0 for k in ("score", "views", "comments"))
        )
        total_items = len(st.session_state.results) or 1
        meta_pct = int(with_meta / total_items * 100)

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("총 수집", f"{summary['total']}건")
        c2.metric("소요 시간", f"{summary['elapsed']:.1f}s")
        c3.metric("성공 플랫폼", f"{len(summary['success'])}")
        c4.metric("실패 플랫폼", f"{len(summary['failed'])}")
        c5.metric(
            "메타 보유율",
            f"{meta_pct}%",
            help="조회/추천/댓글 수치가 정상 파싱된 항목 비율. "
                 "낮으면 스크래퍼가 실제 인기글 페이지가 아닌 것을 수집했을 가능성.",
        )

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
                    "Reddit · Hacker News · YouTube 같은 공개 API 기반 소스만 선택"
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
                    "💡 자주 보이는 원인: `HTTP 403/429` (봇 차단) · "
                    "`연결 실패` (사이트 다운 또는 DNS) · "
                    "`파싱 결과 0건` (사이트 레이아웃 변경)"
                )

    results = st.session_state.results
    if not results:
        st.info(
            "사이드바에서 플랫폼을 선택하고 **'인기글 수집'** 버튼을 눌러보세요.\n\n"
            "📱 모바일에서는 왼쪽 위의 **>** (또는 ☰) 아이콘을 눌러 사이드바를 열어주세요."
        )
    else:
        all_sources = sorted({r.get("source", "") for r in results if r.get("source")})
        fc1, fc2 = st.columns([3, 1])
        selected_platforms = fc1.multiselect(
            "플랫폼 필터",
            options=all_sources,
            default=all_sources,
        )
        sort_by = fc2.selectbox("정렬", ["추천순", "조회순", "댓글순", "최신순"])

        filtered = filter_results(
            results,
            category=genre,
            keyword=keyword,
            platforms=selected_platforms,
            sort=sort_by,
        )

        st.caption(f"필터링 결과: {len(filtered)}건")

        # 카드 3열 그리드
        cols = st.columns(3)
        for idx, item in enumerate(filtered):
            with cols[idx % 3]:
                render_card(item, key_prefix=f"res_{idx}")

# ===== ★ 저장된 소재 =====
with tab_saved:
    saved_items = storage.load_all()
    sc1, sc2, sc3 = st.columns([2, 1, 1])
    sc1.markdown(f"### 저장된 소재 ({len(saved_items)}건)")

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
                        st.caption(f"💾 저장: {item['saved_at'][:19]}")

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
        st.info("아직 저장된 소재가 없어요. 수집 결과 탭에서 ★ 버튼으로 저장해보세요.")

# ===== 📈 트렌드 분석 =====
with tab_analysis:
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

            text = " ".join(r.get("title", "") for r in results)
            # 한글 폰트 자동 탐색
            import glob
            candidates = (
                glob.glob("/usr/share/fonts/**/*Nanum*.ttf", recursive=True)
                + glob.glob("/usr/share/fonts/**/NotoSansCJK*.ttc", recursive=True)
                + glob.glob("/System/Library/Fonts/**/AppleSDGothicNeo*", recursive=True)
            )
            font_path = candidates[0] if candidates else None

            wc = WordCloud(
                font_path=font_path,
                background_color="white",
                width=800,
                height=400,
                max_words=80,
            )
            img = wc.generate(text)
            fig, ax = plt.subplots(figsize=(10, 5))
            ax.imshow(img, interpolation="bilinear")
            ax.axis("off")
            st.pyplot(fig)
            if not font_path:
                st.caption("※ 한글 폰트가 없어 한글이 깨질 수 있어요. NanumGothic 설치 권장.")
        except Exception as exc:  # noqa: BLE001
            st.warning(f"워드클라우드 생성 실패: {exc}")


# ===== ⚙️ 설정 =====
with tab_settings:
    st.header("⚙️ 설정")

    # -----------------------------------------------------------------------
    # 섹션 1) API 키 관리
    # -----------------------------------------------------------------------
    st.subheader("🔑 API 키 관리")

    current_key = os.getenv("ANTHROPIC_API_KEY", "")
    masked = (
        f"{current_key[:12]}…{current_key[-4:]}"
        if current_key and len(current_key) > 20
        else ("입력됨" if current_key else "미설정")
    )

    col_k1, col_k2 = st.columns([3, 1])
    with col_k1:
        if current_key:
            st.success(f"✅ ANTHROPIC_API_KEY 설정됨 ({masked})")
        else:
            st.error("❌ ANTHROPIC_API_KEY 미설정 — 아래에 입력하세요")

    with col_k2:
        if current_key and st.button("🗑️ 키 제거", use_container_width=True):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            st.rerun()

    with st.form("api_key_form", clear_on_submit=True):
        new_key = st.text_input(
            "ANTHROPIC_API_KEY 입력",
            type="password",
            placeholder="sk-ant-api03-XXXXXXXXXXXX...",
            help="형식: sk-ant-api03로 시작하는 약 108자 문자열",
        )
        submitted = st.form_submit_button("💾 저장", type="primary")
        if submitted:
            new_key = (new_key or "").strip()
            if not new_key:
                st.warning("키가 비어있어요.")
            elif not new_key.startswith("sk-ant-"):
                st.error("형식이 올바르지 않아요. `sk-ant-`로 시작해야 합니다.")
            else:
                os.environ["ANTHROPIC_API_KEY"] = new_key
                st.success("✅ 저장 완료! AI 분석 기능이 활성화됩니다. "
                           "(이 세션이 끝나면 사라지니, 영구 저장은 아래 방법 참고)")
                st.rerun()

    st.divider()

    # -----------------------------------------------------------------------
    # 섹션 2) ANTHROPIC API 키 발급 방법
    # -----------------------------------------------------------------------
    st.subheader("📝 ANTHROPIC API 키 발급 및 영구 설정")

    st.markdown(
        """
### 🎯 발급 방법 (3분 소요)
1. <https://console.anthropic.com> 접속 → 계정 생성/로그인
2. 왼쪽 메뉴 → **API Keys** 클릭
3. 오른쪽 상단 **Create Key** 버튼 클릭
4. 키 이름 입력 (예: `shorts-collector`) → **Create Key**
5. 표시된 키(`sk-ant-api03-…`)를 **즉시 복사** — 창 닫으면 다시 못 봐요
6. 위 입력창에 붙여넣기 → 저장

> 💡 가입 직후 **무료 크레딧 $5** 제공 (이 앱 용도로는 수천 번 분석 가능)

---

### 🌐 Streamlit Cloud 배포 시 영구 설정

**위 입력창에 저장한 키는 브라우저 세션에서만 유효**합니다.
배포 후에도 계속 쓰려면 다음 중 하나를 설정하세요.

#### 방법 A — Streamlit Cloud Secrets (권장)
1. Streamlit Cloud 대시보드 → 배포된 앱 → **⋮ → Settings → Secrets**
2. 아래 한 줄 붙여넣기:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-api03-XXXXX..."
   ```
3. **Save** → 앱 자동 재시작 → 영구 반영

#### 방법 B — 로컬 `.env` 파일
프로젝트 루트에 `.env` 파일 만들기:
```
ANTHROPIC_API_KEY=sk-ant-api03-XXXXX...
```
→ `streamlit run app.py` 실행 시 자동 로드됨

---

### 🔒 보안 주의
- `.env` 파일은 이미 `.gitignore`에 포함 → 실수로 커밋 안 됨
- 키 유출 의심 시 즉시 [console.anthropic.com](https://console.anthropic.com) → API Keys → **Revoke**
        """
    )

    st.divider()

    # -----------------------------------------------------------------------
    # 섹션 3) 수집 대상 URL (투명성)
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
        url_rows.append({
            "그룹": "🇰🇷" if reg["group"] == "kr" else "🌍",
            "플랫폼": reg["label"],
            "수집 페이지": base_url + extra,
        })

    import pandas as _pd
    url_df = _pd.DataFrame(url_rows)
    st.dataframe(
        url_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "수집 페이지": st.column_config.LinkColumn(
                "수집 페이지 (클릭해서 원본 확인)",
                display_text=r"https?://([^/]+)(/.*)?",
            ),
        },
    )

    st.info(
        "💡 **'메타없음' 배지가 많이 보이면** 해당 사이트가 차단·레이아웃 변경됐을 가능성이 높아요. "
        "위 링크를 직접 열어보고 실제 페이지와 수집 결과를 비교해보세요."
    )

    st.divider()

    # -----------------------------------------------------------------------
    # 섹션 4) 추후 확장 시 쓸 수 있는 API 키 (선택)
    # -----------------------------------------------------------------------
    with st.expander("💡 추후 확장 시 쓸 수 있는 (현재 미사용) 선택 API 키"):
        st.markdown(
            """
| 키 이름 | 용도 | 형식 예 | 발급처 |
|--------|------|--------|--------|
| `YOUTUBE_API_KEY` | YouTube Data API v3 (RSS 대체) | `AIzaSy…` (39자) | Google Cloud Console |
| `REDDIT_CLIENT_ID` / `REDDIT_SECRET` | Reddit OAuth (레이트 상향) | 무료 등록 | reddit.com/prefs/apps |
| `SCRAPECREATORS_API_KEY` | Threads/TikTok 정식 API | `sk_…` | scrapecreators.com |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | 네이버 검색 트렌드 API | 무료 | developers.naver.com |
            """
        )
