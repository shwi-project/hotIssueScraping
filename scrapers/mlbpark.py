"""MLB파크 불펜 인기글 스크래퍼.

MLB파크 HTML 특징:
- 게시글 URL: `/mp/bbs_view.php?b=bullpen&id=숫자` (id=숫자 필수)
- 말머리(카테고리) 링크: `/mp/b.php?b=bullpen&c=카테고리명` (숫자 아님)
  → 말머리는 '야구', 'IT', '문화', 'VS' 등 짧은 텍스트라 필터에서도 걸러짐
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from .base import BaseScraper

_ARTICLE_RE = re.compile(r"bbs_view\.php.*(?:id|b_id)=\d+", re.I)

# MLB파크 말머리/카테고리 — 정확 일치하면 제목이 아니라 카테고리
_MLB_CATEGORIES = {
    # 스포츠
    "야구", "MLB", "KBO", "축구", "해축", "K리그", "EPL", "농구", "NBA",
    "배구", "골프", "테니스", "격투기", "UFC", "WWE", "F1", "e스포츠",
    "LOL", "롤", "펠클", "펠레클래식",
    # 일반 카테고리
    "IT", "문화", "정치", "경제", "사회", "연예", "방송", "음악", "영화",
    "드라마", "만화", "게임", "역사", "문학", "종교", "철학",
    "코인", "주식", "부동산", "여행", "요리", "반려동물",
    # 파크 특화
    "VS", "자유", "기타", "토론", "썰", "장터",
}


class MlbparkScraper(BaseScraper):
    source = "MLB파크"
    base_url = "https://mlbpark.donga.com/mp/b.php?b=bullpen&m=bbs&p=1&s=2"
    category = "이슈/뉴스"

    def parse(self, html: str) -> list[dict]:
        soup = self.soup(html)
        items: list[dict] = []

        # 모든 tr 중 말머리·광고 제외, 실제 게시글만
        for tr in soup.select("table tr"):
            parsed = self._extract_from_tr(tr)
            if parsed:
                items.append(parsed)

        # 1차 결과 부족 시 link-heuristic
        if len(items) < 3:
            seen: set[str] = set()
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if not _ARTICLE_RE.search(href):
                    continue
                title = a.get_text(" ", strip=True)
                # 최소 10자 + 카테고리 이름 제외
                if not title or len(title) < 10:
                    continue
                if title in _MLB_CATEGORIES:
                    continue
                if href in seen:
                    continue
                seen.add(href)
                url = href if href.startswith("http") else urljoin(
                    "https://mlbpark.donga.com/mp/", href
                )

                # 부모에서 메타 추출
                parent = a.find_parent(["tr", "li", "div"])
                score = views = comments = 0
                if parent:
                    ptxt = parent.get_text(" ", strip=True)
                    nums = [self.to_int(n) for n in re.findall(r"[\d,]+", ptxt)]
                    nums = [n for n in nums if n > 0]
                    if nums:
                        nums_sorted = sorted(nums, reverse=True)
                        if len(nums_sorted) >= 1:
                            views = nums_sorted[0]
                        if len(nums_sorted) >= 2 and nums_sorted[1] < views // 2:
                            score = nums_sorted[1]

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
                if len(items) >= 60:
                    break
        return items

    def _extract_from_tr(self, tr) -> dict | None:
        # 공지 row 제외
        cls = " ".join(tr.get("class", [])).lower()
        if any(k in cls for k in ("notice", "noti", "top", "ad")):
            return None

        # 제목 링크: href가 bbs_view.php + id=숫자 포함이어야 함
        title_link = None
        for a in tr.find_all("a", href=True):
            if _ARTICLE_RE.search(a["href"]):
                text = a.get_text(" ", strip=True)
                # 최소 10자 + MLB 카테고리 블랙리스트 제외
                if len(text) >= 10 and text not in _MLB_CATEGORIES:
                    title_link = a
                    break

        if not title_link:
            return None

        title = title_link.get_text(" ", strip=True)
        href = title_link.get("href") or ""
        url = href if href.startswith("http") else urljoin(
            "https://mlbpark.donga.com/mp/", href
        )

        score = views = comments = 0
        tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        nums = [self.to_int(t) for t in tds if t]
        nums = [n for n in nums if 0 < n < 10_000_000]
        if len(nums) >= 2:
            views, score = max(nums), sorted(nums)[-2]

        cmt = tr.select_one("span.replycnt, span.cmtCnt, span.cmt")
        if cmt:
            comments = self.to_int(cmt.get_text())

        return {
            "title": title,
            "url": url,
            "score": score,
            "views": views,
            "comments": comments,
            "engagement": self.format_engagement(
                score=score, views=views, comments=comments
            ),
        }
