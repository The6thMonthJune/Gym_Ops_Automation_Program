from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import holidays as holidays_lib

WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]
WEEKDAY_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTH_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# 라이브러리가 반환하는 한국어 이름 → 영어 이름
_KO_TO_EN: dict[str, str] = {
    "신정": "New Year's Day",
    "삼일절": "Independence Movement Day",
    "어린이날": "Children's Day",
    "현충일": "Memorial Day",
    "광복절": "Liberation Day",
    "추석": "Chuseok",
    "추석 전날": "Chuseok Eve",
    "추석 다음날": "Chuseok Holiday",
    "개천절": "National Foundation Day",
    "한글날": "Hangul Day",
    "크리스마스": "Christmas Day",
    "기독탄신일": "Christmas Day",
    "설날": "Lunar New Year",
    "설날 전날": "Lunar New Year Eve",
    "설날 다음날": "Lunar New Year Holiday",
    # 대체공휴일 패턴
    "어린이날 대체공휴일": "Children's Day (substitute)",
    "삼일절 대체공휴일": "Independence Movement Day (substitute)",
    "광복절 대체공휴일": "Liberation Day (substitute)",
    "개천절 대체공휴일": "National Foundation Day (substitute)",
    "한글날 대체공휴일": "Hangul Day (substitute)",
    "크리스마스 대체공휴일": "Christmas Day (substitute)",
    "기독탄신일 대체공휴일": "Christmas Day (substitute)",
    "설날 대체공휴일": "Lunar New Year (substitute)",
    "추석 대체공휴일": "Chuseok (substitute)",
}


@dataclass
class HolidayInfo:
    date: date
    name_ko: str
    name_en: str
    is_extra: bool = False  # 수동 추가 임시공휴일 여부


def _ko_to_en(name_ko: str) -> str:
    """한국어 공휴일 이름을 영어로 변환. 매핑 없으면 원문 반환."""
    if name_ko in _KO_TO_EN:
        return _KO_TO_EN[name_ko]
    # 대체공휴일 패턴 fallback
    if "대체공휴일" in name_ko:
        base = name_ko.replace(" 대체공휴일", "")
        base_en = _KO_TO_EN.get(base, base)
        return f"{base_en} (substitute)"
    return name_ko


def get_month_holidays(
    year: int,
    month: int,
    extras: list[HolidayInfo] | None = None,
) -> list[HolidayInfo]:
    """해당 월의 공휴일 목록을 반환한다. extras는 수동 추가 임시공휴일."""
    kr = holidays_lib.KR(years=year)
    result: list[HolidayInfo] = []

    for d, name_ko in kr.items():
        if d.month == month:
            result.append(HolidayInfo(
                date=d,
                name_ko=name_ko,
                name_en=_ko_to_en(name_ko),
            ))

    if extras:
        for h in extras:
            if h.date.year == year and h.date.month == month:
                result.append(h)

    result.sort(key=lambda h: h.date)
    return result


def format_line_ko(h: HolidayInfo) -> str:
    wd = WEEKDAY_KR[h.date.weekday()]
    return f"{h.date.month}/{h.date.day}({wd}) {h.name_ko} — 12시~20시 운영"


def format_line_en(h: HolidayInfo) -> str:
    wd = WEEKDAY_EN[h.date.weekday()]
    mon = MONTH_EN[h.date.month - 1]
    return f"{mon} {h.date.day}({wd}) {h.name_en} — 12PM~8PM"


def build_sms_text(holidays: list[HolidayInfo]) -> str:
    """공휴일 목록으로 한/영 이중 언어 SMS 문구를 반환한다."""
    if not holidays:
        return ""
    ko_lines = "\n".join(format_line_ko(h) for h in holidays)
    en_lines = "\n".join(format_line_en(h) for h in holidays)
    return (
        "[리와인드 휘트니스]\n"
        f"이번 달 공휴일 안내\n"
        f"{ko_lines}\n\n"
        "[Rewind Fitness]\n"
        f"Holiday hours this month\n"
        f"{en_lines}"
    )
