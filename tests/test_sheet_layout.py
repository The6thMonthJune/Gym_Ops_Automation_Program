"""매출 시트 열 배치 — 틀리면 매출이 엉뚱한 칸에 기록되므로 열 단위로 고정해둔다."""
from datetime import date

import pytest

from src.services.entry_service import (
    CURRENT_LAYOUT,
    LEGACY_LAYOUT,
    PaymentEntry,
    _col_letter,
    _offsets,
    _vat_formula,
)
from src.services.total_sales_service import find_monthly_file_sheet_name


def _columns(layout, section):
    start = layout.section_start[section]
    return {
        key: (_col_letter(start + off) if off >= 0 else None)
        for key, off in _offsets(layout, section).items()
    }


class TestCurrentLayout:
    """데일리 · 월별 총매 — 센터 종목과 회원권 사이에 신/재 칸이 있다."""

    def test_center_columns(self):
        assert _columns(CURRENT_LAYOUT, "센터") == {
            "date": "B", "day": "C", "name": "D", "category": "E",
            "membership_type": "F", "membership": "G", "amount": "H",
            "vat": "I", "payment": "J", "approval": "K", "fc": "L",
            "manager": "M", "note": "N",
        }

    def test_lesson_shifts_right_but_keeps_12_columns(self):
        cols = _columns(CURRENT_LAYOUT, "레슨")
        assert cols["date"] == "Q"          # 센터가 한 칸 늘어 P → Q
        assert cols["membership_type"] is None
        assert cols["membership"] == "U"
        assert cols["note"] == "AB"


class TestLegacyLayout:
    """전체 총매 — 신/재 칸이 없는 기존 양식."""

    def test_center_columns(self):
        cols = _columns(LEGACY_LAYOUT, "센터")
        assert cols["membership_type"] is None
        assert cols["membership"] == "F"
        assert cols["amount"] == "G"
        assert cols["note"] == "M"

    def test_lesson_starts_at_p(self):
        assert _columns(LEGACY_LAYOUT, "레슨")["date"] == "P"


class TestVatFormula:
    @pytest.mark.parametrize(
        ("layout", "section", "amount_cell", "payment_cell"),
        [
            (CURRENT_LAYOUT, "센터", "H12", "J12"),
            (CURRENT_LAYOUT, "레슨", "V12", "X12"),
            (LEGACY_LAYOUT, "센터", "G12", "I12"),
            (LEGACY_LAYOUT, "레슨", "U12", "W12"),
        ],
    )
    def test_references_shift_with_layout(self, layout, section, amount_cell, payment_cell):
        start = layout.section_start[section]
        formula = _vat_formula(section, start, 12, _offsets(layout, section))
        assert amount_cell in formula
        assert payment_cell in formula


class TestPaymentEntry:
    def test_membership_type_defaults_empty(self):
        entry = PaymentEntry(
            entry_date=date(2026, 10, 23), name="홍길동", category="헬스",
            membership="3개월", amount=300000, payment_method="카드",
        )
        assert entry.membership_type == ""


class TestMonthlyFileSheetName:
    @pytest.mark.parametrize(
        ("year", "month", "kind", "expected"),
        [
            (2026, 10, "매출", "26.10월매출"),
            (2026, 10, "지출", "26.10월지출"),
            (2026, 9, "매출", "26.9월매출"),
        ],
    )
    def test_finds_sheet(self, year, month, kind, expected):
        names = ["표지", "26.9월매출", "26.10월매출", "26.10월지출"]
        assert find_monthly_file_sheet_name(names, year, month, kind) == expected

    def test_sales_lookup_does_not_match_expense_sheet(self):
        with pytest.raises(ValueError):
            find_monthly_file_sheet_name(["26.10월지출"], 2026, 10, "매출")

    def test_missing_month_raises_with_sheet_list(self):
        with pytest.raises(ValueError, match="26.11월매출"):
            find_monthly_file_sheet_name(["26.10월매출"], 2026, 11, "매출")


