DEFAULT_SHEET_NAME = "데일리매출"

DEFAULT_CASH_CELL = "M5"
DEFAULT_CARD_CELL = "M6"
DEFAULT_TRANSFER_CELL = "M7"
DEFAULT_TOTAL_CELL = "M8"

APP_VERSION = "2.4.2"
APP_NAME = f"리와인드 휘트니스 전산 자동화 프로그램 v{APP_VERSION}"
WINDOW_WIDTH = 500
WINDOW_HEIGHT = 680

# 매출 결제수단 — 지역화폐 추가 시 이 목록 한 곳만 수정
PAYMENT_METHODS: list[str] = ["카드", "법인계좌", "일반계좌", "현금", "지역화폐"]

# 매출 종목
SALES_CATEGORIES: list[str] = ["헬스", "PT", "PTEV", "락카", "일일권", "GX", "필라테스", "골프"]
LESSON_ONLY_CATEGORIES: list[str] = ["PT", "필라테스", "골프"]
