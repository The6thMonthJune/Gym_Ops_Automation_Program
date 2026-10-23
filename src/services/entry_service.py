from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import xlwings as xw

from src.services.total_sales_service import (
    find_monthly_file_sheet_name,
    find_monthly_sheet_name,
)

# 카톡 선택지 → 엑셀 기재 형식
PAYMENT_METHOD_EXCEL = {
    "카드": "카드(VAN)",
    "법인계좌": "법인계좌",
    "일반계좌": "일반계좌",
    "현금": "현금",
    "지역화폐": "지역화폐",
}

# ── 시트 양식 ────────────────────────────────────────────────────────────────
# 2026년 10월, 센터 섹션의 '종목'과 '회원권 종류' 사이에 신/재(신규·재등록) 칸이
# 생겼다. 데일리·월별 총매 파일만 바뀌었고 전체 총매 파일은 기존 양식을 쓴다.
# 센터가 한 칸 늘어난 만큼 레슨 섹션 시작 열도 P(16)에서 Q(17)로 밀린다.

@dataclass(frozen=True)
class SheetLayout:
    section_start: dict[str, int]   # 섹션별 시작 열 (1-based)
    has_membership_type: bool       # 센터 섹션에 신/재 칸이 있는지


LEGACY_LAYOUT = SheetLayout({"센터": 2, "레슨": 16}, has_membership_type=False)
CURRENT_LAYOUT = SheetLayout({"센터": 2, "레슨": 17}, has_membership_type=True)

# 하위 호환 — 기존 호출부가 참조하던 이름
SECTION_START_COL = LEGACY_LAYOUT.section_start


def _offsets(layout: SheetLayout, section: str) -> dict[str, int]:
    """섹션 시작 열을 0으로 둔 상대 위치. 신/재 칸이 없으면 그 뒤가 한 칸씩 당겨진다."""
    has_type = layout.has_membership_type and section == "센터"
    shift = 1 if has_type else 0
    return {
        "date": 0,
        "day": 1,
        "name": 2,
        "category": 3,
        "membership_type": 4 if has_type else -1,
        "membership": 4 + shift,
        "amount": 5 + shift,
        "vat": 6 + shift,
        "payment": 7 + shift,
        "approval": 8 + shift,
        "fc": 9 + shift,
        "manager": 10 + shift,
        "note": 11 + shift,
    }


@dataclass
class PaymentEntry:
    entry_date: date
    name: str                    # 회원명
    category: str                # 종목 (헬스 / PT / PTEV / 락카 / 일일권 …)
    membership: str              # 회원권 종류
    amount: int                  # 금액 (부가세 포함)
    payment_method: str          # 카드 / 법인계좌 / 일반계좌 / 현금
    section: str = "센터"        # 매출 구분: 센터 or 레슨
    approval_number: str = ""    # 카드 승인번호 (선택)
    fc: str = ""                 # FC 담당자 (선택)
    manager: str = ""            # 담당 (선택)
    note: str = ""               # 기타 / 특이사항 (선택)
    membership_type: str = ""    # 신/재 — 신규 / 재등 / 기존 (신규 양식 전용)

    @property
    def payment_method_excel(self) -> str:
        return PAYMENT_METHOD_EXCEL.get(self.payment_method, self.payment_method)


# ── xlwings 헬퍼 ────────────────────────────────────────────────────────────

def _open_book(path: str | Path, password: str | None = None) -> tuple:
    """
    파일이 이미 Excel에서 열려 있으면 그 인스턴스에 연결하고,
    아니면 숨김 Excel 인스턴스를 생성해서 파일을 열어 반환한다.

    Returns:
        (book, was_already_open)
        was_already_open=True 이면 호출자가 book.app.quit()를 하면 안 된다.
    """
    resolved = Path(path).resolve()

    # 실행 중인 Excel 인스턴스에서 이미 열린 파일 탐색
    try:
        for app in xw.apps:
            for book in app.books:
                try:
                    if Path(book.fullname).resolve() == resolved:
                        return book, True
                except Exception:
                    continue
    except Exception:
        pass

    # 열려 있지 않으면 숨김 인스턴스로 열기
    new_app = xw.App(visible=False)
    new_app.display_alerts = False  # 모든 Excel 팝업(복사본·읽기전용 권장 등) 차단
    try:
        if password:
            book = new_app.books.open(
                str(resolved), password=password,
                update_links=0, ignore_read_only_recommended=True,
            )
        else:
            book = new_app.books.open(
                str(resolved),
                update_links=0, ignore_read_only_recommended=True,
            )
        return book, False
    except Exception:
        new_app.quit()
        raise


