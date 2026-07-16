from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import gspread
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

_SETTINGS_DIR = Path(os.environ.get("APPDATA", "~")).expanduser() / "리와인드자동화"
_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# 스프레드시트 구조 상수
_DAILY_HEADER_ROW = 3
_DAILY_DATA_START = 4
_DAILY_DATA_END = 16
_MONTHLY_HEADER_ROW = 18
_MONTHLY_DATA_START = 19


def _sheet_name_for(year: int, month: int) -> str:
    return f"{str(year)[2:]}년 {month:02d}월"


def get_client(credentials_path: str = "") -> gspread.Client:
    """OAuth 인증을 거쳐 gspread 클라이언트를 반환한다. 최초 실행 시 브라우저가 열린다."""
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    token_path = _SETTINGS_DIR / "google_token.json"
    creds_path = Path(credentials_path) if credentials_path else _SETTINGS_DIR / "google_credentials.json"

    creds: Credentials | None = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), _SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not creds_path.exists():
                raise FileNotFoundError(
                    f"Google 인증 파일({creds_path.name})을 찾을 수 없습니다.\n\n"
                    "설정에서 Google 인증 파일(credentials.json) 경로를 지정해주세요.\n"
                    "파일은 Google Cloud Console → API 및 서비스 → 사용자 인증 정보에서 발급합니다."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), _SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return gspread.Client(auth=creds)


def _get_month_sheet(
    client: gspread.Client, spreadsheet_id: str, year: int, month: int
) -> gspread.Worksheet:
    spreadsheet = client.open_by_key(spreadsheet_id)
    name = _sheet_name_for(year, month)
    try:
        return spreadsheet.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        raise ValueError(f"시트를 찾을 수 없습니다: {name}")


def get_or_create_month_sheet(
    client: gspread.Client, spreadsheet_id: str, year: int, month: int
) -> gspread.Worksheet:
    """해당 월 시트가 없으면 전월 시트를 복사·초기화해서 생성한다."""
    spreadsheet = client.open_by_key(spreadsheet_id)
    name = _sheet_name_for(year, month)
    try:
        return spreadsheet.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        prev_month = month - 1 if month > 1 else 12
        prev_year = year if month > 1 else year - 1
        prev_name = _sheet_name_for(prev_year, prev_month)
        try:
            prev_ws = spreadsheet.worksheet(prev_name)
        except gspread.exceptions.WorksheetNotFound:
            raise ValueError(
                f"전월 시트({prev_name})가 없어 {name} 시트를 생성할 수 없습니다."
            )
        new_ws = spreadsheet.duplicate_sheet(
            source_sheet_id=prev_ws.id,
            new_sheet_name=name,
            insert_sheet_index=len(spreadsheet.worksheets()),
        )
        # 데일리·월별 데이터 영역 초기화
        new_ws.batch_clear([
            f"B{_DAILY_DATA_START}:I{_DAILY_DATA_END}",
            f"B{_MONTHLY_DATA_START}:I1000",
        ])
        return new_ws


def append_daily_entry(ws: gspread.Worksheet, entry: dict) -> int:
    """데일리예약 섹션(rows 4~16)에 새 행을 추가한다. 삽입된 row 번호를 반환한다."""
    daily_data = ws.get(f"B{_DAILY_DATA_START}:I{_DAILY_DATA_END}") or []

    insert_row = _DAILY_DATA_START
    for i, row in enumerate(daily_data):
        if any(str(cell).strip() for cell in row):
            insert_row = _DAILY_DATA_START + i + 1
        else:
            break

    if insert_row > _DAILY_DATA_END:
        raise RuntimeError(
            "데일리예약 섹션이 가득 찼습니다 (최대 13건).\n"
            "실장 기능에서 월별 이동을 먼저 실행해주세요."
        )

    today = date.today().strftime("%m/%d")
    row_data = [
        today,
        entry.get("name", ""),
        entry.get("phone", ""),
        entry.get("visit_date", ""),
        entry.get("category", ""),
        entry.get("amount", ""),
        entry.get("is_new", ""),
        entry.get("notes", ""),
    ]
    ws.update(f"B{insert_row}:I{insert_row}", [row_data])
    return insert_row


