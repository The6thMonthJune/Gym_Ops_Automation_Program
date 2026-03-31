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
        raise ValueError