def _find_next_entry_row(sheet, start_row: int = 12, col: int = 4) -> int:
    """지정된 열이 None인 첫 번째 빈 행 번호를 반환한다.
    col: 1-based 컬럼 번호 (센터=D열=4, 레슨=R열=18)
    """
    for row_num in range(start_row, 2000):
        if sheet.range((row_num, col)).value is None:
            return row_num
    raise ValueError("빈 행을 찾을 수 없습니다. 엑셀 파일에 입력 행이 부족합니다.")


def _to_list(val) -> list:
    """xlwings 범위 읽기 결과를 항상 flat list로 반환한다."""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]


def _col_letter(n: int) -> str:
    """1-based 컬럼 번호를 Excel 열 문자로 변환 (1→A, 26→Z, 27→AA)."""
    result = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _vat_formula(section: str, col_start: int, row_num: int, offsets: dict[str, int]) -> str:
    """부가세 제외 금액 셀에 넣을 Excel 수식을 반환한다.
    엑셀 원본 양식의 수식과 동일하게 유지해야 다음날 파일 복사 시 양식이 깨지지 않는다.
    """
    amt = f"{_col_letter(col_start + offsets['amount'])}{row_num}"
    pay = f"{_col_letter(col_start + offsets['payment'])}{row_num}"
    if section == "레슨":
        return (
            f'=IF(OR({pay}="카드(VAN)",{pay}="카드(C-PG)",{pay}="법인계좌",'
            f'{pay}="네이버페이",{pay}="지역화폐"),{amt}/11*10,{amt})'
        )
    # 센터
    return (
        f'=IF(OR({pay}="카드(VAN)",{pay}="카드(C-PG)",{pay}="카드(P-PG)"),'
        f'{amt}/11*10,IF({pay}="네이버페이",{amt}/11*10,'
        f'IF({pay}="법인계좌",{amt}/11*10,IF({pay}="지역화폐",{amt}/11*10,{amt}))))'
    )


def _date_already_written(sheet, row_num: int, col_start: int, entry_date: date) -> bool:
    """같은 날짜가 col_start 열 12행~row_num-1행 사이에 이미 존재하면 True.
    xlwings는 셀 값을 datetime 또는 date로 반환할 수 있으므로 둘 다 처리한다.
    """
    for r in range(12, row_num):
        val = sheet.range((r, col_start)).value
        if val is None:
            continue
        if isinstance(val, datetime):
            if val.date() == entry_date:
                return True
        elif isinstance(val, date):
            if val == entry_date:
                return True
    return False


def check_duplicate(
    sheet, entry: PaymentEntry, start_row: int = 12,
    layout: SheetLayout = LEGACY_LAYOUT,
) -> bool:
    """
    같은 날짜(일) + 회원명 + 금액의 항목이 시트에 이미 존재하는지 확인한다.
    탐색 컬럼은 섹션과 시트 양식에 따라 달라진다.
    """
    col_start = layout.section_start.get(entry.section, 2)
    offsets = _offsets(layout, entry.section)
    col_day    = col_start + offsets["day"]
    col_name   = col_start + offsets["name"]
    col_amount = col_start + offsets["amount"]

    next_row = _find_next_entry_row(sheet, start_row, col=col_name)
    last_data_row = next_row - 1

    if last_data_row < start_row:
        return False

    names   = _to_list(sheet.range((start_row, col_name),   (last_data_row, col_name)).value)
    amounts = _to_list(sheet.range((start_row, col_amount), (last_data_row, col_amount)).value)
    days    = _to_list(sheet.range((start_row, col_day),    (last_data_row, col_day)).value)

    for name, amount, day in zip(names, amounts, days):
        if (
            name is not None
            and str(name).strip() == entry.name.strip()
            and amount == entry.amount
            and day == entry.entry_date.day
        ):
            return True
    return False


