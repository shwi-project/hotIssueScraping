"""JSON 파일 기반 저장된 소재 관리."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from config import SAVED_IDEAS_PATH

logger = logging.getLogger(__name__)


def _ensure_file(path: Path) -> None:
    if not path.exists():
        path.write_text("[]", encoding="utf-8")


def load_all() -> list[dict]:
    """저장된 소재 전체 로드."""
    _ensure_file(SAVED_IDEAS_PATH)
    try:
        with SAVED_IDEAS_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as exc:  # noqa: BLE001
        logger.warning("저장 파일 로드 실패: %s", exc)
        return []


def save_all(items: list[dict]) -> None:
    """전체 덮어쓰기."""
    _ensure_file(SAVED_IDEAS_PATH)
    with SAVED_IDEAS_PATH.open("w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def add_item(item: dict, *, note: str = "") -> bool:
    """항목 추가. URL 기준 중복이면 False 반환."""
    items = load_all()
    url = item.get("url", "")
    for existing in items:
        if existing.get("url") == url and url:
            return False
    saved = {
        **item,
        "note": note,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    items.append(saved)
    save_all(items)
    return True


def remove_item(url: str) -> bool:
    """URL로 항목 삭제."""
    items = load_all()
    new_items = [it for it in items if it.get("url") != url]
    if len(new_items) == len(items):
        return False
    save_all(new_items)
    return True


def update_note(url: str, note: str) -> bool:
    """URL로 메모 업데이트."""
    items = load_all()
    changed = False
    for it in items:
        if it.get("url") == url:
            it["note"] = note
            changed = True
            break
    if changed:
        save_all(items)
    return changed


def clear_all() -> None:
    save_all([])


def to_csv_bytes() -> bytes:
    """저장된 전체를 CSV 바이트로."""
    items = load_all()
    if not items:
        return "".encode("utf-8-sig")

    rows = []
    for it in items:
        analysis = it.get("analysis") or {}
        rows.append({
            "제목": it.get("title", ""),
            "출처": it.get("source", ""),
            "카테고리": it.get("category", ""),
            "참여도": it.get("engagement", ""),
            "URL": it.get("url", ""),
            "요약": analysis.get("summary", it.get("summary", "")),
            "쇼츠 아이디어": analysis.get("shorts_idea", ""),
            "타겟 시청자": analysis.get("target_audience", ""),
            "해시태그": ", ".join(analysis.get("hashtags", []) or []),
            "활용도 점수": analysis.get("score", ""),
            "메모": it.get("note", ""),
            "저장시각": it.get("saved_at", ""),
        })

    df = pd.DataFrame(rows)
    # Excel 한글 호환용 UTF-8 BOM
    return ("\ufeff" + df.to_csv(index=False)).encode("utf-8")


def is_saved(url: str) -> bool:
    return any(it.get("url") == url for it in load_all())
