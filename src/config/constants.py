DEFAULT_SHEET_NAME = "데일리매출"

# 매출 요약 셀 위치는 양식에 따라 움직이므로 src/core/sheet_layout 에서 계산한다.
# (신/재 칸이 생기며 M열 → N열) 여기에 다시 상수로 박아두지 말 것.

APP_VERSION = "3.3.1"
APP_NAME = f"리와인드 휘트니스 전산 자동화 프로그램 v{APP_VERSION}"
WINDOW_WIDTH = 500
WINDOW_HEIGHT = 770

# 매출 결제수단 — 지역화폐 추가 시 이 목록 한 곳만 수정
PAYMENT_METHODS: list[str] = ["카드", "법인계좌", "일반계좌", "현금", "지역화폐"]

# 매출 종목
SALES_CATEGORIES: list[str] = ["헬스", "PT", "PTEV", "락카", "일일권", "GX", "필라테스", "골프"]
LESSON_ONLY_CATEGORIES: list[str] = ["PT", "필라테스", "골프"]
