"""뽐뿌 핫딜 HOT 스크래퍼.

URL 전략:
1) 모바일 HOT 페이지 (m.ppomppu.co.kr/new/hot.php) — HTML 단순, 인기만
2) 데스크톱 HOT (/hot.php) — fallback
3) 레거시 zboard — fallback

모바일 페이지는 li 기반, 데스크톱은 tr 기반이므로 둘 다 파싱 가능하게 구현.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from .base import BaseScraper


class PpomppuScraper(BaseScraper):
    source = "뽐뿌"
    # 모바일 HOT — 가장 안정적
    base_url = "https://m.ppomppu.co.kr/new/hot.php"
    category = "핫딜"
    encoding = "euc-kr"

    FALLBACK_URLS = [
        "https://www.ppomppu.co.kr/hot.php",
        "https://www.ppomppu.co.kr/zboard/zboard.php?id=ppomppu",
    ]

    FREE_BEST_URL = (
        "https://www.ppomppu.co.kr/zboard/zboard.php"
        "?id=freeboard&page=1&category=999"
    )

    # --- 메뉴/카테고리/정책 텍스트 (수집 결과에서 제외) ---
    MENU_TEXTS = {
        # 게시판 이름
        "뽐뿌", "자유게시판", "뽐뿌게시판", "이벤트게시판",
        "쿠폰게시판", "이것저것공유", "휴대폰뽐뿌", "가전뽐뿌", "컴퓨터뽐뿌",
        "뽐뿌4", "뽐뿌5", "뽐뿌6", "뽐뿌7", "뽐뿌8",
        # 스폰서 / 광고 게시판 — 이름 바뀔 가능성 대비 여러 표현
        "뽐뿌스폰서", "뽐뿌 스폰서", "스폰서 뽐뿌", "스폰서뽐뿌",
        "광고뽐뿌", "광고 뽐뿌", "핫딜스폰서", "핫딜 스폰서",
        # 카테고리 탭
        "오늘의특가", "오늘특가", "최신글", "인기글", "인기순", "최신순",
        "전체", "랭킹", "쇼핑", "HOT", "BEST", "NEW",
        # 네비게이션
        "메인", "홈", "설정", "로그인", "회원가입", "마이페이지",
        "구매가이드",
        # 법적/정책/고객센터 (footer)
        "개인정보처리방침", "개인정보취급방침", "청소년보호정책",
        "이용약관", "책임의 한계", "책임한계", "저작권정책",
        "광고/제휴", "광고·제휴", "광고ㆍ제휴", "광고문의", "제휴문의",
        "불법촬영물등 신고", "불법촬영물 신고", "신고안내",
        "자주묻는질문", "FAQ", "고객센터", "공지사항",
        "회사소개", "사이트맵", "이메일무단수집거부",
    }

    # --- 통신/인터넷/렌탈/약정 등 광고 배너 (제목에 부분일치만 돼도 제외) ---
    AD_TITLE_SUBSTRINGS = (
        # 휴대폰/통신
        "휴대폰 개통", "휴대폰개통", "휴대폰 가입", "휴대폰가입",
        "휴대폰 성지", "휴대폰성지", "휴대폰 보조금", "휴대폰보조금",
        "통신비 절약", "통신비절약", "통신사 변경", "통신사변경",
        "알뜰폰", "요금제 추천", "요금제추천",
        # 인터넷
        "인터넷 신청", "인터넷신청", "인터넷 가입", "인터넷가입",
        "인터넷 약정", "인터넷약정", "인터넷 변경", "인터넷변경",
        "인터넷 설치", "인터넷설치", "인터넷+TV", "결합상품",
        # 렌탈/렌털/구독
        "렌탈 신청", "렌탈신청", "렌털 신청", "렌털신청",
        "렌탈 문의", "렌탈문의", "렌털 문의", "렌털문의",
        "정수기 렌탈", "정수기렌탈", "공기청정기 렌탈",
        "구독 서비스", "구독서비스",
        # 일반 광고
        "상담 신청", "상담신청", "상담 받으세요", "상담받으세요",
        "방문 상담", "방문상담", "전화 상담", "전화상담",
        "할부 가능", "약정 할인", "무료 가입", "무료가입",
        "캐시백", "현금 지급", "현금지급",
    )

    # --- 뽐뿌 상담실/쇼핑뽐뿌 카테고리 prefix ([렌탈상담] 처럼 앞머리) ---
    # 이런 카테고리에서 온 글은 전부 광고·영업 글이므로 제외
    AD_CATEGORY_PREFIXES = (
        "[렌탈상담]", "[보험상담]", "[대출상담]", "[휴대폰상담]",
        "[에어컨상담]", "[보안상담]", "[카드상담]", "[법률상담]",
        "[인터넷가입상담]", "[가전견적상담]", "[신차견적상담]", "[PC견적상담]",
        "[상담실]", "[쇼핑뽐뿌]", "[쇼핑몰뽐뿌]", "[핫딜광장]",
        # 뽐뿌스폰서 — 명시적 광고 섹션
        "[뽐뿌스폰서]", "[뽐뿌 스폰서]", "[스폰서]", "[스폰서뽐뿌]",
        "[광고뽐뿌]", "[광고]", "[AD뽐뿌]", "[핫딜스폰서]",
        "뽐뿌스폰서", "뽐뿌 스폰서", "스폰서뽐뿌", "광고뽐뿌",
        # 상담실 하위 게시판들
        "렌탈상담", "보험상담", "대출상담", "휴대폰상담",
        "에어컨상담", "보안상담", "카드상담", "법률상담",
        "인터넷가입상담", "가전견적상담", "신차견적상담", "PC견적상담",
    )

    # ~상담 / ~상담실 같은 카테고리성 제목 정규식
    _CATEGORY_SUFFIX_RE = re.compile(
        r"^\s*\[?[가-힣A-Za-z0-9]{1,15}(?:상담|상담실|견적|포럼|장터)\]?\s*:?\s*"
    )

    def _is_ad_title(self, title: str) -> bool:
        """뽐뿌 특화 추가 광고 판정 (base의 _is_notice_or_ad 외에)."""
        if not title:
            return False
        t = title.strip()
        if t in self.MENU_TEXTS:
            return True
        for s in self.AD_TITLE_SUBSTRINGS:
            if s in t:
                return True
        # '[렌탈상담]' 같은 카테고리 prefix 시작
        for p in self.AD_CATEGORY_PREFIXES:
            if t.startswith(p):
                return True
        # '~상담', '~견적' 카테고리 label (20자 미만)
        if len(t) < 30 and self._CATEGORY_SUFFIX_RE.match(t):
            return True
        return False

    def parse(self, html: str) -> list[dict]:
        soup = self.soup(html)
        items: list[dict] = []

        # ---- 1차: 모바일 li 구조 ----
        for li in soup.select(
            "ul.contents_list li, ul.list-style li, "
            "div.contents li, section li"
        ):
            parsed = self._extract_mobile(li)
            if parsed:
                items.append(parsed)

        # ---- 2차: 데스크톱 tr 구조 ----
        if len(items) < 3:
            rows = soup.select(
                "tr.list0, tr.list1, tr.baseList, "
                "table.board_table tr, table#revolution_main_table tr"
            )
            for tr in rows:
                parsed = self._extract_from_tr(tr)
                if parsed:
                    items.append(parsed)

        # ---- 3차: 링크 휴리스틱 (모바일/데스크톱 둘 다 커버) ----
        if len(items) < 10:
            seen: set[str] = set(it.get("url", "") for it in items)
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if not re.search(r"view\.php.*no=\d+", href):
                    continue
                title = a.get_text(" ", strip=True)
                if not title or len(title) < 5:
                    continue
                if self._is_ad_title(title):
                    continue
                if href in seen:
                    continue
                seen.add(href)
                url = href if href.startswith("http") else urljoin(
                    "https://www.ppomppu.co.kr/", href.lstrip("./")
                )

                # 부모에서 메타 추출
                score = views = comments = 0
                parent = a.find_parent(["li", "tr", "div", "article"])
                if parent:
                    ptxt = parent.get_text(" ", strip=True)
                    m_v = re.search(r"(?:조회|views?|hit)[\s:]*([\d,]+)", ptxt, re.I)
                    m_s = re.search(r"(?:추천|좋아요|\u25B2)[\s:]*([\d,]+)", ptxt, re.I)
                    m_c = re.search(r"(?:댓글|reply|\(\d+\))[\s:]*([\d,]+)", ptxt, re.I)
                    if m_v: views = self.to_int(m_v.group(1))
                    if m_s: score = self.to_int(m_s.group(1))
                    if m_c: comments = self.to_int(m_c.group(1))

                items.append({
                    "title": title,
                    "url": url,
                    "score": score,
                    "views": views,
                    "comments": comments,
                    "engagement": self.format_engagement(
                        score=score, views=views, comments=comments
                    ),
                })
                if len(items) >= 80:
                    break

        # 최종 필터: _is_ad_title + URL에 no= 숫자 + 광고/통신 게시판 URL 제외
        _AD_BOARD_IDS = re.compile(
            r"id=(?:phone|mobile|telecom|internet|rental|"
            r"ppomppu4|ppomppu5|ppomppu6|ppomppu7|ppomppu8)",
            re.I,
        )

        def _ok(it: dict) -> bool:
            t = (it.get("title") or "").strip()
            if self._is_ad_title(t):
                return False
            u = it.get("url", "")
            if not re.search(r"no=\d+", u):
                return False
            if _AD_BOARD_IDS.search(u):
                return False
            return True
        items = [it for it in items if _ok(it)]
        return items

    def _extract_mobile(self, li) -> dict | None:
        """모바일 HOT 페이지의 li 하나에서 게시글 정보 추출."""
        # 공지 스킵
        cls = " ".join(li.get("class", [])).lower()
        if any(k in cls for k in ("notice", "noti", "top_notice", "ad")):
            return None
        if li.find("img", src=re.compile(r"notice|공지|icon_ad", re.I)):
            return None

        a = li.find("a", href=True)
        if not a:
            return None
        href = a["href"]
        # 게시글 URL 만 (view.php?id=xxx&no=숫자)
        if not re.search(r"view\.php.*no=\d+", href):
            return None

        # 제목: li 내 가장 긴 텍스트 블록
        title_el = (
            li.select_one(".title, .subject, .sbj, strong, h3, h4, p.title")
            or a
        )
        title = title_el.get_text(" ", strip=True)
        if not title or len(title) < 5:
            return None
        if self._is_ad_title(title):
            return None

        url = href if href.startswith("http") else urljoin(
            "https://www.ppomppu.co.kr/", href.lstrip("./")
        )

        # 메타
        score = views = comments = 0
        full_text = li.get_text(" ", strip=True)
        m_v = re.search(r"(?:조회|views?|hit)[\s:]*([\d,]+)", full_text, re.I)
        m_s = re.search(r"(?:추천|좋아요|\u25B2)[\s:]*([\d,]+)", full_text, re.I)
        m_c = re.search(r"(?:댓글|reply|\[(\d+)\])", full_text, re.I)
        if m_v: views = self.to_int(m_v.group(1))
        if m_s: score = self.to_int(m_s.group(1))
        if m_c: comments = self.to_int(m_c.group(1))

        return {
            "title": title,
            "url": url,
            "score": score,
            "views": views,
            "comments": comments,
            "engagement": self.format_engagement(score=score, views=views, comments=comments),
        }

    def _extract_from_tr(self, tr) -> dict | None:
        tr_classes = " ".join(tr.get("class", [])).lower()
        if any(k in tr_classes for k in ("notice", "noti", "board_notice", "top_notice")):
            return None
        if tr.find("img", src=re.compile(r"notice|공지", re.I)):
            return None

        a = tr.select_one(
            "a.baseList-title, font.list_title a, td.list_vspace a, "
            "a[href*='view.php'], a[href*='no=']"
        )
        if not a:
            a = tr.find("a", href=True)
        if not a:
            return None
        title = a.get_text(" ", strip=True)
        href = a.get("href") or ""
        if not title or not href or len(title) < 3:
            return None
        if self._is_ad_title(title):
            return None
        # URL이 view.php 포함이어야 게시글
        if "view.php" not in href and "no=" not in href:
            return None
        url = href if href.startswith("http") else urljoin(
            "https://www.ppomppu.co.kr/zboard/", href.lstrip("./")
        )

        score = views = comments = 0
        tds = tr.find_all("td")
        texts = [td.get_text(" ", strip=True) for td in tds]
        nums = [self.to_int(t) for t in texts if t and t.replace(",", "").replace("-", "0").isdigit()]
        nums = [n for n in nums if n]
        if len(nums) >= 2:
            score, views = nums[-2], nums[-1]
        cmt = tr.select_one("span.list_comment2, .baseList-c")
        if cmt:
            comments = self.to_int(cmt.get_text())

        return {
            "title": title,
            "url": url,
            "score": score,
            "views": views,
            "comments": comments,
            "engagement": self.format_engagement(score=score, views=views, comments=comments),
        }

    # ------------------------------------------------------------------
    def get_trending(self, limit: int = 10) -> list[dict]:
        """HOT 페이지(모바일) → fallback URL → 자유게시판 베스트 순서.
        필터링으로 많이 탈락되므로 각 페이지에서 넉넉히 가져옴 (limit*3)."""
        # 수집 목표를 넉넉히 — 필터 후에도 limit 채울 수 있게
        oversample = max(limit * 3, 30)
        half = limit  # 핫딜만으로 limit 채울 수 있게 시도

        # 1) HOT (모바일) 시도, 실패 시 fallback
        hot_deals = super().get_trending(limit=oversample)
        deal_error = self.last_error
        if not hot_deals:
            for fb_url in self.FALLBACK_URLS:
                try:
                    html = self.fetch(fb_url)
                    parsed = self.parse(html)
                    parsed = [it for it in parsed if not self._is_notice_or_ad(it)
                              and not self._is_ad_title(it.get("title", ""))]
                    if parsed:
                        hot_deals = [self._normalize(it) for it in parsed[:oversample]]
                        deal_error = ""
                        break
                except Exception as exc:  # noqa: BLE001
                    deal_error = f"{type(exc).__name__}: {str(exc)[:80]}"
        # 핫딜 너무 적으면 자유게시판도 가져옴
        for it in hot_deals:
            it["category"] = "핫딜"

        # 2) 자유게시판 베스트 — 핫딜이 limit에 못 미칠 때만
        free_items: list[dict] = []
        free_error = ""
        if len(hot_deals) < limit:
            try:
                html = self.fetch(self.FREE_BEST_URL)
                parsed = self.parse(html)
                parsed = [it for it in parsed if not self._is_notice_or_ad(it)
                          and not self._is_ad_title(it.get("title", ""))]
                need = limit - len(hot_deals)
                for it in parsed[:need]:
                    norm = self._normalize({**it, "category": "유머/밈"})
                    free_items.append(norm)
            except Exception as exc:  # noqa: BLE001
                free_error = f"{type(exc).__name__}: {str(exc)[:80]}"

        combined = (hot_deals + free_items)[:limit]
        if combined:
            self.last_error = ""
        else:
            self.last_error = deal_error or free_error or "HOT 수집 0건"
        return combined