class TestYearlyTotalFile:
    """연말 — 전체 총매 파일을 새 연도로 넘긴다."""

    def test_builds_next_year_name(self):
        from src.services.yearly_total_service import build_year_path

        assert build_year_path("/x/리와인드 총매출 2026.xlsx", 2027).name == \
            "리와인드 총매출 2027.xlsx"

    def test_reads_year_from_name(self):
        from src.services.yearly_total_service import file_year

        assert file_year("/x/리와인드 총매출 2026.xlsx") == 2026
        assert file_year("/x/총매출.xlsx") is None

    def test_name_without_year_explains_what_to_do(self):
        from src.services.yearly_total_service import build_year_path

        with pytest.raises(ValueError, match="직접 만들어"):
            build_year_path("/x/총매출.xlsx", 2027)

    def test_only_old_month_sheets_are_removed(self):
        from src.services.yearly_total_service import _old_month_sheet_names

        names = [
            "표지", "연간요약",
            "총 매출26년 11월", "총 지출26년 11월",
            "총 매출26년 12월", "총 지출26년 12월",
            "총 매출27년 1월", "총 지출27년 1월",
        ]
        removed = _old_month_sheet_names(names, 2027)

        assert removed == [
            "총 매출26년 11월", "총 지출26년 11월",
            "총 매출26년 12월", "총 지출26년 12월",
        ]
        assert "표지" not in removed        # 월 시트가 아닌 것은 건드리지 않는다
        assert "연간요약" not in removed


class TestReaderMatchesWriterLayout:
    """입력·조회가 서로 다른 열 배치를 들고 있어 내역 조회가 비던 적이 있다."""

    def _daily(self, tmp_path):
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "데일리매출"
        # 센터: 신/재(F) 포함 13칸
        for cell, value in [
            ("C12", 24), ("D12", "홍길동"), ("E12", "헬스"), ("F12", "신규"),
            ("G12", "헬스 3개월"), ("H12", 300000), ("J12", "카드(VAN)"), ("L12", "정준"),
        ]:
            ws[cell] = value
        # 레슨: 신/재 없이 Q열부터
        for cell, value in [
            ("R13", 24), ("S13", "김철수"), ("T13", "PT"),
            ("U13", "PT 10회"), ("V13", 900000), ("X13", "현금"),
        ]:
            ws[cell] = value
        path = tmp_path / "리와인드 데일리 10.24.xlsx"
        wb.save(str(path))
        return path

    def test_reads_both_sections_of_new_layout(self, tmp_path):
        from src.services.entry_reader_service import read_sales_entries

        rows = read_sales_entries(self._daily(tmp_path))

        assert len(rows) == 2
        center = next(r for r in rows if r.section == "센터")
        assert (center.name, center.membership_type, center.membership) == \
            ("홍길동", "신규", "헬스 3개월")
        assert center.amount == 300000      # 신/재 칸만큼 밀린 금액 열을 읽는다
        assert center.fc == "정준"

        lesson = next(r for r in rows if r.section == "레슨")
        assert (lesson.name, lesson.membership, lesson.amount) == ("김철수", "PT 10회", 900000)
        assert lesson.membership_type == ""  # 레슨에는 신/재 칸이 없다

    def test_text_in_amount_column_does_not_kill_the_whole_list(self, tmp_path):
        """양식이 또 어긋나도 조회가 통째로 비지 않고 읽히는 만큼은 보여준다."""
        import openpyxl

        from src.services.entry_reader_service import read_sales_entries

        path = self._daily(tmp_path)
        wb = openpyxl.load_workbook(str(path))
        wb["데일리매출"]["H12"] = "삼십만원"   # 금액 칸에 글자
        wb.save(str(path))

        rows = read_sales_entries(path)

        assert len(rows) == 2
        assert next(r for r in rows if r.section == "센터").amount == 0


