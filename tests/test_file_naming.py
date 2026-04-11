import pytest

from src.core.file_naming import (
    build_next_date_filename,
    extract_date_from_filename,
    ParsedFilenameDate,
)


class TestExtractDateFromFilename:
    def test_basic(self):
        result = extract_date_from_filename("리와인드 중산점 데일리 3.31.xlsx")
        assert result == ParsedFilenameDate(month=3, day=31)

    def test_single_digit_month_and_day(self):
        result = extract_date_from_filename("리와인드 중산점 데일리 4.1.xlsx")
        assert result == ParsedFilenameDate(month=4, day=1)

    def test_no_date_raises(self):
        with pytest.raises(ValueError, match="날짜 패턴"):
            extract_date_from_filename("리와인드 중산점 데일리 양식.xlsx")


class TestBuildNextDateFilename:
    def test_month_boundary(self):
        # 3.31 → 4.1 (월 경계 넘어가기)
        result = build_next_date_filename("리와인드 중산점 데일리 3.31.xlsx", year=2026)
        assert result == "리와인드 중산점 데일리 4.1.xlsx"

    def test_within_month(self):
        result = build_next_date_filename("리와인드 중산점 데일리 4.1.xlsx", year=2026)
        assert result == "리와인드 중산점 데일리 4.2.xlsx"

    def test_year_boundary(self):
        # 12.31 → 1.1 (연말 경계)
        result = build_next_date_filename("리와인드 중산점 데일리 12.31.xlsx", year=2025)
        assert result == "리와인드 중산점 데일리 1.1.xlsx"

    def test_stem_only_replaced_once(self):
        # 파일명에 날짜처럼 보이는 숫자가 두 번 있을 때 한 번만 치환되어야 함
        result = build_next_date_filename("4.1 데일리 4.1.xlsx", year=2026)
        assert result == "4.2 데일리 4.1.xlsx"
