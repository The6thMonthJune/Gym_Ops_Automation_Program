from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from src.config.settings import (
    _KEY_APARTMENT_COMPLEXES,
    _KEY_BROJ_PASSWORD,
    _KEY_BROJ_USERNAME,
    _KEY_CONSULT_SPREADSHEET_ID,
    _KEY_EXPENSE_DAILY_SHEET,
    _KEY_GOOGLE_CREDENTIALS_PATH,
    _KEY_NATEON_WEBHOOK_URL,
    _KEY_PHONE_IP,
    _KEY_SMS_GATEWAY_PASSWORD,
    _KEY_SMS_GATEWAY_PORT,
    _KEY_SMS_GATEWAY_USERNAME,
    _KEY_SMS_TEST_PHONE,
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

        self.sms_port_input = QLineEdit()
        self.sms_port_input.setPlaceholderText("기본값: 8080")
        form.addRow("SMS Gateway 포트:", self.sms_port_input)

        self.sms_username_input = QLineEdit()
        self.sms_username_input.setPlaceholderText("기본값: user")
        form.addRow("SMS Gateway 사용자명:", self.sms_username_input)

        self.sms_password_input = QLineEdit()
        self.sms_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.sms_password_input.setPlaceholderText("기본값: password")
        form.addRow("SMS Gateway 비밀번호:", self.sms_password_input)

        self.sms_test_phone_input = QLineEdit()
        self.sms_test_phone_input.setPlaceholderText("예: 01012345678  (테스트 발송 전용)")
        form.addRow("SMS 테스트 번호:", self.sms_test_phone_input)

        self.broj_username_input = QLineEdit()
        self.broj_username_input.setPlaceholderText("브로제이 로그인 이메일 또는 아이디")
        form.addRow("브로제이 아이디:", self.broj_username_input)

        self.broj_password_input = QLineEdit()
        self.broj_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.broj_password_input.setPlaceholderText("브로제이 비밀번호")
        form.addRow("브로제이 비밀번호:", self.broj_password_input)

        self.consult_sheet_id_input = QLineEdit()
        self.consult_sheet_id_input.setPlaceholderText(
            "구글 시트 URL의 /d/ 뒤 문자열"
        )
        form.addRow("상담관리 시트 ID:", self.consult_sheet_id_input)

        self.google_creds_path_input = QLineEdit()
        self.google_creds_path_input.setPlaceholderText(
            "Google credentials.json 파일 경로 (없으면 %APPDATA%\\리와인드자동화\\google_credentials.json)"
        )
        form.addRow("Google 인증 파일 경로:", self.google_creds_path_input)

        layout.addLayout(form)

        # 아파트 단지 목록 편집
        layout.addWidget(QLabel("아파트 단지 목록 (신규 회원 거주지 선택에 사용)"))

        self._apt_list = QListWidget()
        self._apt_list.setFixedHeight(120)
        layout.addWidget(self._apt_list)

        apt_row = QHBoxLayout()
        self._apt_input = QLineEdit()
        self._apt_input.setPlaceholderText("단지명 입력 후 추가")
        apt_row.addWidget(self._apt_input)

        add_btn = QPushButton("추가")
        add_btn.setFixedWidth(52)
        add_btn.clicked.connect(self._add_apt)
        apt_row.addWidget(add_btn)

        del_btn = QPushButton("삭제")
        del_btn.setFixedWidth(52)
        del_btn.clicked.connect(self._del_apt)
        apt_row.addWidget(del_btn)

        layout.addLayout(apt_row)

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
        self.sms_port_input.setText(str(settings.get(_KEY_SMS_GATEWAY_PORT, "") or ""))
        self.sms_username_input.setText(settings.get(_KEY_SMS_GATEWAY_USERNAME, ""))
        self.sms_password_input.setText(settings.get(_KEY_SMS_GATEWAY_PASSWORD, ""))
        self.sms_test_phone_input.setText(settings.get(_KEY_SMS_TEST_PHONE, ""))
        self.broj_username_input.setText(settings.get(_KEY_BROJ_USERNAME, ""))
        self.broj_password_input.setText(settings.get(_KEY_BROJ_PASSWORD, ""))
        self.consult_sheet_id_input.setText(settings.get(_KEY_CONSULT_SPREADSHEET_ID, ""))
        self.google_creds_path_input.setText(settings.get(_KEY_GOOGLE_CREDENTIALS_PATH, ""))
        self._apt_list.clear()
        for apt in settings.get(_KEY_APARTMENT_COMPLEXES, []):
            self._apt_list.addItem(apt)

    def _add_apt(self) -> None:
        name = self._apt_input.text().strip()
        if not name:
            return
        existing = [self._apt_list.item(i).text() for i in range(self._apt_list.count())]
        if name not in existing:
            self._apt_list.addItem(name)
        self._apt_input.clear()

    def _del_apt(self) -> None:
        for item in self._apt_list.selectedItems():
            self._apt_list.takeItem(self._apt_list.row(item))

    def _save(self) -> None:
        settings = load_settings()
        settings[_KEY_TOTAL_SALES_PASSWORD] = self.password_input.text()
        settings[_KEY_EXPENSE_DAILY_SHEET] = self.expense_sheet_input.text().strip()
        settings[_KEY_PHONE_IP] = self.phone_ip_input.text().strip()
        settings[_KEY_NATEON_WEBHOOK_URL] = self.nateon_webhook_input.text().strip()
        try:
            settings[_KEY_SMS_GATEWAY_PORT] = int(self.sms_port_input.text().strip() or 8080)
        except ValueError:
            settings[_KEY_SMS_GATEWAY_PORT] = 8080
        settings[_KEY_SMS_GATEWAY_USERNAME] = self.sms_username_input.text().strip()
        settings[_KEY_SMS_GATEWAY_PASSWORD] = self.sms_password_input.text()
        settings[_KEY_SMS_TEST_PHONE] = self.sms_test_phone_input.text().strip()
        settings[_KEY_BROJ_USERNAME] = self.broj_username_input.text().strip()
        settings[_KEY_BROJ_PASSWORD] = self.broj_password_input.text()
        settings[_KEY_CONSULT_SPREADSHEET_ID] = self.consult_sheet_id_input.text().strip()
        settings[_KEY_GOOGLE_CREDENTIALS_PATH] = self.google_creds_path_input.text().strip()
        settings[_KEY_APARTMENT_COMPLEXES] = [
            self._apt_list.item(i).text() for i in range(self._apt_list.count())
        ]
        save_settings(settings)
        QMessageBox.information(self, "완료", "설정이 저장되었습니다.")
        self.accept()