class TestSalesSummaryCells:
    """메인 화면 새로고침이 읽는 현금/카드/계좌/총합 — 신/재 칸만큼 M → N으로 밀렸다."""

    def _book(self, tmp_path, column, name="데일리 10.28.xlsx"):
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "데일리매출"
        ws[f"{column}5"] = 50000
        ws[f"{column}6"] = 300000
        ws[f"{column}7"] = 120000
        ws[f"{column}8"] = 470000
        path = tmp_path / name
        wb.save(str(path))
        return path

    def test_reads_new_layout_at_n_column(self, tmp_path):
        from src.services.sales_report_service import read_sales_values

        values = read_sales_values(self._book(tmp_path, "N"))

        assert values == {"cash": 50000, "card": 300000, "transfer": 120000, "total": 470000}

    def test_still_reads_old_files_at_m_column(self, tmp_path):
        """예전에 만든 데일리 파일도 그대로 열려야 한다."""
        from src.services.sales_report_service import read_sales_values

        values = read_sales_values(self._book(tmp_path, "M", "데일리 9.1.xlsx"))

        assert values["total"] == 470000

    def test_empty_sheet_reports_zero_not_crash(self, tmp_path):
        import openpyxl

        from src.services.sales_report_service import read_sales_values

        wb = openpyxl.Workbook()
        wb.active.title = "데일리매출"
        path = tmp_path / "데일리 10.28.xlsx"
        wb.save(str(path))

        assert read_sales_values(path) == {"cash": 0, "card": 0, "transfer": 0, "total": 0}

    def test_summary_column_follows_layout(self):
        from src.core.sheet_layout import CURRENT_LAYOUT, LEGACY_LAYOUT, summary_cells

        assert summary_cells(CURRENT_LAYOUT)["cash"] == "N5"
        assert summary_cells(LEGACY_LAYOUT)["cash"] == "M5"


class TestNextDayFileClearing:
    """다음날 파일을 만들 때 덜 지우면 어제 매출이 남는다."""

    def test_clears_both_sections_in_new_layout(self, tmp_path, monkeypatch):
        import openpyxl

        from src.services.daily_file_service import create_next_daily_file

        monkeypatch.setattr(
            "src.services.daily_file_service.get_expense_daily_sheet", lambda: "데일리지출"
        )
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "데일리매출"
        for cell, value in [
            ("D12", "홍길동"), ("E12", "헬스"), ("F12", "신규"),
            ("G12", "3개월"), ("H12", 300000), ("N12", "비고"),
        ]:
            ws[cell] = value
        for cell, value in [
            ("S12", "김철수"), ("T12", "PT"), ("U12", "10회"),
            ("V12", 900000), ("AB12", "레슨비고"),
        ]:
            ws[cell] = value
        wb.create_sheet("데일리지출")
        source = tmp_path / "리와인드 데일리 10.28.xlsx"
        wb.save(str(source))

        created = create_next_daily_file(source)

        ws2 = openpyxl.load_workbook(str(created))["데일리매출"]
        for cell in ("D12", "E12", "F12", "G12", "H12", "N12",
                     "S12", "T12", "U12", "V12", "AB12"):
            assert ws2[cell].value is None, f"{cell}이 지워지지 않았습니다"


class TestMonthSheetName:
    """월별 총매 파일의 시트명 표기는 파일마다 다르다 — 템플릿을 그대로 따라야 한다."""

    @pytest.mark.parametrize(
        ("template", "year", "month", "expected"),
        [
            ("26.10월매출", 2026, 11, "26.11월매출"),
            ("26.10월지출", 2026, 11, "26.11월지출"),
            ("26.09월매출", 2026, 10, "26.10월매출"),   # 0 채움 유지
            ("26.12월매출", 2027, 1, "27.1월매출"),     # 연말 넘김
            ("26년 10월 매출", 2026, 11, "26년 11월 매출"),  # 구분자 유지
        ],
    )
    def test_follows_template_style(self, template, year, month, expected):
        from src.services.total_sales_service import build_month_sheet_name

        assert build_month_sheet_name(template, year, month) == expected

    def test_rejects_name_without_month(self):
        from src.services.total_sales_service import build_month_sheet_name

        with pytest.raises(ValueError, match="연·월"):
            build_month_sheet_name("표지", 2026, 11)


class _FakeRange:
    """xlwings Range 중 formula 읽기와 value 쓰기만 흉내낸다."""

    def __init__(self, formulas):
        self.formula = formulas
        self.value = None


class _FakeSheet:
    def __init__(self, formulas):
        self._range = _FakeRange(formulas)
        self.requested = None

    def range(self, start, end):
        self.requested = (start, end)
        return self._range


