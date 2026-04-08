from src.core.file_naming import build_next_date_filename

def test_build_next_date_filename():
    source = "리와인드 중산점 데일리 3.31.xlsx"
    result = build_next_date_filename(source, year = 2026)

    assert result == "리와인드 중산점 데일리 4.1.xlsx"