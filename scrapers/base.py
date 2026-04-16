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
    #: 스크래퍼별 타임아웃 오버라이드 (None이면 REQUEST_TIMEOUT 사용)
    scraper_timeout: int | None = None

    def __init__(self) -> None:
        # cloudscraper가 있으면 Cloudflare JS 챌린지 자동 해결 (더쿠/에펨 등)
        try:
            import cloudscraper
            self.session = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "mobile": False},
                delay=1,
            )
        except Exception:  # noqa: BLE001 — 미설치 또는 초기화 실패 시 fallback
            self.session = requests.Session()
        self.session.headers.update(self._default_headers())

        # curl_cffi 백업 세션 — TLS fingerprint를 실제 Chrome으로 위조해 403/430 돌파
        self._cffi_session = None
        try:
            from curl_cffi import requests as _cffi
            self._cffi_session = _cffi.Session(impersonate="chrome124")
        except Exception:  # noqa: BLE001 — 미설치 시 None으로 둠
            pass

        #: 마지막 수집에서 발생한 에러 메시지 (비어있으면 성공/미실행)
        self.last_error: str = ""

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------
    #: 서브클래스에서 커스텀 Referer 지정 가능 (봇 차단 우회)
    default_referer: str | None = None

    def _default_headers(self) -> dict[str, str]:
        """진짜 Chrome 요청처럼 보이도록 Sec-* 헤더 포함."""
        return {
            "User-Agent": random_user_agent(),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8,"
                "application/signed-exchange;v=b3;q=0.7"
            ),
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "max-age=0",
            "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="122", "Chromium";v="122"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Connection": "keep-alive",
        }

    #: fetch 실패 시 재시도 횟수 (지수 백오프)
    MAX_RETRIES: int = 2

    def fetch(self, url: str | None = None, *, params: dict | None = None,
              headers: dict | None = None) -> str:
        """HTTP GET. 실패 시 curl_cffi fallback + MAX_RETRIES 재시도."""
        target = url or self.base_url
        merged_headers_base = dict(self.session.headers)
        if headers:
            merged_headers_base.update(headers)

        last_exc: Exception | None = None
        response = None

        for attempt in range(self.MAX_RETRIES + 1):
            # 매 시도마다 User-Agent 로테이션 + Referer 재계산
            merged_headers = dict(merged_headers_base)
            merged_headers["User-Agent"] = random_user_agent()
            if self.default_referer:
                merged_headers.setdefault("Referer", self.default_referer)
            elif target:
                from urllib.parse import urlparse
                p = urlparse(target)
                if p.scheme and p.netloc:
                    merged_headers.setdefault("Referer", f"{p.scheme}://{p.netloc}/")

            _timeout = self.scraper_timeout if self.scraper_timeout is not None else REQUEST_TIMEOUT
            try:
                response = self.session.get(
                    target, params=params, headers=merged_headers,
                    timeout=_timeout,
                )
                response.raise_for_status()
                break  # 성공
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                # curl_cffi로 폴백 (같은 시도 내 2차 채널)
                if self._cffi_session is not None:
                    try:
                        response = self._cffi_session.get(
                            target, params=params, headers=merged_headers,
                            timeout=_timeout, impersonate="chrome124",
                        )
                        response.raise_for_status()
                        break  # curl_cffi 성공
                    except Exception as exc2:  # noqa: BLE001
                        last_exc = exc2
                # 재시도 대기 (지수 백오프 + 지터)
                if attempt < self.MAX_RETRIES:
                    import random as _rnd
                    backoff = (2 ** attempt) + _rnd.random()
                    logger.info(
                        "[%s] 시도 %d 실패 (%s), %.1fs 후 재시도",
                        self.source, attempt + 1, exc, backoff,
                    )
                    time.sleep(backoff)
                    continue
                # 재시도 한도 초과
                raise last_exc

        if self.encoding:
            # EUC-KR 등 비UTF-8 인코딩은 response.content를 직접 디코딩.
            # curl_cffi는 .encoding 할당을 예외 없이 조용히 무시하므로
            # try/except로는 감지 불가 → 무조건 content 기반으로 처리.
            try:
                time.sleep(REQUEST_DELAY)
                return response.content.decode(self.encoding, errors="replace")
            except Exception:  # noqa: BLE001
                try:
                    response.encoding = self.encoding
                except Exception:  # noqa: BLE001
                    pass
        else:
            try:
                response.encoding = response.apparent_encoding or "utf-8"
            except Exception:  # noqa: BLE001
                pass
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
        """HTML → BeautifulSoup. 파싱 전에 footer/header/nav/aside 영역을 제거해
        약관/정책/저작권/고객센터 같은 사이트 전역 링크가 수집되지 않게 한다."""
        soup = BeautifulSoup(html, "lxml")
        # 태그 기반 제거
        for tag_name in ("header", "footer", "nav", "aside"):
            for el in soup.find_all(tag_name):
                el.decompose()
        # 클래스/ID 기반 제거 — 실제 사이트에서 자주 쓰는 이름들
        selectors = (
            "#header", "#footer", "#nav", "#navbar", "#sidebar", "#aside",
            "#gnb", "#lnb", "#menu", "#topbar", "#bottom", "#quick",
            ".header", ".footer", ".nav", ".navbar", ".navigation",
            ".sidebar", ".aside", ".side", ".gnb", ".lnb", ".menu", ".topbar",
            ".bottom-menu", ".bottom_menu", ".policy", ".policy-links",
            ".terms", ".copyright", ".site-info", ".site_info",
        )
        for sel in selectors:
            for el in soup.select(sel):
                el.decompose()
        return soup

    # ------------------------------------------------------------------
    # 공지/광고/네비게이션 필터
    # ------------------------------------------------------------------
    #: 대괄호/괄호 안에 이 단어들이 포함되면 공지로 간주 (정규식 기반)
    _NOTICE_BRACKET_WORDS = (
        r"공지|안내|알림|필독|운영|관리|중요|주의|정보|보안|점검|"
        r"이벤트|광고|공식|EVENT|event|notice|NOTICE|AD|ad|admin"
    )
    _NOTICE_REGEX = __import__("re").compile(
        rf"[\[\(【]\s*[^\]\)】]*(?:{_NOTICE_BRACKET_WORDS})[^\]\)】]*\s*[\]\)】]"
    )

    #: 제목에서 이 키워드/패턴이 발견되면 공지/광고로 간주하고 제외 (레거시, 빠른 검색)
    NOTICE_PATTERNS: list[str] = [
        "[공지]", "(공지)", "【공지】", "공지)", "공지]",
        "[필독]", "(필독)", "[안내]", "(안내)", "[알림]", "(알림)",
        "[보안안내]", "[운영공지]", "[필독공지]", "[업데이트]",
        "[운영]", "[관리]", "[중요]", "[주의]", "[정보]",
        "[이벤트]", "(이벤트)", "[EVENT]", "[event]",
        "[광고]", "(광고)", "[AD]", "(AD)", "[ad]", "광고문의",
        "notice:", "[notice]", "(notice)",
        # 괄호 없는 공지성 문구
        "이용 안내", "이용안내", "이용 규칙", "이용규칙",
        "운영 안내", "운영안내", "운영 정책", "운영정책", "운영 원칙", "운영원칙",
        "서비스 안내", "서비스안내", "점검 안내", "점검안내",
        "안내드립니다", "알려드립니다", "공지합니다", "공지사항",
        "이용약관", "이용 약관", "가이드라인",
        # 업데이트/점검/운영 공지 (MLB파크 등)
        "업데이트 안내", "업데이트안내", "시즌 업데이트", "시즌업데이트",
        "말머리 위반", "말머리위반", "말머리 가이드", "말머리가이드",
        "처리 예정", "처리예정", "진행 예정 사항", "진행예정 사항", "예정 사항",
        "향후 진행", "운영 공지", "운영공지",
        # 사이트 법적/정책 문서 (뽐뿌 등 footer에서 자주 등장)
        "개인정보처리방침", "개인정보 처리방침", "개인정보취급방침",
        "청소년보호정책", "청소년 보호정책", "청소년보호 정책",
        "저작권정책", "저작권 정책", "저작권보호",
        "책임의 한계", "책임한계", "면책조항",
        "불법촬영물등 신고", "불법촬영물 신고", "불법 촬영물",
        "광고/제휴", "광고·제휴", "광고ㆍ제휴", "광고 제휴",
        "제휴문의", "제휴 문의", "광고문의", "광고 문의", "제안문의",
        "자주묻는질문", "자주 묻는 질문", "자주묻는 질문",
        "회사소개", "회사 소개", "사이트맵", "사이트 맵",
        "신고안내", "신고 안내",
        # '고객센터', 'FAQ'는 일반 불만글/질문글 제목에도 흔해서 제거
        # (footer 내 이런 링크는 BaseScraper.soup() 의 footer 제거로 이미 차단됨)
    ]
    #: 제목/요약에서 발견되면 광고/모집글로 간주 (substring 검색)
    AD_KEYWORDS: list[str] = [
        # 금융/투자
        "보험상담", "보험모집", "대출상담", "대출문의", "투자유치", "투자상담",
        "주식리딩", "리딩방", "종목추천", "코인리딩",
        # 무료/상담 미끼
        "무료상담", "무료진단", "무료체험", "후원금", "기부",
        "상담받으세요", "문의주세요", "상담 신청", "상담신청",
        # 판매/렌탈
        "구매대행", "제휴문의", "업체 문의", "업체문의",
        "판매합니다", "팝니다", "분양합니다", "임대합니다",
        # 통신 광고
        "휴대폰 개통", "휴대폰개통", "휴대폰 가입", "휴대폰가입",
        "휴대폰 성지", "휴대폰성지", "휴대폰 보조금", "휴대폰보조금",
        "통신비 절약", "통신비절약", "통신사 변경", "통신사변경",
        "알뜰폰 추천", "요금제 추천", "요금제추천",
        # 인터넷 광고
        "인터넷 신청", "인터넷신청", "인터넷 가입", "인터넷가입",
        "인터넷 약정", "인터넷약정", "인터넷 변경", "인터넷변경",
        "인터넷 설치", "인터넷설치", "인터넷+TV", "결합상품",
        # 렌탈
        "렌탈 신청", "렌탈신청", "렌털 신청", "렌털신청",
        "렌탈 문의", "렌탈문의", "렌털 문의", "렌털문의",
        "정수기 렌탈", "정수기렌탈", "공기청정기 렌탈",
        "구독 서비스", "구독서비스",
        # 일반 영업
        "방문 상담", "방문상담", "전화 상담", "전화상담",
        "할부 가능", "약정 할인", "무료 가입", "무료가입",
        "캐시백", "현금 지급", "현금지급", "사은품 증정", "사은품증정",
        # 뽐뿌 특화 광고 (screenshots에서 통과하던 케이스들)
        "렌탈몰", "종합가전", "본사직영", "최고혜택", "비교불가",
        "신규입점", "후기이벤트", "24시간상담", "24시간 상담",
        "설치전날", "선지급", "뽐뿌점수", "활동점수",
        "카드업체", "포인트 지급", "포인트지급",
        "신한카드", "삼성카드", "KB카드", "현대카드",
        # 성지/직영점/한정 이벤트성 광고
        "성지점", "휴대폰성지", "휴대폰 성지",
        "직영점", "본사 직영", "공식판매점", "공식 판매점",
        "공식인증점", "공인대리점", "인증대리점",
        "한정수량", "한정 수량", "한정판매", "한정 판매",
        "선착순", "수량 한정", "사은품 증정", "사은품증정",
        "특별할인", "특별 할인", "파격할인", "파격 할인",
        "최저가 보장", "최저가보장",
        # 혜택/현금지급 강조
        "현금 혜택", "현금혜택", "현금 사은품",
        "가입 혜택", "가입혜택", "신규가입", "신규 가입",
        "가입시", "가입 시 혜택",
        "추가 할인", "추가할인", "제휴 할인", "제휴할인",
        # 계약/장기 약정
        "3년 약정", "3년약정", "2년 약정", "2년약정",
        "결합 약정", "결합약정",
    ]
    #: 통신 3사 브랜드 (제목에 2개 이상 나오면 광고로 판정)
    _TELCO_REGEX = __import__("re").compile(
        r"\b(?:SKT|SK\s*텔레콤|SK\s*브로드밴드|KT|KTF|KT올레|올레KT|"
        r"LG\s*U\s*\+?|LGU\s*\+?|LG유플러스|유플러스)\b"
    )

    #: 렌탈/가전 브랜드 (2개 이상 나열되면 비교광고/렌탈몰로 판정)
    _RENTAL_BRANDS = (
        "코웨이", "청호나이스", "쿠쿠", "SK매직", "LG전자", "삼성전자",
        "현대렌탈", "현대렌털", "현대백화점", "교원웰스", "웰스", "바디프랜드",
        "쿠첸", "위닉스", "동양매직", "동양렌탈", "교원",
    )
    #: 제목이 이런 접미사로 끝나면 '게시판 네비게이션 링크'로 간주
    NAV_SUFFIXES: tuple[str, ...] = (
        "게시판", "광장", "마당", "포털", "포럼", "플라자",
        "커뮤니티", "갤러리", "뽐뿌", "공유", "토크",
    )
    #: 제목의 첫 단어(띄어쓰기 기준)가 이 접미사로 끝나면 업체명 → AD로 간주
    #: 예) "준준모터스 중고순정부품" → 첫 단어 "준준모터스" → "모터스" 접미사 매칭
    SHOP_NAME_SUFFIXES: tuple[str, ...] = (
        "모터스", "카센터", "정비소", "공업사", "상회", "상사",
        "제휴사", "부동산", "중개소", "공인중개", "타이어", "오토바이",
    )

    def _is_notice_or_ad(self, item: dict) -> bool:
        """공지/광고/모집/네비게이션 링크 여부 판단."""
        title = (item.get("title") or "").strip()
        if not title:
            return True  # 빈 제목은 제외

        # 0-a) 너무 짧은 제목 — 공백/탭/중점 제거 후 실제 글자 4자 미만
        # ('VS', 'IT', '문화', '해축', '5108' 같은 말머리/카테고리/ID)
        stripped = "".join(c for c in title if c not in " \t·ㆍ/-_")
        if len(stripped) < 4:
            return True
        # 0-b) 제목이 숫자만으로 이루어져 있음 (게시글 ID 잘못 파싱)
        if stripped.isdigit():
            return True

        # 0-c) AD 접두어 — 'AD ...', '[AD]...', '(AD)...'
        title_upper = title.upper()
        if (title_upper.startswith("AD ") or title_upper.startswith("AD:")
                or title_upper.startswith("[AD]") or title_upper.startswith("(AD)")):
            return True

        # 0-d) 해시태그 도배 — 제목에 # 3개 이상이면 광고 (길이 180자 이내)
        if title.count("#") >= 3 and len(title) < 180:
            return True

        # 0-e) 통신 3사 브랜드 2개 이상 + 통신 문맥 → 통신/인터넷 광고
        import re as _re
        telco_matches = self._TELCO_REGEX.findall(title)
        telco_set = {m.strip().upper().replace(" ", "") for m in telco_matches}
        # 이미 매칭된 부분 제거 후 단독 브랜드(SK/KT/LG) 추가 계산 (중복 방지)
        remaining = self._TELCO_REGEX.sub(" ", title)
        simple_brands = set(_re.findall(r"\b(?:SK|KT|LG)\b", remaining))
        total_brands = len(telco_set) + len(simple_brands)

        telco_context_words = (
            "인터넷", "통신", "휴대폰", "모바일", "개통", "가입", "약정",
            "요금", "결합", "청약", "알뜰폰", "와이파이", "wifi", "TV",
        )
        low = title.lower()
        has_telco_context = any(w.lower() in low for w in telco_context_words)
        if total_brands >= 2 and has_telco_context:
            return True
        # 정식 통신사명(SKT/LGU+/유플러스 등) 2개 이상은 문맥 없어도 광고
        strict_names = {"SKT", "LGU+", "LGU", "LG유플러스", "유플러스",
                         "SK텔레콤", "SK브로드밴드", "KTF", "KT올레", "올레KT"}
        if len(telco_set & strict_names) >= 2:
            return True

        # 0-f) 렌탈/가전 브랜드 2개 이상 나열 → 비교광고/렌탈몰
        brand_count = sum(1 for b in self._RENTAL_BRANDS if b in title)
        if brand_count >= 2:
            return True

        # 1) 정규식 — 대괄호/괄호 내 공지성 단어 ([보안안내], [운영공지] 등)
        if self._NOTICE_REGEX.search(title):
            return True

        # 2) 레거시 문자열 리스트
        lower = title.lower()
        for pat in self.NOTICE_PATTERNS:
            if pat.lower() in lower:
                return True

        # 3) 광고/모집 키워드
        for kw in self.AD_KEYWORDS:
            if kw in title:
                return True

        # 4) 네비게이션 메뉴 링크 ("쿠폰게시판", "휴대폰뽐뿌" 등)
        # - 짧은 제목(15자 미만)이 네비게이션 접미사로 끝나는 경우
        if len(title) < 15:
            for suf in self.NAV_SUFFIXES:
                if title.endswith(suf):
                    return True

        # 4-2) 짧고 공백 없는 2어절 합성어 메뉴 ("오늘특가", "인기핫딜", "최신글" 등)
        # - 공백이 없고 길이 3-8자인데 '글/특가/핫딜/순위/랭킹/추천/신상' 끝
        if 3 <= len(title) <= 8 and " " not in title:
            nav_endings = (
                "핫딜", "특가", "할인", "세일", "이벤트",
                "순위", "랭킹", "추천", "신상",
                "최신글", "인기글", "인기순", "최신순", "조회순", "추천순",
                "목록", "리스트",
            )
            for suf in nav_endings:
                if title.endswith(suf):
                    return True

        # 5) 업체명으로 시작하는 광고 ("준준모터스 중고순정부품" 등)
        first_word = title.split()[0] if title.split() else ""
        for suf in self.SHOP_NAME_SUFFIXES:
            # 첫 단어가 업체 suffix로 끝나고, 단어 길이가 2자보다 크면 (접미사만 있는 건 제외)
            if first_word.endswith(suf) and len(first_word) > len(suf):
                return True

        return False


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

        # 셀렉터 실패 시 범용 링크 휴리스틱 fallback
        if not items:
            items = self._heuristic_parse(html)
            if items:
                logger.info("[%s] heuristic fallback 사용: %d건", self.source, len(items))

        # 공지/광고 제거
        items = [it for it in items if not self._is_notice_or_ad(it)]

        # 추천/조회 내림차순으로 재정렬 (진짜 인기글 먼저)
        def _popularity(it: dict) -> int:
            return (
                int(it.get("score", 0) or 0) * 10
                + int(it.get("views", 0) or 0) // 100
                + int(it.get("comments", 0) or 0) * 3
            )
        items.sort(key=_popularity, reverse=True)

        if not items:
            self.last_error = (
                "파싱 결과 0건 — 레이아웃 변경 또는 CAPTCHA/빈 페이지 반환 가능"
            )

        out: list[dict] = []
        for it in items[:limit]:
            out.append(self._normalize(it))
        return out

    # ------------------------------------------------------------------
    # RSS / 모바일 fallback 헬퍼
    # ------------------------------------------------------------------
    @staticmethod
    def _fetch_rss(url: str, limit: int, source: str) -> list[dict]:
        """RSS URL에서 feedparser 로 항목 추출. 실패 시 빈 리스트."""
        try:
            import feedparser
            feed = feedparser.parse(url)
            if getattr(feed, "bozo", 0) and not feed.entries:
                return []
            items: list[dict] = []
            for entry in feed.entries[:limit]:
                title = entry.get("title", "")
                link = entry.get("link", "")
                if not title or not link:
                    continue
                summary = entry.get("summary", "") or entry.get("description", "")
                # HTML 태그 제거
                if "<" in summary:
                    summary = re.sub(r"<[^>]+>", " ", summary)
                summary = re.sub(r"\s+", " ", summary).strip()[:300]
                items.append({
                    "title": title,
                    "url": link,
                    "summary": summary,
                    "source": source,
                    "engagement": "RSS",
                    "score": 0,
                    "views": 0,
                    "comments": 0,
                })
            return items
        except Exception as exc:  # noqa: BLE001
            logger.info("[%s] RSS 실패 (%s): %s", source, url, exc)
            return []

    def _try_urls(self, urls: list[str], limit: int) -> list[dict]:
        """여러 URL을 순차 시도, 첫 성공의 결과 반환."""
        for u in urls:
            try:
                html = self.fetch(u)
                items = self.parse(html)
                if not items:
                    items = self._heuristic_parse(html)
                if items:
                    return items
            except Exception as exc:  # noqa: BLE001
                logger.info("[%s] %s 실패: %s", self.source, u, exc)
        return []


    def _heuristic_parse(self, html: str) -> list[dict]:
        """스크래퍼 parse()가 0건일 때 fallback.

        페이지의 모든 <a> 중 '게시글 URL처럼 생긴' 것들만 추출:
        - href에 숫자 ID 또는 view/article/board 패턴
        - 제목 길이 10~200자
        - 중복 href 제외
        """
        import re
        from urllib.parse import urljoin, urlparse
        try:
            soup = self.soup(html)
        except Exception:  # noqa: BLE001
            return []

        # 응답이 CAPTCHA/차단 페이지면 스킵 (대부분 <body> 크기가 작음)
        body = soup.find("body")
        if not body or len(body.get_text(strip=True)) < 200:
            return []

        base_netloc = urlparse(self.base_url).netloc
        # 게시글 URL의 공통 패턴 — 숫자 ID가 꼭 있어야 함 (게시판 선택용 ?id=coupon 같은 건 제외)
        article_href_re = re.compile(
            r"(?:^|/)\d{5,}(?:[/?]|$)"              # /12345+ 숫자 5자리 이상 path
            r"|(?:no|wr_id|articleid|post_id|thread_id|tid|doc|document_srl)=\d+"
            r"|/(?:view|article|read|post|thread|document)/\d+"
            r"|view\.php\?[^#]*no=\d+",             # view.php?no=...
            re.I,
        )
        items: list[dict] = []
        seen_hrefs: set[str] = set()

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue

            # 게시글 URL 패턴 확인
            if not article_href_re.search(href):
                continue

            # 절대 URL 변환 + 같은 호스트만 (외부 링크 제외)
            abs_url = urljoin(self.base_url, href)
            try:
                netloc = urlparse(abs_url).netloc
                if base_netloc and netloc and not self._same_site(netloc, base_netloc):
                    continue
            except Exception:  # noqa: BLE001
                continue

            if abs_url in seen_hrefs:
                continue

            # 제목 후보: a 태그 내부에서 가장 적절한 텍스트 추출
            title_el = (
                a.select_one(".title, .subject, .sbj, .tit, h3, h4, strong")
                or a
            )
            raw_title = title_el.get_text(" ", strip=True)
            title = self.clean_title(raw_title)
            if not title or len(title) < 8 or len(title) > 200:
                continue
            # 메뉴성 텍스트 제외
            if title in ("더보기", "목록", "이전", "다음", "홈", "로그인"):
                continue

            # ★ 핵심: 부모 컨텍스트에 숫자가 2개 이상 있어야 게시글로 인정
            parent = a.find_parent(["tr", "li", "article", "div"])
            score = views = comments = 0
            if parent:
                # 부모 텍스트가 부족하면 조부모까지 확장
                parent_text = parent.get_text(" ", strip=True)
                all_nums_str = re.findall(r"\d{1,6}(?:,\d{3})*", parent_text)
                if len(all_nums_str) < 2:
                    grandparent = parent.parent
                    if grandparent:
                        gtext = grandparent.get_text(" ", strip=True)
                        gnums = re.findall(r"\d{1,6}(?:,\d{3})*", gtext)
                        if len(gnums) >= 2:
                            parent_text = gtext
                            all_nums_str = gnums
                            parent = grandparent
                # 숫자가 2개 미만이어도 어느 정도 긴 제목(10자+)이면 실제 게시글일 확률 높음
                # → 메타 없이도 수집 허용 (메타 0건으로 표시)
                if len(all_nums_str) < 2 and len(title) < 10:
                    continue

                # 레이블 기반 추출 — 더 많은 변형 지원
                m_score = re.search(
                    r"(?:추천\s*수?|좋아요|공감|👍|⭐|UP|vote|likes?)[\s:：]*([\d,]+)",
                    parent_text, re.I,
                )
                m_views = re.search(
                    r"(?:조회\s*수?|👁|views?|hit|읽음)[\s:：]*([\d,]+)",
                    parent_text, re.I,
                )
                m_comments = re.search(
                    r"(?:댓글\s*수?|💬|reply|comments?)[\s:：]*([\d,]+)",
                    parent_text, re.I,
                )
                if m_score:
                    score = self.to_int(m_score.group(1))
                if m_views:
                    views = self.to_int(m_views.group(1))
                if m_comments:
                    comments = self.to_int(m_comments.group(1))

                # 레이블 매칭 없으면 매그니튜드 기반 추정:
                # 가장 큰 숫자 → views, 그 다음 → comments
                if not (score or views or comments):
                    nums = sorted(
                        {self.to_int(n) for n in all_nums_str if self.to_int(n) > 0},
                        reverse=True,
                    )
                    # 100 이상이고 댓글/추천 같은 작은 수 후보 제외 (날짜 4자리 등 회피)
                    nums = [n for n in nums if 1 <= n <= 9_999_999]
                    if len(nums) >= 1:
                        views = nums[0]
                    if len(nums) >= 2:
                        comments = nums[1] if nums[1] < nums[0] // 5 else 0
            else:
                # 부모 없음 = 구조 비정상, 스킵
                continue

            seen_hrefs.add(abs_url)
            items.append({
                "title": title,
                "url": abs_url,
                "score": score,
                "views": views,
                "comments": comments,
                "engagement": self.format_engagement(
                    score=score, views=views, comments=comments
                ),
            })

            if len(items) >= 50:
                break
        return items

    @staticmethod
    def _same_site(a: str, b: str) -> bool:
        """두 호스트가 같은 사이트(루트 도메인 일치)인지 확인."""
        def root(host: str) -> str:
            parts = host.split(".")
            return ".".join(parts[-2:]) if len(parts) >= 2 else host
        return root(a) == root(b)

    # ------------------------------------------------------------------
    # 반환 포맷 정규화
    # ------------------------------------------------------------------
    @staticmethod
    def clean_title(raw: str) -> str:
        """제목에서 메타데이터/닉네임 잔재 제거.

        예) '실제 제목 닉네임 조회 1234 추천 56' → '실제 제목'
            '제목 21:51 1057 플러티고' → '제목'  (클리앙 스타일 꼬리)
        """
        if not raw:
            return ""
        import re
        s = raw.strip()
        # 1) 후행 메타데이터 라벨 절단 ('조회 123', '추천 45' 등)
        for label in ("조회", "추천", "댓글", "좋아요", "공감",
                      "views", "view", "hit", "comment", "reply", "like"):
            m = re.search(rf"\s+{label}\s*[:：]?\s*[\d,]+.*$", s, re.I)
            if m:
                s = s[:m.start()].rstrip()
        # 2) 뒤에 [숫자] 또는 (숫자)로 댓글 표시된 경우 제거
        s = re.sub(r"\s*[\[\(]\s*\d+\s*[\]\)]\s*$", "", s)
        # 3) 클리앙/루리웹 스타일 꼬리 "... HH:MM 숫자 닉네임" 또는
        #    "... HH:MM 숫자" — 시간 뒤에 숫자가 따라오면 메타로 판정하고 절단
        s = re.sub(r"\s+\d{1,2}:\d{2}\s+\d+.*$", "", s)
        # 4) 시간/날짜 단독 후행 제거
        s = re.sub(r"\s+\d{1,2}[:.\-]\d{1,2}(?:[:.\-]\d{1,4})?\s*$", "", s)
        s = re.sub(r"\s+\d{4}[-./]\d{1,2}[-./]\d{1,2}\s*$", "", s)
        # 5) 꼬리에 '숫자 한두단어' 가 붙은 패턴 (추천수 + 닉네임) — 2+ 숫자 + 한글/영문 1-10자
        #    예: '... 7 7 2 2857 핫핫' → '...'
        s = re.sub(
            r"\s+(?:\d+\s+){2,}[\w가-힣]{1,10}\s*$",
            "", s,
        )
        # 5-b) 꼬리에 '공백+숫자' 가 2번 이상 반복해서 남은 경우 (예: '제목 1 1')
        s = re.sub(r"(?:\s+\d+){2,}\s*$", "", s)
        # 6) 연속 공백 정리
        s = re.sub(r"\s{2,}", " ", s).strip()
        return s

    def _normalize(self, item: dict) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        def _safe_int(v) -> int:
            if isinstance(v, int):
                return v
            try:
                return int(v or 0)
            except (ValueError, TypeError):
                return self.to_int(v)

        return {
            "title": self.clean_title(item.get("title") or ""),
            "summary": (item.get("summary") or "").strip(),
            "url": item.get("url", ""),
            "source": item.get("source", self.source),
            "category": item.get("category", self.category),
            "engagement": item.get("engagement", ""),
            "thumbnail": item.get("thumbnail", ""),
            "collected_at": item.get("collected_at", now),
            "score": _safe_int(item.get("score")),
            "views": _safe_int(item.get("views")),
            "comments": _safe_int(item.get("comments")),
        }

    # ------------------------------------------------------------------
    # 편의 유틸
    # ------------------------------------------------------------------
    @staticmethod
    def to_int(text: str | None) -> int:
        """'1.2K', '3,456', '조회 789' 같은 문자열을 정수로 변환.

        날짜 문자열('23.06.19') 등 float로 파싱 불가능한 케이스는 0 반환.
        """
        if text is None:
            return 0
        s = str(text).strip().lower().replace(",", "")
        import re
        # 정수 또는 소수 한 번(예: 1.2K)만 허용 — 날짜 23.06.19 는 매칭 안 됨
        m = re.search(r"(\d+(?:\.\d+)?)\s*([km万])?", s)
        if not m:
            return 0
        try:
            num = float(m.group(1))
        except (ValueError, TypeError):
            return 0
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

    def gemini_call(self, prompt: str, max_tokens: int = 2048) -> str | None:
        """Gemini REST API 호출 — 모델 자동 폴백 + 예외 안전.

        성공 시 응답 텍스트(thought 제외) 반환, 실패 시 None + self.last_error 설정.
        """
        import requests as _rq
        import time as _time
        from config import GEMINI_MODEL, get_gemini_key

        key = get_gemini_key()
        if not key:
            self.last_error = "GEMINI_API_KEY 없음"
            return None

        headers = {"Content-Type": "application/json", "x-goog-api-key": key}
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens},
        }
        models = [GEMINI_MODEL, "gemini-2.0-flash", "gemini-1.5-flash"]

        for model in models:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models"
                f"/{model}:generateContent"
            )
            for attempt in range(2):
                try:
                    resp = _rq.post(url, headers=headers, json=body, timeout=60)
                except Exception as exc:  # noqa: BLE001
                    self.last_error = f"Gemini {model} 연결 오류: {exc}"
                    break
                if resp.status_code in (429, 503, 529):
                    self.last_error = f"Gemini {model} {resp.status_code}"
                    _time.sleep((attempt + 1) * 3)
                    continue
                if not resp.ok:
                    self.last_error = f"Gemini {model} {resp.status_code}"
                    break
                try:
                    parts = resp.json()["candidates"][0]["content"].get("parts", [])
                    text = "\n".join(
                        p.get("text", "") for p in parts
                        if p.get("text") and not p.get("thought")
                    )
                    if text:
                        self.last_error = ""
                        return text
                except Exception as exc:  # noqa: BLE001
                    self.last_error = f"Gemini {model} 응답 파싱 오류: {exc}"
                break  # 재시도 불필요한 오류 → 다음 모델로

        return None
