from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from src.services import adb_service
from src.config.settings import (
    get_consult_spreadsheet_id,
    get_google_credentials_path,
    get_phone_ip,
)
from src.services.consultation_service import (
    append_daily_entry,
    build_kakao_message,
    find_existing_entry,
    get_client,
    get_or_create_month_sheet,
    update_entry_notes,
)

_BTN = """
QPushButton {{
    background: {bg}; color: white; font-size: 13px; font-weight: 700;
    border: none; border-radius: 8px; padding: 8px 0;
}}
QPushButton:hover {{ background: {hv}; }}
QPushButton:disabled {{ background: #9CA3AF; }}
"""
_BLUE = _BTN.format(bg="#3B82F6", hv="#2563EB")
_AMBER = _BTN.format(bg="#F59E0B", hv="#D97706")
_GREEN = _BTN.format(bg="#16A34A", hv="#15803D")


class ConsultationDialog(QDialog):
    """상담 입력 다이얼로그. 구글 시트에 저장하고 카톡 발송 버튼 제공."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("상담 입력")
        self.setMinimumWidth(420)
        self._message: str = ""
        self._saved = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout()
        root.setSpacing(12)

        # ── 입력 폼 ────────────────────────────────────────────────
        form = QFormLayout()
        form.setSpacing(8)

        self._name = QLineEdit()
        self._name.setPlaceholderText("예: 홍길동")
        form.addRow("성함 *", self._name)

        self._phone = QLineEdit()
        self._phone.setPlaceholderText("예: 010-1234-5678")
        form.addRow("전화번호 *", self._phone)

        self._visit_date = QLineEdit()
        self._visit_date.setPlaceholderText("예: 07/18")
        self._visit_date.setText(date.today().strftime("%m/%d"))
        form.addRow("방문예정일", self._visit_date)

        self._category = QComboBox()
        self._category.addItems(["헬스", "PT"])
        form.addRow("종목 (카톡용)", self._category)

        self._amount = QLineEdit()
        self._amount.setPlaceholderText("예: 대학생 16만 / 일반 19만")
        form.addRow("금액", self._amount)

        self._is_new = QComboBox()
        self._is_new.addItems(["신규", "재등"])
        form.addRow("신규 / 재등", self._is_new)

        root.addLayout(form)

        # ── 내용 ────────────────────────────────────────────────────
        root.addWidget(QLabel("내용"))
        self._notes = QTextEdit()
        self._notes.setPlaceholderText(
            "0715) 인스타 광고 보고 문의. 다음주 방문 예정."
        )
        self._notes.setFixedHeight(90)
        root.addWidget(self._notes)

        # ── 저장 버튼 ───────────────────────────────────────────────
        save_btn = QPushButton("구글 시트 저장")
        save_btn.setFixedHeight(40)
        save_btn.setStyleSheet(_GREEN)
        save_btn.clicked.connect(self._save)
        root.addWidget(save_btn)

        # ── 카톡 전송 (저장 후 활성화) ─────────────────────────────
        kakao_box = QGroupBox("📱 카톡 전송")
        kakao_lay = QVBoxLayout()
        kakao_lay.setSpacing(8)

        self._status_lbl = QLabel()
        self._refresh_phone_status()
        kakao_lay.addWidget(self._status_lbl)

        self._msg_preview = QLabel("저장 후 전송 가능합니다.")
        self._msg_preview.setWordWrap(True)
        self._msg_preview.setStyleSheet(
            "background: #F9FAFB; border: 1px solid #E5E7EB; "
            "border-radius: 6px; padding: 8px; font-size: 11px; color: #374151;"
        )
        self._msg_preview.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._msg_preview.setMinimumHeight(80)
        kakao_lay.addWidget(self._msg_preview)

        btn_row = QHBoxLayout()
        self._info_btn = QPushButton("인포방 전송")
        self._info_btn.setFixedHeight(44)
        self._info_btn.setStyleSheet(_BLUE)
        self._info_btn.setEnabled(False)
        self._info_btn.clicked.connect(lambda: self._send_kakao("알바"))

        self._staff_btn = QPushButton("직원방 전송")
        self._staff_btn.setFixedHeight(44)
        self._staff_btn.setStyleSheet(_AMBER)
        self._staff_btn.setEnabled(False)
        self._staff_btn.clicked.connect(lambda: self._send_kakao("직원"))

        btn_row.addWidget(self._info_btn)
        btn_row.addWidget(self._staff_btn)
        kakao_lay.addLayout(btn_row)

        kakao_box.setLayout(kakao_lay)
        root.addWidget(kakao_box)

        # ── 닫기 ────────────────────────────────────────────────────
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet(
            "QPushButton { background: #F3F4F6; color: #374151; border: none; "
            "border-radius: 8px; padding: 6px; }"
            "QPushButton:hover { background: #E5E7EB; }"
        )
        root.addWidget(close_btn)

        self.setLayout(root)

    def _refresh_phone_status(self) -> None:
        ip = get_phone_ip()
        if not ip:
            self._status_lbl.setText("● 센터폰 IP 미설정 (설정에서 입력)")
            self._status_lbl.setStyleSheet("color: #EF4444; font-weight: bold;")
        elif adb_service.is_reachable(ip):
            self._status_lbl.setText(f"● 센터폰 연결됨 ({ip})")
            self._status_lbl.setStyleSheet("color: #22C55E; font-weight: bold;")
        else:
            self._status_lbl.setText(f"● 센터폰 미연결 ({ip})")
            self._status_lbl.setStyleSheet("color: #EF4444; font-weight: bold;")

    def _collect_entry(self) -> dict:
        return {
            "name": self._name.text().strip(),
            "phone": self._phone.text().strip(),
            "visit_date": self._visit_date.text().strip(),
            "category": self._category.currentText(),
            "amount": self._amount.text().strip(),
            "is_new": self._is_new.currentText(),
            "notes": self._notes.toPlainText().strip(),
        }

    def _save(self) -> None:
        entry = self._collect_entry()
        if not entry["name"] or not entry["phone"]:
            QMessageBox.warning(self, "입력 오류", "성함과 전화번호는 필수입니다.")
            return

        spreadsheet_id = get_consult_spreadsheet_id()
        if not spreadsheet_id:
            QMessageBox.warning(
                self, "설정 필요",
                "설정에서 상담관리 스프레드시트 ID를 먼저 입력해주세요.\n"
                "(구글 시트 URL에서 /d/ 뒤의 문자열)"
            )
            return

        try:
            client = get_client(get_google_credentials_path())
            today = date.today()
            ws = get_or_create_month_sheet(client, spreadsheet_id, today.year, today.month)

            existing_row, existing_notes = find_existing_entry(ws, entry["name"], entry["phone"])
            is_update = existing_row is not None

            if is_update:
                update_entry_notes(ws, existing_row, existing_notes, entry["notes"])
                result_msg = f"{entry['name']} 님의 기존 상담 내용이 업데이트되었습니다."
            else:
                append_daily_entry(ws, entry)
                result_msg = f"{entry['name']} 님의 상담이 스프레드시트에 저장되었습니다."

            self._message = build_kakao_message(entry, is_update=is_update)
            self._msg_preview.setText(self._message)
            self._info_btn.setEnabled(True)
            self._staff_btn.setEnabled(True)
            self._saved = True

            QMessageBox.information(
                self, "저장 완료",
                f"{result_msg}\n아래에서 카톡 발송을 진행하세요."
            )
        except FileNotFoundError as exc:
            QMessageBox.warning(self, "인증 파일 없음", str(exc))
        except Exception as exc:
            QMessageBox.critical(self, "저장 실패", str(exc))

    def _send_kakao(self, target: str) -> None:
        if not self._message:
            QMessageBox.warning(self, "경고", "먼저 저장을 완료해주세요.")
            return
        ip = get_phone_ip()
        if not ip:
            QMessageBox.warning(self, "설정 필요", "센터폰 IP를 먼저 설정해주세요.")
            return
        try:
            adb_service.send_kakao(ip, target, self._message)
            label = "인포방" if target == "알바" else "직원방"
            QMessageBox.information(self, "전송 완료", f"{label}으로 전송했습니다.")
        except Exception as exc:
            QMessageBox.critical(self, "전송 실패", str(exc))