class TestClearKeepFormulas:
    """새 달 시트를 만들 때 값만 비워야 한다 — 부가세 수식까지 날리면 양식이 깨진다."""

    def test_keeps_formulas_and_clears_values(self):
        from src.services.entry_service import _clear_keep_formulas

        sheet = _FakeSheet([
            ["홍길동", "헬스", "=H12/11*10", 300000],
            ["", "", "=H13/11*10", ""],
        ])

        _clear_keep_formulas(sheet, 12, 13, 2, 5)

        assert sheet._range.value == [
            [None, None, "=H12/11*10", None],
            [None, None, "=H13/11*10", None],
        ]

    def test_keeps_whole_column_when_asked(self):
        """지출 시트의 B열 순번은 값이라도 남겨야 한다."""
        from src.services.entry_service import _clear_keep_formulas

        sheet = _FakeSheet([[1, "간식대", "커피", 5000]])

        _clear_keep_formulas(sheet, 6, 6, 2, 5, keep_cols={2})

        assert sheet._range.value == [[1, None, None, None]]

    def test_handles_single_row_result(self):
        """xlwings가 한 줄 범위를 평평한 튜플로 돌려줘도 깨지지 않아야 한다."""
        from src.services.entry_service import _clear_keep_formulas

        sheet = _FakeSheet(("값", "=SUM(A1)"))

        _clear_keep_formulas(sheet, 12, 12, 2, 3)

        assert sheet._range.value == [[None, "=SUM(A1)"]]


class _FakeWorkSheet(_FakeSheet):
    def __init__(self, name, formulas=None):
        super().__init__(formulas or [[None]])
        self.name = name
        self.copied_after = None

    def copy(self, after=None):
        self.copied_after = after
        clone = _FakeWorkSheet(self.name + " (복사본)", self._range.formula)
        after._book.sheets.append(clone)
        return clone


class _FakeSheets(list):
    def __getitem__(self, key):
        if isinstance(key, str):
            return next(s for s in self if s.name == key)
        return list.__getitem__(self, key)


class _FakeBook:
    def __init__(self, names):
        self.sheets = _FakeSheets(_FakeWorkSheet(n) for n in names)
        for sheet in self.sheets:
            sheet._book = self
        self.saved = False

    def save(self):
        self.saved = True


class TestMonthlyFileSheetCreation:
    """11월이 됐는데 월별 총매에 11월 시트가 안 생겨 결제 입력이 막혔다."""

    def test_returns_existing_sheet_untouched(self):
        from src.services.entry_service import _month_sheet_in_book

        book = _FakeBook(["표지", "26.10월매출", "26.11월매출"])

        assert _month_sheet_in_book(book, 2026, 11, "매출") == "26.11월매출"
        assert len(book.sheets) == 3      # 새로 만들지 않는다

    def test_creates_from_previous_month(self):
        from src.services.entry_service import _month_sheet_in_book

        book = _FakeBook(["표지", "26.10월매출", "26.10월지출"])

        name = _month_sheet_in_book(book, 2026, 11, "매출")

        assert name == "26.11월매출"
        assert [s.name for s in book.sheets][-1] == "26.11월매출"

    def test_expense_sheet_is_separate_from_sales(self):
        from src.services.entry_service import _month_sheet_in_book

        book = _FakeBook(["26.10월매출", "26.10월지출"])

        assert _month_sheet_in_book(book, 2026, 11, "지출") == "26.11월지출"

    def test_skips_back_further_when_a_month_is_missing(self):
        """9월만 있고 10월이 비어 있어도 11월을 만들 수 있어야 한다."""
        from src.services.entry_service import _month_sheet_in_book

        book = _FakeBook(["26.9월매출"])

        assert _month_sheet_in_book(book, 2026, 11, "매출") == "26.11월매출"

    def test_explains_what_to_do_when_no_template_exists(self):
        from src.services.entry_service import _month_sheet_in_book

        book = _FakeBook(["표지"])

        with pytest.raises(ValueError, match="직접 만들어"):
            _month_sheet_in_book(book, 2026, 11, "매출")

    def test_ensure_reports_only_newly_created(self, monkeypatch):
        from src.services import entry_service

        book = _FakeBook(["26.10월매출", "26.10월지출", "26.11월매출"])
        monkeypatch.setattr(entry_service, "_open_book", lambda *a, **k: (book, True))

        created = entry_service.ensure_monthly_file_sheets("x.xlsx", 2026, 11)

        assert created == ["26.11월지출"]   # 이미 있는 매출은 빼고
        assert book.saved
