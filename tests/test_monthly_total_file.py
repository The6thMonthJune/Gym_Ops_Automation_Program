"""월별 총매는 달마다 새 파일 — 파일명 규칙과 복사 동작."""
from pathlib import Path

import pytest

from src.services.monthly_total_service import (
    build_month_file_path,
    ensure_monthly_file,
    file_month,
)


class TestBuildMonthFilePath:
    @pytest.mark.parametrize(
        ("name", "year", "month", "expected"),
        [
            ("26년 10월 총매.xlsx", 2026, 11, "26년 11월 총매.xlsx"),
            ("26.10월 총매.xlsx", 2026, 11, "26.11월 총매.xlsx"),
            ("리와인드 2026-10 총매.xlsx", 2026, 11, "리와인드 2026-11 총매.xlsx"),
            ("10월 월별총매.xlsx", 2026, 11, "11월 월별총매.xlsx"),
            ("26년 09월 총매.xlsx", 2026, 1, "26년 01월 총매.xlsx"),   # 0 채움 유지
            ("26년 9월 총매.xlsx", 2026, 1, "26년 1월 총매.xlsx"),     # 0 없음 유지
            ("26년 12월 총매.xlsx", 2027, 1, "27년 1월 총매.xlsx"),    # 연말 넘김
        ],
    )
    def test_keeps_naming_style(self, name, year, month, expected):
        assert build_month_file_path(f"/x/{name}", year, month).name == expected

    def test_explains_when_no_month_in_name(self):
        with pytest.raises(ValueError, match="직접 만들어"):
            build_month_file_path("/x/월별총매.xlsx", 2026, 11)

    def test_reads_year_and_month(self):
        assert file_month("/x/26년 10월 총매.xlsx") == (2026, 10)
        assert file_month("/x/10월 총매.xlsx") == (None, 10)
        assert file_month("/x/총매.xlsx") is None


@pytest.fixture
def october(tmp_path, monkeypatch):
    """10월 파일 하나를 만들고, 복사 후 처리는 가로채 호출만 기록한다."""
    import openpyxl

    path = tmp_path / "26년 10월 총매.xlsx"
    wb = openpyxl.Workbook()
    wb.active.title = "26.10월매출"
    wb.create_sheet("26.10월지출")
    wb.save(str(path))

    calls = []
    monkeypatch.setattr(
        "src.services.monthly_total_service._retitle_and_clear",
        lambda p, y, m, pw, sm=None: calls.append((Path(p).name, y, m)),
    )
    return path, calls


class TestEnsureMonthlyFile:
    def test_creates_november_from_october(self, october):
        path, calls = october

        created_path, created = ensure_monthly_file(path, 2026, 11)

        assert created is True
        assert created_path.name == "26년 11월 총매.xlsx"
        assert created_path.exists()
        assert path.exists()                      # 원본은 그대로
        assert calls == [("26년 11월 총매.xlsx", 2026, 11)]

    def test_returns_existing_file_without_copying(self, october):
        path, calls = october
        existing = path.with_name("26년 11월 총매.xlsx")
        existing.write_bytes(b"already here")

        resolved, created = ensure_monthly_file(path, 2026, 11)

        assert (resolved, created) == (existing, False)
        assert existing.read_bytes() == b"already here"
        assert calls == []

    def test_looks_back_when_last_month_is_missing(self, october):
        """10월 파일만 있고 11월을 건너뛰어도 12월을 만들 수 있어야 한다."""
        path, calls = october

        created_path, created = ensure_monthly_file(path, 2026, 12)

        assert created is True
        assert created_path.name == "26년 12월 총매.xlsx"

    def test_errors_when_no_source_exists(self, tmp_path):
        missing = tmp_path / "26년 10월 총매.xlsx"

        with pytest.raises(FileNotFoundError, match="이전 달 파일"):
            ensure_monthly_file(missing, 2026, 11)

    def test_half_made_file_is_removed_on_failure(self, october, monkeypatch):
        path, _ = october
        monkeypatch.setattr(
            "src.services.monthly_total_service._retitle_and_clear",
            lambda p, y, m, pw, sm=None: (_ for _ in ()).throw(RuntimeError("엑셀 오류")),
        )

        with pytest.raises(RuntimeError):
            ensure_monthly_file(path, 2026, 11)

        assert not path.with_name("26년 11월 총매.xlsx").exists()


class _Sheet:
    def __init__(self, name, book):
        self.name = name
        self._book = book
        self.cleared = False

    def range(self, start, end):
        self.cleared = True
        return type("R", (), {"formula": [[None]], "value": None})()

    def delete(self):
        self._book.sheets.remove(self)


class _App:
    display_alerts = True

    def quit(self):
        pass


class _Book:
    def __init__(self, names):
        self.sheets = []
        self.sheets.extend(_Sheet(n, self) for n in names)
        self.app = _App()
        self.saved = False

    def save(self):
        self.saved = True


class TestRetitleHandlesLeftoverSheets:
    """이전 버전이 원본에 다음 달 시트를 잘못 만들어 둬서 이름이 충돌했다."""

    def _run(self, names, source_month, monkeypatch):
        from src.services import monthly_total_service as svc

        book = _Book(names)
        monkeypatch.setattr(
            "src.services.entry_service._open_book", lambda *a, **k: (book, False)
        )
        monkeypatch.setattr(
            "src.services.entry_service._clear_keep_formulas",
            lambda *a, **k: None,
        )
        svc._retitle_and_clear(Path("x.xlsx"), 2026, 11, None, source_month)
        return book

    def test_drops_leftover_target_month_sheet(self, monkeypatch):
        book = self._run(
            ["표지", "26.10월매출", "26.10월지출", "26.11월매출", "26.11월지출"],
            source_month=10,
            monkeypatch=monkeypatch,
        )

        assert [s.name for s in book.sheets] == ["표지", "26.11월매출", "26.11월지출"]
        assert book.saved

    def test_plain_rename_when_no_conflict(self, monkeypatch):
        book = self._run(
            ["표지", "26.10월매출", "26.10월지출"], source_month=10, monkeypatch=monkeypatch
        )

        assert [s.name for s in book.sheets] == ["표지", "26.11월매출", "26.11월지출"]

    def test_leaves_sheets_without_month_alone(self, monkeypatch):
        book = self._run(
            ["매출요약", "26.10월매출"], source_month=10, monkeypatch=monkeypatch
        )

        assert "매출요약" in [s.name for s in book.sheets]   # 월 표기가 없으면 건드리지 않는다
