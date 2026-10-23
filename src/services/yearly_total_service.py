"""해가 바뀔 때 새 연도의 전체 총매 파일을 만든다.

전체 총매 파일은 연 단위로 따로 운영한다. 1월에 새 파일이 없으면 월 시트를
찾지 못해 매출 입력이 통째로 막히므로, 전년도 파일을 복사해 새 연도 파일을
준비한다. 원본 파일은 건드리지 않는다.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from src.services.entry_service import (
    _open_book,
    create_monthly_expense_sheet,
    create_monthly_sheet,
)

# 파일명 안의 4자리 연도 (예: '리와인드 총매출 2026.xlsx')
_YEAR_PATTERN = re.compile(r"(?<!\d)(20\d{2})(?!\d)")


def file_year(path: str | Path) -> int | None:
    """파일명에서 4자리 연도를 읽는다. 없으면 None."""
    match = _YEAR_PATTERN.search(Path(path).name)
    return int(match.group(1)) if match else None


def build_year_path(path: str | Path, year: int) -> Path:
    """파일명의 연도만 바꾼 경로를 반환한다."""
    source = Path(path)
    match = _YEAR_PATTERN.search(source.name)
    if not match:
        raise ValueError(
            f"파일명에 연도(예: 2026)가 없어 새 연도 파일 이름을 만들 수 없습니다.\n"
            f"{source.name}\n\n"
            "파일명에 연도를 넣어주시거나, 새 연도 파일을 직접 만들어 설정에서 선택해주세요."
        )
    return source.with_name(source.name[:match.start()] + str(year) + source.name[match.end():])


def _old_month_sheet_names(sheet_names: list[str], keep_year: int) -> list[str]:
    """새 연도가 아닌 월 시트 이름만 추린다. 표지 등 다른 시트는 건드리지 않는다."""
    keep_token = f"{keep_year % 100}년"
    return [
        name for name in sheet_names
        if ("매출" in name or "지출" in name)
        and re.search(r"\d{2}년\s*\d{1,2}월", name)
        and keep_token not in name
    ]


def create_next_year_file(
    total_path: str | Path,
    year: int,
    password: str | None = None,
) -> tuple[Path, list[str]]:
    """전년도 전체 총매 파일을 복사해 새 연도 파일을 만든다.

    복사본에 새 연도 1월 매출·지출 시트를 만든 뒤, 지난 연도의 월 시트만 지운다.
    표지처럼 월 시트가 아닌 것은 그대로 둔다. 원본 파일은 수정하지 않는다.

    Returns:
        (새로 만든 파일 경로, 지운 시트 이름 목록)
        파일이 이미 있으면 (기존 경로, []) 를 돌려준다.
    """
    source = Path(total_path)
    if not source.exists():
        raise FileNotFoundError(f"전체 총매 파일을 찾을 수 없습니다: {source}")

    target = build_year_path(source, year)
    if target.exists():
        return target, []

    shutil.copy2(source, target)

    # 새 연도 1월 시트를 먼저 만든다. 전년도 12월 시트가 템플릿이 되므로
    # 지우는 작업보다 앞서야 한다.
    create_monthly_sheet(target, year, 1, password)
    create_monthly_expense_sheet(target, year, 1, password)

    book, was_open = _open_book(target, password=password)
    try:
        removed = _old_month_sheet_names([s.name for s in book.sheets], year)
        for name in removed:
            book.sheets[name].delete()
        book.save()
    finally:
        if not was_open:
            book.app.quit()

    return target, removed
