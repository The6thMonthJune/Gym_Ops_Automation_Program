from datetime import datetime

from src.services.sales_report_service import build_sales_report_text

def test_build_sales_report_text():
    sales = {
        "cash": 100000,
        "card": 200000,
        "transfer": 300000,
        "total": 600000,
    }

    report = build_sales_report_text(datetime(2026,3,31), sales)

    expected = (
        "3.31 화\n\n"
        "현금:\n100,000원\n\n"
        "카드:\n200,000원\n\n"
        "계좌:\n300,000원\n\n"
        "총합:\n600,000원"

    )

    assert report == expected