from __future__ import annotations
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

DATE_PATTERN = re.compile(r"(?P<month>\d{1,2})\.(?P<day>\d{1,2})")

# 파일명에는 연도가 없다. 연말·연초에 파일 날짜의 연도를 추론할 때 쓰는 허용 범위.
_YEAR_GUESS_WINDOW_DAYS = 183

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


def resolve_file_date(filename: str, today: date | None = None) -> date:
    """
    파일명의 'M.D'에 연도를 붙여 실제 날짜로 변환한다.

    파일명에 연도가 없으므로 오늘 날짜와 가장 가까운 연도를 고른다.
    1월 2일에 '12.31' 파일을 보면 올해가 아니라 작년 12월 31일로 해석한다.
    """
    today = today or date.today()
    parsed = extract_date_from_filename(filename)

    for year in (today.year, today.year - 1, today.year + 1):
        try:
            candidate = date(year, parsed.month, parsed.day)
        except ValueError:
            continue  # 윤년이 아닌 해의 2.29
        if abs((candidate - today).days) <= _YEAR_GUESS_WINDOW_DAYS:
            return candidate

    return parsed.to_date(today.year)


def build_date_filename(file_path: str | Path, target_date: date) -> str:
    """
    파일명의 날짜 부분을 target_date로 교체한 새 파일명을 반환한다.

    Example:
        ('리와인드 중산점 데일리 3.31.xlsx', date(2026, 4, 2)) -> '리와인드 중산점 데일리 4.2.xlsx'
    """
    filename = Path(file_path).name
    match = DATE_PATTERN.search(filename)
    if not match:
        raise ValueError(f"파일명에서 날짜 패턴(M.D 또는 MM.DD)을 찾을 수 없습니다: {filename}")

    new_date_str = f"{target_date.month}.{target_date.day}"
    return filename[:match.start()] + new_date_str + filename[match.end():]


def build_date_path(file_path: str | Path, target_date: date) -> Path:
    """원본과 같은 폴더에서 날짜만 target_date로 바뀐 경로를 반환한다."""
    path = Path(file_path)
    return path.with_name(build_date_filename(path, target_date))


def build_next_date_filename(file_path: str | Path, year: int | None) -> str:
    """
    파일명에 포함된 날짜를 하루 증가시킨 새 파일명을 반환한다.

    Example:
        '리와인드 중산점 데일리 3.31.xlsx' -> '리와인드 중산점 데일리 4.1.xlsx'
    """
    path = Path(file_path)
    parsed = extract_date_from_filename(path.name)
    current_date = parsed.to_date(year or date.today().year)
    return build_date_filename(path, current_date + timedelta(days=1))

def build_next_date_path(file_path: str | Path, year: int | None = None) -> Path:
    """
    원본 파일 경로를 기준으로 하루 뒤 날짜가 반영된 새 경로를 반환한다.
    """

    path = Path(file_path)
    new_filename = build_next_date_filename(path, year = year)
    return path.with_name(new_filename)
