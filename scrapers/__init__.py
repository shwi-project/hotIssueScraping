"""스크래퍼 패키지.

각 플랫폼별 스크래퍼를 한 곳에서 import할 수 있게 모은다.
"""
from __future__ import annotations

from .base import BaseScraper
from .arcalive import ArcaliveScraper
from .bobaedream import BobaedreamScraper
from .clien import ClienScraper
from .dcinside import DcinsideScraper
from .fmkorea import FmkoreaScraper
from .humoruniv import HumorunivScraper
from .instiz import InstizScraper
from .inven import InvenScraper
from .mlbpark import MlbparkScraper
from .natepan import NatepanScraper
from .naver_trends import NaverTrendsScraper
from .ppomppu import PpomppuScraper
from .reddit import RedditScraper
from .ruliweb import RuliwebScraper
from .theqoo import TheqooScraper
from .threads import ThreadsScraper
from .tiktok_trends import TiktokTrendsScraper
from .youtube_trends import YoutubeTrendsScraper


SCRAPER_CLASSES: dict[str, type[BaseScraper]] = {
    "dcinside": DcinsideScraper,
    "fmkorea": FmkoreaScraper,
    "ppomppu": PpomppuScraper,
    "ruliweb": RuliwebScraper,
    "theqoo": TheqooScraper,
    "inven": InvenScraper,
    "natepan": NatepanScraper,
    "arcalive": ArcaliveScraper,
    "clien": ClienScraper,
    "instiz": InstizScraper,
    "bobaedream": BobaedreamScraper,
    "mlbpark": MlbparkScraper,
    "humoruniv": HumorunivScraper,
    "naver_trends": NaverTrendsScraper,
    "reddit": RedditScraper,
    "threads": ThreadsScraper,
    "youtube_trends": YoutubeTrendsScraper,
    "tiktok_trends": TiktokTrendsScraper,
}


def get_scraper(key: str) -> BaseScraper | None:
    """키로 스크래퍼 인스턴스 생성. 없으면 None."""
    cls = SCRAPER_CLASSES.get(key)
    return cls() if cls else None


__all__ = [
    "BaseScraper",
    "SCRAPER_CLASSES",
    "get_scraper",
]