def _write_entry_row(
    sheet, entry: PaymentEntry, layout: SheetLayout = LEGACY_LAYOUT
) -> int:
    """시트의 다음 빈 행에 결제 내역을 기록하고 행 번호를 반환한다.
    시작 컬럼과 칸 구성은 섹션·시트 양식에 따라 달라진다.
    """
    col_start = layout.section_start.get(entry.section, 2)
    offsets = _offsets(layout, entry.section)
    col_name = col_start + offsets["name"]
    row_num = _find_next_entry_row(sheet, start_row=12, col=col_name)
    entry_datetime = datetime(
        entry.entry_date.year, entry.entry_date.month, entry.entry_date.day
    )

    # 같은 날짜가 이미 위에 기록된 경우 계약일 셀을 비워 날짜 중복 표시 방지
    date_val = (
        None
        if _date_already_written(sheet, row_num, col_start, entry.entry_date)
        else entry_datetime
    )

    values = {
        "date": date_val,
        "day": entry.entry_date.day,
        "name": entry.name,
        "category": entry.category,
        "membership_type": entry.membership_type or None,
        "membership": entry.membership,
        "amount": entry.amount,
        "vat": None,                       # 수식으로 별도 입력
        "payment": entry.payment_method_excel,
        "approval": entry.approval_number or None,
        "fc": entry.fc or None,
        "manager": entry.manager or None,
        "note": entry.note or None,
    }

    # 오프셋 순서대로 한 줄에 써야 Excel 왕복이 한 번으로 끝난다
    width = max(offsets.values()) + 1
    row: list = [None] * width
    for key, offset in offsets.items():
        if offset >= 0:
            row[offset] = values[key]
    sheet.range((row_num, col_start)).value = row

    # 부가세 제외 금액: 엑셀 원본 양식과 동일한 수식을 삽입
    sheet.range((row_num, col_start + offsets["vat"])).formula = _vat_formula(
        entry.section, col_start, row_num, offsets
    )

    return row_num


# ── 월별 시트 생성 ──────────────────────────────────────────────────────────

def create_monthly_sheet(
    total_path: str | Path,
    year: int,
    month: int,
    password: str | None = None,
) -> str:
    """
    총매출 파일에 해당 연월 매출 시트가 없으면 전월 시트를 복사해 생성한다.
    이미 존재하면 기존 시트 이름을 그대로 반환한다.

    전월 시트를 복사한 뒤 12행 이하 데이터 셀을 비워 빈 양식으로 만든다.
    """
    book, was_open = _open_book(total_path, password=password)
    try:
        sheet_names = [s.name for s in book.sheets]

        try:
            return find_monthly_sheet_name(sheet_names, year, month)
        except ValueError:
            pass

        # 전월 시트를 템플릿으로 탐색 (최대 3개월 전까지)
        template_sheet = None
        for delta in range(1, 4):
            pm = month - delta
            py = year
            while pm <= 0:
                pm += 12
                py -= 1
            try:
                prev_name = find_monthly_sheet_name(sheet_names, py, pm)
                template_sheet = book.sheets[prev_name]
                break
            except ValueError:
                continue

        two_digit_year = year % 100
        new_name = f"총 매출{two_digit_year}년 {month}월"

        if template_sheet:
            template_sheet.copy(after=book.sheets[-1])
            new_sheet = book.sheets[-1]
            new_sheet.name = new_name
            # 12행부터 데이터 클리어 (센터 B~N, 레슨 P~AB 포함 범위)
            new_sheet.range("B12:AH500").clear_contents()
            # M열 수식 복원: clear_contents로 지워지므로 재삽입
            # F열(회원권 종류)에 PT/EV 포함 시 L열(담당) 유무에 따라 배정요함/PT이벤트 표시
            new_sheet.range("M12:M500").formula = (
                '=IFERROR(IF((IFERROR(IF(FIND("EV",F12)>0,1,0),0))'
                '+(IFERROR(IF(FIND("ev",F12)>0,1,0),0))'
                '+(IFERROR(IF(FIND("pt",F12)>0,1,0),0))'
                '+(IFERROR(IF(FIND("PT",F12)>0,1,0),0))>0,'
                'IF(L12>"","PT이벤트","배정요함"),""),"")'
            )
        else:
            book.sheets.add(new_name, after=book.sheets[-1])

        book.save()
        return new_name
    finally:
        if not was_open:
            book.app.quit()


