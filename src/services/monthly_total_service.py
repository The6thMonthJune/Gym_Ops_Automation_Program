"""월별 총매 파일은 달마다 새 파일로 운영한다.

달이 바뀌면 전월 파일을 복사해 새 파일을 만들고, 안에 있는 시트명을 새 달로
바꾼 뒤 입력값을 비운다. 양식과 수식은 그대로 둔다. 원본 파일은 건드리지 않는다.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from src.core.sheet_layout import CURRENT_LAYOUT, last_column

# 파일명에 들어간 연·월 표기. 위에서부터 먼저 맞는 것을 쓴다.
_FILE_MONTH_PATTERNS = (
    # 26년 10월 / 2026 년 10 월
    re.compile(r"(?P<year>\d{2,4})(?P<ysep>\s*년\s*)(?P<month>\d{1,2})(?P<msep>\s*월)"),
    # 26.10월 / 26-10월
    re.compile(r"(?P<year>\d{2,4})(?P<ysep>\s*[.\-_]\s*)(?P<month>\d{1,2})(?P<msep>\s*월)"),
    # 2026-10 / 2026_10 (뒤에 숫자가 더 붙지 않을 때)
    re.compile(r"(?P<year>\d{4})(?P<ysep>\s*[-_.]\s*)(?P<month>\d{1,2})(?P<msep>)(?!\d)"),
    # 10월 — 연도 표기가 없는 경우
    re.compile(r"(?<!\d)(?P<year>)(?P<ysep>)(?P<month>\d{1,2})(?P<msep>\s*월)"),
)


def _match_month(name: str):
    for pattern in _FILE_MONTH_PATTERNS:
        found = pattern.search(name)
        if found:
            return found
    return None


def file_month(path: str | Path) -> tuple[int | None, int] | None:
    """파일명에서 (연도, 월)을 읽는다. 연도 표기가 없으면 연도는 None."""
    found = _match_month(Path(path).name)
    if not found:
        return None
    year_text = found.group("year")
    year = None
    if year_text:
        year = int(year_text)
        if year < 100:
            year += 2000
    return year, int(found.group("month"))


def build_month_file_path(path: str | Path, year: int, month: int) -> Path:
    """파일명의 연·월만 바꾼 경로. 표기 방식(구분자·0 채움·자릿수)은 그대로 둔다."""
    source = Path(path)
    found = _match_month(source.name)
    if not found:
        raise ValueError(
            f"파일명에서 월을 찾을 수 없어 새 달 파일 이름을 만들 수 없습니다.\n"
            f"{source.name}\n\n"
            "파일명에 '11월' 같은 월 표기를 넣어주시거나, "
            "새 달 파일을 직접 만들어 프로그램에서 선택해주세요."
        )

    year_text = found.group("year")
    if year_text:
        new_year = f"{year % 100:02d}" if len(year_text) == 2 else str(year)
    else:
        new_year = ""

    month_text = found.group("month")
    padded = len(month_text) == 2 and month_text.startswith("0")
    new_month = f"{month:02d}" if padded else str(month)

    replacement = new_year + found.group("ysep") + new_month + found.group("msep")
    new_name = source.name[:found.start()] + replacement + source.name[found.end():]
    return source.with_name(new_name)


def _sheet_kind(name: str) -> str | None:
    if "지출" in name:
        return "지출"
    if "매출" in name:
        return "매출"
    return None


def ensure_monthly_file(
    configured_path: str | Path,
    year: int,
    month: int,
    password: str | None = None,
    max_lookback: int = 12,
) -> tuple[Path, bool]:
    """해당 연월의 월별 총매 파일 경로를 돌려준다.

    없으면 가장 가까운 이전 달 파일을 복사해 만들고, 시트명을 새 달로 바꾼 뒤
    입력값을 비운다. 원본은 수정하지 않는다.

    Returns:
        (파일 경로, 새로 만들었는지)
    """
    configured = Path(configured_path)
    target = build_month_file_path(configured, year, month)
    if target.exists():
        return target, False

    source = _find_source_file(configured, year, month, max_lookback)
    if source is None:
        raise FileNotFoundError(
            f"{year % 100:02d}년 {month}월 월별 총매 파일을 만들 양식을 찾지 못했습니다.\n"
            f"찾아본 이름: {target.name}\n\n"
            "이전 달 파일이 같은 폴더에 있어야 복사해서 만들 수 있습니다."
        )

    shutil.copy2(source, target)
    try:
        _retitle_and_clear(target, year, month, password)
    except Exception:
        target.unlink(missing_ok=True)  # 반쯤 만들어진 파일을 남기지 않는다
        raise
    return target, True


def _find_source_file(
    configured: Path, year: int, month: int, max_lookback: int
) -> Path | None:
    """설정된 파일부터 보고, 없으면 이전 달 이름으로 거슬러 올라가며 찾는다."""
    if configured.exists():
        return configured
    for delta in range(1, max_lookback + 1):
        past_month, past_year = month - delta, year
        while past_month <= 0:
            past_month += 12
            past_year -= 1
        try:
            candidate = build_month_file_path(configured, past_year, past_month)
        except ValueError:
            return None
        if candidate.exists():
            return candidate
    return None


def _retitle_and_clear(
    path: Path, year: int, month: int, password: str | None
) -> None:
    """복사본의 매출·지출 시트명을 새 달로 바꾸고 입력값만 비운다."""
    from src.services.entry_service import _clear_keep_formulas, _open_book
    from src.services.total_sales_service import build_month_sheet_name

    book, was_open = _open_book(path, password=password)
    try:
        for sheet in list(book.sheets):
            kind = _sheet_kind(sheet.name)
            if kind is None:
                continue  # 표지 같은 시트는 건드리지 않는다
            try:
                sheet.name = build_month_sheet_name(sheet.name, year, month)
            except ValueError:
                pass  # 시트명에 연·월이 없으면 이름은 그대로 두고 비우기만 한다

            if kind == "매출":
                _clear_keep_formulas(sheet, 12, 500, 2, last_column(CURRENT_LAYOUT))
            else:
                _clear_keep_formulas(sheet, 6, 500, 1, 10, keep_cols={2})
        book.save()
    finally:
        if not was_open:
            book.app.quit()
