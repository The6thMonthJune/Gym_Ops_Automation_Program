from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from src.config.settings import (
    _KEY_EXPENSE_DAILY_SHEET,
    _KEY_TOTAL_SALES_PASSWORD,
    load_settings,
    save_settings,
)


class SettingsDialog(QDialog):
    """
    총매출 파일 비밀번호를 입력·저장하는 설정 다이얼로그.
    저장된 값은 %APPDATA%\\리와인드자동화\\settings.json에 기록되며
    Git에는 올라가지 않는다.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("설정")
        self.setMinimumWidth(380)
        self._setup_ui()
        self._load()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()

        layout.addWidget(
            QLabel("저장된 설정은 이 PC에만 보관되며 GitHub에 올라가지 않습니다.")
        )

        form = QFormLayout()

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("총매출 파일 비밀번호 (없으면 공란)")
        form.addRow("총매출 파일 비밀번호:", self.password_input)

        self.expense_sheet_input = QLineEdit()
        self.expense_sheet_input.setPlaceholderText("기본값: 데일리지출 (변경 시에만 입력)")
        form.addRow("지출 시트 이름:", self.expense_sheet_input)

        layout.addLayout(form)

        save_button = QPushButton("저장")
        save_button.clicked.connect(self._save)
        layout.addWidget(save_button)

        self.setLayout(layout)

    def _load(self) -> None:
        settings = load_settings()
        self.password_input.setText(settings.get(_KEY_TOTAL_SALES_PASSWORD, ""))
        self.expense_sheet_input.setText(settings.get(_KEY_EXPENSE_DAILY_SHEET, ""))

    def _save(self) -> None:
        settings = load_settings()
        settings[_KEY_TOTAL_SALES_PASSWORD] = self.password_input.text()
        settings[_KEY_EXPENSE_DAILY_SHEET] = self.expense_sheet_input.text().strip()
        save_settings(settings)
        QMessageBox.information(self, "완료", "설정이 저장되었습니다.")
        self.accept()