def create_monthly_expense_sheet(
    total_path: str | Path,
    year: int,
    month: int,
    password: str | None = None,
) -> str:
    """
    총매출 파일에 해당 연월 지출 시트가 없으면 전월 시트를 복사해 생성한다.
    이미 존재하면 기존 시트 이름을 그대로 반환한다.
    """
    from src.services.total_sales_service import find_monthly_expense_sheet_name

    book, was_open = _open_book(total_path, password=password)
    try:
        sheet_names = [s.name for s in book.sheets]

        try:
            return find_monthly_expense_sheet_name(sheet_names, year, month)
        except ValueError:
            pass

        template_sheet = None
        for delta in range(1, 4):
            pm = month - delta
            py = year
            while pm <= 0:
                pm += 12
                py -= 1
            try:
                prev_name = find_monthly_expense_sheet_name(sheet_names, py, pm)
                template_sheet = book.sheets[prev_name]
                break
            except ValueError:
                continue

        two_digit_year = year % 100
        new_name = f"총 지출{two_digit_year}년 {month}월"

        if template_sheet:
            template_sheet.copy(after=book.sheets[-1])
            new_sheet = book.sheets[-1]
            new_sheet.name = new_name
            new_sheet.range("B14:J500").clear_contents()
        else:
            book.sheets.add(new_name, after=book.sheets[-1])

        book.save()
        return new_name
    finally:
        if not was_open:
            book.app.quit()


# ── 공개 API ────────────────────────────────────────────────────────────────

def write_entry_to_daily(
    daily_path: str | Path,
    entry: PaymentEntry,
    force: bool = False,
) -> tuple[int | None, bool]:
    """
    데일리 파일의 '데일리매출' 시트에 결제 내역을 추가한다.

    Args:
        force: True이면 중복 체크를 건너뛰고 강제 입력한다.

    Returns:
        (row_num, is_duplicate)
        중복이 감지되고 force=False이면 row_num=None, is_duplicate=True.
    """
    book, was_open = _open_book(daily_path)
    try:
        sheet = book.sheets["데일리매출"]

        if not force and check_duplicate(sheet, entry, layout=CURRENT_LAYOUT):
            return None, True

        row_num = _write_entry_row(sheet, entry, CURRENT_LAYOUT)
        book.save()
        return row_num, False
    finally:
        if not was_open:
            book.app.quit()


def write_entry_to_total_sales(
    total_path: str | Path,
    entry: PaymentEntry,
    password: str | None = None,
    force: bool = False,
) -> tuple[int | None, bool]:
    """
    총매출 파일의 해당 연/월 시트에 결제 내역을 추가한다.

    Args:
        force: True이면 중복 체크를 건너뛰고 강제 입력한다.

    Returns:
        (row_num, is_duplicate)
    """
    book, was_open = _open_book(total_path, password=password)
    try:
        sheet_names = [s.name for s in book.sheets]
        sheet_name = find_monthly_sheet_name(
            sheet_names, entry.entry_date.year, entry.entry_date.month
        )
        sheet = book.sheets[sheet_name]

        # 전체 총매는 신/재 칸이 없는 기존 양식을 그대로 쓴다
        if not force and check_duplicate(sheet, entry, layout=LEGACY_LAYOUT):
            return None, True

        row_num = _write_entry_row(sheet, entry, LEGACY_LAYOUT)
        book.save()
        return row_num, False
    finally:
        if not was_open:
            book.app.quit()


def write_entry_to_monthly_total(
    monthly_path: str | Path,
    entry: PaymentEntry,
    password: str | None = None,
    force: bool = False,
) -> tuple[int | None, bool]:
    """월별 총매 파일의 해당 연월 매출 시트에 결제 내역을 추가한다.

    데일리와 같은 양식(신/재 칸 포함)이고, 시트명만 '26.10월매출' 형태로 다르다.

    Returns:
        (row_num, is_duplicate)
    """
    book, was_open = _open_book(monthly_path, password=password)
    try:
        sheet_name = find_monthly_file_sheet_name(
            [s.name for s in book.sheets],
            entry.entry_date.year, entry.entry_date.month, "매출",
        )
        sheet = book.sheets[sheet_name]

        if not force and check_duplicate(sheet, entry, layout=CURRENT_LAYOUT):
            return None, True

        row_num = _write_entry_row(sheet, entry, CURRENT_LAYOUT)
        book.save()
        return row_num, False
    finally:
        if not was_open:
            book.app.quit()
