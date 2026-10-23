"""매출 시트의 열 배치.

입력·조회·수정이 각자 열 위치를 하드코딩하고 있던 탓에, 양식이 바뀌었을 때
입력만 고치고 조회가 깨지는 일이 있었다. 열 배치는 이 모듈 한 곳에서만 정의한다.

2026년 10월, 센터 섹션의 '종목'과 '회원권 종류' 사이에 신/재(신규·재등록) 칸이
들어갔다. 데일리·월별 총매 파일만 바뀌었고 전체 총매 파일은 기존 양식을 쓴다.
센터가 한 칸 늘어난 만큼 레슨 섹션 시작 열도 P(16)에서 Q(17)로 밀린다.
"""
from __future__ import annotations

from dataclasses import dataclass

# 매출 데이터가 시작되는 행
SALES_START_ROW = 12

# 섹션 시작 열 기준 상대 위치의 기준 순서
FIELD_ORDER = (
    "date", "day", "name", "category", "membership_type", "membership",
    "amount", "vat", "payment", "approval", "fc", "manager", "note",
)


@dataclass(frozen=True)
class SheetLayout:
    section_start: dict[str, int]   # 섹션별 시작 열 (1-based)
    has_membership_type: bool       # 센터 섹션에 신/재 칸이 있는지


# 전체 총매 — 신/재 칸이 없는 기존 12칸 양식
LEGACY_LAYOUT = SheetLayout({"센터": 2, "레슨": 16}, has_membership_type=False)
# 데일리 · 월별 총매 — 센터에 신/재 칸이 있는 13칸 양식
CURRENT_LAYOUT = SheetLayout({"센터": 2, "레슨": 17}, has_membership_type=True)


def offsets(layout: SheetLayout, section: str) -> dict[str, int]:
    """섹션 시작 열을 0으로 둔 상대 위치.

    신/재 칸이 없는 섹션에서는 membership_type이 -1(없음)이고 그 뒤가 한 칸씩 당겨진다.
    """
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


def section_width(layout: SheetLayout, section: str) -> int:
    """섹션이 차지하는 열 개수."""
    return max(offsets(layout, section).values()) + 1


def last_column(layout: SheetLayout) -> int:
    """시트에서 읽어야 할 마지막 열 번호."""
    return max(
        start + section_width(layout, section) - 1
        for section, start in layout.section_start.items()
    )


def col_letter(n: int) -> str:
    """1-based 컬럼 번호를 Excel 열 문자로 변환 (1→A, 26→Z, 27→AA)."""
    result = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        result = chr(65 + remainder) + result
    return result
