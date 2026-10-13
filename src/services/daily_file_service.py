from __future__ import annotations

import shutil
from datetime import date, timedelta
from pathlib import Path

import openpyxl

from src.core.file_naming import build_date_path, build_next_date_path, resolve_file_date
from src.config.constants import DEFAULT_SHEET_NAME
from src.config.settings import get_expense_daily_sheet

# 한 번에 자동 생성할 수 있는 최대 일수. 이보다 큰 공백은 사용자에게 되묻는다.
MAX_BACKFILL_DAYS = 62


def create_next_daily_file(source_file: str | Path, overwrite: bool = False) -> Path:
    """
    원본 파일을 복사하여 다음 날짜 파일을 생성한다.
    복사 후 매출·지출 입력 데이터를 초기화하고 수식·유효성 검사는 보존한다.
    """
    source_path = Path(source_file)

    if not source_path.exists():
        raise FileNotFoundError(f"원본 파일을 찾을 수 없습니다: {source_path}")

    target_path = build_next_date_path(source_path)

    if target_path.exists() and not overwrite:
        raise FileExistsError(f"이미 대상 파일이 존재합니다: {target_path}")

    shutil.copy2(source_path, target_path)
    _clear_daily_entries(target_path)
    return target_path


def create_daily_file_for_date(
    source_file: str | Path, target_date: date, overwrite: bool = False
) -> Path:
    """원본 파일을 복사하여 target_date 날짜의 파일을 생성한다."""
    source_path = Path(source_file)

    if not source_path.exists():
        raise FileNotFoundError(f"원본 파일을 찾을 수 없습니다: {source_path}")

    target_path = build_date_path(source_path, target_date)

    if target_path.exists() and not overwrite:
        raise FileExistsError(f"이미 대상 파일이 존재합니다: {target_path}")

    shutil.copy2(source_path, target_path)
    _clear_daily_entries(target_path)
    return target_path


def find_missing_dates(
    source_file: str | Path, until_date: date
) -> list[date]:
    """원본 파일 날짜 다음날부터 until_date까지, 파일이 없는 날짜만 골라 반환한다."""
    source_path = Path(source_file)
    start = resolve_file_date(source_path.name, today=until_date)
    return [
        start + timedelta(days=offset)
        for offset in range(1, (until_date - start).days + 1)
        if not build_date_path(source_path, start + timedelta(days=offset)).exists()
    ]


def backfill_dailies(
    source_file: str | Path,
    until_date: date,
    max_days: int = MAX_BACKFILL_DAYS,
) -> list[Path]:
    """원본 파일 날짜 다음날부터 until_date까지 빠진 데일리 파일을 모두 만든다.

    매출이 없어 직원이 프로그램을 켜지 않은 날은 그날 파일이 아예 생기지 않는다.
    그 공백을 메워서 날짜 사슬이 끊기지 않게 한다. 양식은 그대로 두고 매출·지출
    입력값만 비운 상태로 만든다.

    복사 원본은 매번 '그 날짜 직전에 실제로 존재하는 파일'이라, 중간에 양식이
    바뀌었더라도 가장 최신 양식이 이어진다. 이미 있는 날짜는 건드리지 않는다.
    새로 만든 파일 경로를 날짜순으로 반환한다.
    """
    source_path = Path(source_file)

    if not source_path.exists():
        raise FileNotFoundError(f"원본 파일을 찾을 수 없습니다: {source_path}")

    start = resolve_file_date(source_path.name, today=until_date)
    gap = (until_date - start).days
    if gap <= 0:
        return []
    if gap > max_days:
        raise ValueError(
            f"마지막 데일리 파일({start.month}.{start.day})이 {gap}일 전 날짜입니다.\n"
            f"한 번에 {max_days}일까지만 자동 생성합니다. 데일리 파일을 직접 선택해주세요."
        )

    created: list[Path] = []
    latest = source_path
    for offset in range(1, gap + 1):
        target_path = build_date_path(source_path, start + timedelta(days=offset))
        if target_path.exists():
            latest = target_path
            continue
        try:
            _copy_blank_daily(latest, target_path)
        except Exception:
            if latest == source_path:
                raise
            # 직전 날짜 파일이 손상돼 있으면 마지막으로 멀쩡했던 원본에서 다시 복사한다.
            _copy_blank_daily(source_path, target_path)
        created.append(target_path)
        latest = target_path

    return created


def _copy_blank_daily(source: Path, target: Path) -> None:
    """source를 target으로 복사한 뒤 입력값을 비운다. 실패하면 반쯤 만들어진 파일을 지운다."""
    shutil.copy2(source, target)
    try:
        _clear_daily_entries(target)
    except Exception:
        target.unlink(missing_ok=True)
        raise


# ── 데이터 초기화 ──────────────────────────────────────────────────────────────

def _is_formula(value) -> bool:
    return isinstance(value, str) and value.startswith("=")


def _clear_value(cell) -> None:
    """수식이 아닌 경우에만 셀 값을 지운다."""
    if cell.value is not None and not _is_formula(cell.value):
        cell.value = None


def _clear_daily_entries(file_path: Path) -> None:
    """복사된 데일리 파일의 매출·지출 데이터를 초기화한다."""
    wb = openpyxl.load_workbook(str(file_path))

    sales_name = DEFAULT_SHEET_NAME          # "데일리매출"
    expense_name = get_expense_daily_sheet() # "데일리지출" (설정값)

    if sales_name in wb.sheetnames:
        _clear_sales_sheet(wb[sales_name])

    if expense_name in wb.sheetnames:
        _clear_expense_sheet(wb[expense_name])

    wb.save(str(file_path))


def _clear_sales_sheet(ws) -> None:
    """데일리매출 시트 초기화 (12행~, 센터 B-M · 레슨 P-AA).
    H·M열의 VAT/자동기타 수식은 보존한다."""
    CENTER_COLS = range(2, 14)   # B–M
    LESSON_COLS = range(16, 28)  # P–AA (레슨 섹션)

    for row_num in range(12, min(ws.max_row + 1, 400)):
        center_name = ws.cell(row_num, 4).value   # D: 회원명 (센터)
        lesson_name = ws.cell(row_num, 18).value  # R: 회원명 (레슨, 16+2)

        has_center = center_name is not None and not _is_formula(center_name)
        has_lesson = lesson_name is not None and not _is_formula(lesson_name)

        if not has_center and not has_lesson:
            continue

        for col in CENTER_COLS:
            _clear_value(ws.cell(row_num, col))
        for col in LESSON_COLS:
            _clear_value(ws.cell(row_num, col))


def _clear_expense_sheet(ws) -> None:
    """데일리지출 시트 초기화 (6행~, A-J열).
    B열 미리 채워진 순번(C열이 None인 행)은 건드리지 않는다."""
    for row_num in range(6, ws.max_row + 1):
        date_val = ws.cell(row_num, 3).value  # C: 일자 (정상 입력)
        bug_val  = ws.cell(row_num, 1).value  # A: 구버전 버그로 잘못 기록된 값

        if date_val is None and bug_val is None:
            continue  # B열 순번만 있는 빈 행 → 보존

        for col in range(1, 11):  # A–J (B열=2 번호는 보존)
            if col == 2:
                continue
            _clear_value(ws.cell(row_num, col))