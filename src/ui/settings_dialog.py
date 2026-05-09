from __future__ import annotations

from PySide6.QtCore import Qt
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
    _KEY_NATEON_WEBHOOK_URL,
    _KEY_PHONE_IP,
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

        self.phone_ip_input = QLineEdit()
        self.phone_ip_input.setPlaceholderText("예: 192.168.219.206")
        form.addRow("센터폰 IP:", self.phone_ip_input)

        self.nateon_webhook_input = QLineEdit()
        self.nateon_webhook_input.setPlaceholderText("https://teamroom.nate.com/api/webhook/...")
        form.addRow("네이트온 웹훅 URL:", self.nateon_webhook_input)

        layout.addLayout(form)

        save_button = QPushButton("저장")
        save_button.clicked.connect(self._save)
        layout.addWidget(save_button)

        contact = QLabel(
            "프로그램에 문제가 생기면 연락주세요.\n"
            "제작자: 정준 실장\n"
            "연락처: 010-9141-6322"
        )
        contact.setStyleSheet("color: #6B7280; font-size: 11px;")
        contact.setAlignment(Qt.AlignCenter)
        layout.addWidget(contact)

        self.setLayout(layout)

    def _load(self) -> None:
        settings = load_settings()
        self.password_input.setText(settings.get(_KEY_TOTAL_SALES_PASSWORD, ""))
        self.expense_sheet_input.setText(settings.get(_KEY_EXPENSE_DAILY_SHEET, ""))
        self.phone_ip_input.setText(settings.get(_KEY_PHONE_IP, ""))
        self.nateon_webhook_input.setText(settings.get(_KEY_NATEON_WEBHOOK_URL, ""))

    def _save(self) -> None:
        settings = load_settings()
        settings[_KEY_TOTAL_SALES_PASSWORD] = self.password_input.text()
        settings[_KEY_EXPENSE_DAILY_SHEET] = self.expense_sheet_input.text().strip()
        settings[_KEY_PHONE_IP] = self.phone_ip_input.text().strip()
        settings[_KEY_NATEON_WEBHOOK_URL] = self.nateon_webhook_input.text().strip()
        save_settings(settings)
        QMessageBox.information(self, "완료", "설정이 저장되었습니다.")
        self.accept()
