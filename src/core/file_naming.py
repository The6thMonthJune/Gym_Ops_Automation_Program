from __future__ import annotations
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

DATE_PATTERN = re.compile(r"(?P<month>\d{1, 2})\.(?P<day>\d{1,2})")

@dataclass(frozen=True)
class ParsedFilenameDate:
    month: int
    day: int

    def to_date(self, year: int) -> date:
        return date(year, self.month, self.day)
    
def extract_date_from_filename(filename: str) -> ParsedFilenameDate:
    """
    파일명에서 '3.31' 같은 날짜 패턴을 추출한다.

    Example:
        '리와인드 중산점 데일리 3.31.xlsx' -> ParsedFilenameDate(month=3, day=31)
    """
    match = DATE_PATTERN.search(filename)
    if not match:
        raise ValueError(f"파일명에서 날짜 패턴(M.D 또는 MM.DD)을 찾을 수 없습니다: {filename}")

    month = int(match.group("month"))
    day = int(match.group("day"))

    return ParsedFilenameDate(month= month, day= day)

def build_next_date_filename(file_path: str | Path, year: int | None) -> str:
    """
    파일명에 포함된 날짜를 하루 증가시킨 새 파일명을 반환한다.

    Example:
        '리와인드 중산점 데일리 3.31.xlsx' -> '리와인드 중산점 데일리 4.1.xlsx'
    """
    path = Path(file_path)
    filename = path.name

    parsed = extract_month_day_from_filename(file)
    current_year = year or date.today().year
    current_date = parsed.to_date(current_year)
    next_date = current_date + timedelta(days = 1)

    old_date_str = f"{parsed.month}.{parsed.day}"
    new_date_str = f"{next_date.month}.{next_date.day}"

    new_filename = filename.replace(old_date_str, new_date_str, 1)
    return new_filename

def build_next_date_path(file_path: str | Path, year: int | None = None) -> Path:
    """
    원본 파일 경로를 기준으로 하루 뒤 날짜가 반영된 새 경로를 반환한다.
    """

    path = Path(file_path)
    new_filename = build_next_date_filename(path, year = year)
    return path.with_name(new_filename)