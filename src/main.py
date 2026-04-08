import sys

from PySide6.QtWidgets import QApplication

from src.config.constants import WINDOW_WIDTH, WINDOW_HEIGHT
from src.ui.main_window import MainWindow

def main() -> None:
    app = QApplication(sys.argv)

    window = MainWindow()
    window.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()