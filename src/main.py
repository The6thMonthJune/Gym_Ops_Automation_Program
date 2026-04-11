import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from src.config.constants import WINDOW_WIDTH, WINDOW_HEIGHT
from src.ui.main_window import MainWindow

# 아이콘 경로: EXE로 빌드된 경우와 개발 환경 모두 대응
_ICON_PATH = Path(__file__).resolve().parents[1] / "assets" / "icon.ico"


def main() -> None:
    app = QApplication(sys.argv)

    if _ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(_ICON_PATH)))

    window = MainWindow()
    window.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
