"""🎬 쇼츠 소재 수집기 — Streamlit 메인 앱."""
from __future__ import annotations

import logging
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
    initial_sidebar_state="expanded",
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
    success, failed = [], []

    def _run(key: str) -> tuple[str, list[dict]]:
        scraper = get_scraper(key)
        if scraper is None:
            return key, []
        try:
            return key, scraper.get_trending(limit=limit)
        except Exception:  # noqa: BLE001
            return key, []

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_run, k): k for k in keys}
        for fut in as_completed(futures):
            key, items = fut.result()
            if items:
                success.append(key)
                results.extend(items)
            else:
                failed.append(key)

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
# 사이드바
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("🎬 쇼츠 소재 수집기")
    st.caption("국내외 18개 인기 플랫폼에서 바이럴 콘텐츠 수집")

    # --- 플랫폼 선택 ---
    st.subheader("🇰🇷 국내 커뮤니티")
    kr_all = st.checkbox("전체 선택/해제", value=False, key="kr_all")
    kr_keys: list[str] = []
    for item in SCRAPER_REGISTRY:
        if item["group"] != "kr":
            continue
        default = kr_all if st.session_state.get("kr_all_applied") != st.session_state.kr_all else item["default"]
        # "전체 선택/해제" 토글 ON이면 체크박스 기본값을 True로 밀어줌
        val = st.checkbox(
            item["label"],
            value=kr_all or item["default"],
            key=f"chk_{item['key']}",
        )
        if val:
            kr_keys.append(item["key"])

    st.divider()
    st.subheader("🌍 해외 플랫폼")
    gl_keys: list[str] = []
    for item in SCRAPER_REGISTRY:
        if item["group"] != "global":
            continue
        val = st.checkbox(
            item["label"],
            value=item["default"],
            key=f"chk_{item['key']}",
        )
        if val:
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

    badge = (
        f'<span class="platform-badge" style="background:{color};">{source}</span>'
        f'<span class="category-tag">{category}</span>'
    )
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
tab_results, tab_saved, tab_analysis = st.tabs(
    ["📊 수집 결과", "★ 저장된 소재", "📈 트렌드 분석"]
)

# ===== 📊 수집 결과 =====
with tab_results:
    summary = st.session_state.last_summary
    if summary:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("총 수집", f"{summary['total']}건")
        c2.metric("소요 시간", f"{summary['elapsed']:.1f}s")
        c3.metric("성공 플랫폼", f"{len(summary['success'])}")
        c4.metric("실패 플랫폼", f"{len(summary['failed'])}")

        if summary["failed"]:
            failed_labels = []
            for k in summary["failed"]:
                for r in SCRAPER_REGISTRY:
                    if r["key"] == k:
                        failed_labels.append(r["label"])
                        break
            st.warning(
                f"⚠️ 수집 실패한 플랫폼: {', '.join(failed_labels)}  "
                "(차단/레이아웃 변경 가능성 — 회사망에서는 일부 사이트가 막혀있을 수 있어요)"
            )

    results = st.session_state.results
    if not results:
        st.info("👈 왼쪽 사이드바에서 플랫폼을 선택하고 '인기글 수집' 버튼을 눌러보세요.")
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
