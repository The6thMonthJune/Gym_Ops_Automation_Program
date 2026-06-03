import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from src.config.constants import WINDOW_WIDTH, WINDOW_HEIGHT
from src.ui.main_window import APP_QSS, MainWindow

# 아이콘 경로: EXE로 빌드된 경우와 개발 환경 모두 대응
_ICON_PATH = Path(__file__).resolve().parents[1] / "assets" / "아이콘.ico"


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # QSS가 모든 OS에서 일관되게 적용되도록 강제
    app.setStyleSheet(APP_QSS)  # 다크모드 무관하게 라이트 테마 고정

    if _ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(_ICON_PATH)))

    window = MainWindow()
    window.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