def get_todays_visitors(
    spreadsheet_id: str, credentials_path: str = ""
) -> list[dict]:
    """방문예정일이 오늘인 회원 목록(이름, 전화번호)을 반환한다."""
    today_str = date.today().strftime("%m/%d")
    client = get_client(credentials_path)
    today = date.today()
    ws = _get_month_sheet(client, spreadsheet_id, today.year, today.month)

    daily = ws.get(f"B{_DAILY_DATA_START}:I{_DAILY_DATA_END}") or []
    monthly = ws.get(f"B{_MONTHLY_DATA_START}:I1000") or []

    visitors: list[dict] = []
    for row in daily + monthly:
        if len(row) >= 4 and str(row[3]).strip() == today_str:
            visitors.append({
                "name": row[1] if len(row) > 1 else "",
                "phone": row[2] if len(row) > 2 else "",
            })
    return visitors


def do_daily_rollover(
    spreadsheet_id: str, credentials_path: str = ""
) -> int:
    """데일리예약 섹션 데이터를 월별 섹션으로 이동한다. 이동한 행 수를 반환한다."""
    client = get_client(credentials_path)
    today = date.today()
    ws = _get_month_sheet(client, spreadsheet_id, today.year, today.month)

    daily_data = ws.get(f"B{_DAILY_DATA_START}:I{_DAILY_DATA_END}") or []
    data_rows = [r for r in daily_data if any(str(c).strip() for c in r)]
    if not data_rows:
        return 0

    monthly_col = ws.col_values(2)  # B열 (예약일)
    append_row = _MONTHLY_DATA_START
    for i in range(_MONTHLY_DATA_START - 1, len(monthly_col)):
        if monthly_col[i].strip():
            append_row = i + 2  # 다음 빈 행

    # 각 행을 8열(B~I)로 패딩
    padded = [r + [""] * (8 - len(r)) for r in data_rows]
    ws.update(
        f"B{append_row}:I{append_row + len(padded) - 1}",
        padded,
        value_input_option="USER_ENTERED",
    )
    ws.batch_clear([f"B{_DAILY_DATA_START}:I{_DAILY_DATA_END}"])
    return len(data_rows)


def find_existing_entry(ws: gspread.Worksheet, name: str, phone: str) -> tuple[int | None, str]:
    """성함+전화번호로 기존 상담 행을 찾는다. (데일리 → 월별 순서)
    Returns (row_number, existing_notes) or (None, "")
    """
    daily_data = ws.get(f"B{_DAILY_DATA_START}:I{_DAILY_DATA_END}") or []
    for i, row in enumerate(daily_data):
        if len(row) >= 3 and str(row[1]).strip() == name and str(row[2]).strip() == phone:
            return _DAILY_DATA_START + i, str(row[7]).strip() if len(row) > 7 else ""

    monthly_data = ws.get(f"B{_MONTHLY_DATA_START}:I1000") or []
    for i, row in enumerate(monthly_data):
        if len(row) >= 3 and str(row[1]).strip() == name and str(row[2]).strip() == phone:
            return _MONTHLY_DATA_START + i, str(row[7]).strip() if len(row) > 7 else ""

    return None, ""


def update_entry_notes(ws: gspread.Worksheet, row_num: int, existing_notes: str, new_notes: str) -> None:
    """기존 행의 내용(I열)에 새 내용을 줄바꿈으로 이어붙인다."""
    merged = f"{existing_notes}\n{new_notes}" if existing_notes else new_notes
    ws.update(f"I{row_num}", [[merged]])


def build_kakao_message(entry: dict, is_update: bool = False) -> str:
    """상담 입력 내용을 카톡 보고 문구로 포맷한다."""
    today = date.today().strftime("%m/%d")
    category = entry.get("category", "")
    action = "상담 업데이트" if is_update else "상담 발생"
    lines = [
        f"📋 {action} ({today})",
        "─" * 16,
        f"👤 {entry.get('name', '')}  |  {entry.get('phone', '')}",
    ]
    if category:
        lines.append(f"🏋 종목: {category}")
    lines += [
        f"💰 금액: {entry.get('amount', '')}  ({entry.get('is_new', '')})",
        f"📆 방문예정: {entry.get('visit_date', '')}",
    ]
    notes = entry.get("notes", "").strip()
    if notes:
        lines += ["─" * 16, notes]
    return "\n".join(lines)
