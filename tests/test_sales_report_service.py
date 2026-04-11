from datetime import datetime

from src.services.sales_report_service import (
    build_report_header,
    build_sales_report_text,
    format_currency,
)


class TestFormatCurrency:
    def test_thousand_separator(self):
        assert format_currency(100000) == "100,000원"

    def test_zero(self):
        assert format_currency(0) == "0원"

    def test_float_truncated(self):
        # 엑셀에서 읽힌 값이 float일 수 있음
        assert format_currency(100000.0) == "100,000원"


class TestBuildReportHeader:
    def test_tuesday(self):
        assert build_report_header(datetime(2026, 3, 31)) == "3.31 화"

    def test_saturday(self):
        assert build_report_header(datetime(2026, 4, 4)) == "4.4 토"

    def test_sunday(self):
        assert build_report_header(datetime(2026, 4, 5)) == "4.5 일"


class TestBuildSalesReportText:
    def test_full_report(self):
        sales = {
            "cash": 100000,
            "card": 200000,
            "transfer": 300000,
            "total": 600000,
        }
        report = build_sales_report_text(datetime(2026, 3, 31), sales)
        expected = (
            "3.31 화\n\n"
            "현금:\n100,000원\n\n"
            "카드:\n200,000원\n\n"
            "계좌:\n300,000원\n\n"
            "총합:\n600,000원"
        )
        assert report == expected

    def test_all_zero(self):
        sales = {"cash": 0, "card": 0, "transfer": 0, "total": 0}
        report = build_sales_report_text(datetime(2026, 4, 1), sales)
        assert "0원" in report
        assert "4.1 수" in report
