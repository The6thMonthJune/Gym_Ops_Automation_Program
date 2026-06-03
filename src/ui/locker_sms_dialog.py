from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.config.settings import get_phone_ip, get_sms_gateway_credentials, get_sms_test_phone
from src.services.foreign_member_service import get_expired_locker_foreign_members
from src.services.sms_gateway_service import send_bulk_sms

_MSG_TEMPLATE = (
    "[Rewind Fitness]\n"
    "Hi {name}!\n"
    "Your locker rental period has expired.\n"
    "Please visit us to renew 😊\n\n"
    "[리와인드 휘트니스]\n"
    "{name}님, 락카 이용 기간이 만료되었습니다.\n"
    "재계약을 원하시면 센터로 문의해주세요 😊"
)


def _build_message(name: str) -> str:
    return _MSG_TEMPLATE.format(name=name)


class LockerSmsDialog(QDialog):
    """만료된 락카를 가진 외국인 회원에게 한/영 개별 문자를 발송하는 다이얼로그."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("외국인 만료 락카 문자 발송")
        self.setMinimumWidth(440)
        self._checkboxes: list[tuple[QCheckBox, str, str]] = []  # (checkbox, name, phone)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setSpacing(10)

        guide = QLabel("락카 이용 기간이 만료된 외국인 회원 목록입니다.")
        guide.setStyleSheet("color: #6B7280; font-size: 11px;")
        layout.addWidget(guide)

        # 회원 목록 (스크롤)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(180)
        container = QWidget()
        list_layout = QVBoxLayout()
        list_layout.setSpacing(4)
        list_layout.setContentsMargins(4, 4, 4, 4)

        members = get_expired_locker_foreign_members()
        for m in members:
            expiry_str = m.locker_expiry.strftime("%Y.%m.%d") if m.locker_expiry else (
                m.expiry_date.strftime("%Y.%m.%d") if m.expiry_date else "만료일 미상"
            )
            cb = QCheckBox(f"{m.name}  |  만료: {expiry_str}  |  {m.phone_number}")
            cb.setChecked(True)
            self._checkboxes.append((cb, m.name, m.phone_number))
            list_layout.addWidget(cb)

        if not self._checkboxes:
            empty = QLabel("락카가 만료된 외국인 회원이 없습니다.")
            empty.setStyleSheet("color: #9CA3AF;")
            list_layout.addWidget(empty)

        list_layout.addStretch()
        container.setLayout(list_layout)
        scroll.setWidget(container)
        layout.addWidget(scroll)

        # 전체 선택/해제
        sel_row = QHBoxLayout()
        all_btn = QPushButton("전체 선택")
        all_btn.setFixedHeight(28)
        all_btn.clicked.connect(lambda: self._set_all(True))
        none_btn = QPushButton("전체 해제")
        none_btn.setFixedHeight(28)
        none_btn.clicked.connect(lambda: self._set_all(False))
        sel_row.addWidget(all_btn)
        sel_row.addWidget(none_btn)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        # 문구 미리보기
        layout.addWidget(QLabel("발송 문구 미리보기:"))
        preview = QTextEdit()
        preview.setReadOnly(True)
        preview.setFixedHeight(140)
        preview.setPlainText(_build_message("John"))
        preview.setStyleSheet("font-size: 12px; font-family: 'Malgun Gothic', sans-serif;")
        layout.addWidget(preview)

        # 버튼
        btn_row = QHBoxLayout()
        test_btn = QPushButton("🧪  테스트 발송")
        test_btn.setFixedHeight(38)
        test_btn.setStyleSheet(
            "QPushButton { background: #F3F4F6; color: #374151; border: none; border-radius: 8px; font-size: 13px; }"
            "QPushButton:hover { background: #E5E7EB; }"
        )
        test_btn.clicked.connect(self._test_send)
        send_btn = QPushButton("📨  선택 회원에게 발송")
        send_btn.setFixedHeight(38)
        send_btn.setStyleSheet(
            "QPushButton { background: #3B82F6; color: white; border: none; border-radius: 8px; font-size: 13px; font-weight: 600; }"
            "QPushButton:hover { background: #2563EB; }"
        )
        send_btn.clicked.connect(self._send)
        btn_row.addWidget(test_btn)
        btn_row.addWidget(send_btn)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    def _set_all(self, checked: bool) -> None:
        for cb, _, _ in self._checkboxes:
            cb.setChecked(checked)

    def _selected(self) -> list[tuple[str, str]]:
        return [(name, phone) for cb, name, phone in self._checkboxes if cb.isChecked()]

    def _get_connection(self) -> tuple[str, int, str, str] | None:
        phone_ip = get_phone_ip()
        if not phone_ip:
            QMessageBox.warning(self, "설정 오류", "설정에서 센터폰 IP를 먼저 등록해주세요.")
            return None
        port, username, password = get_sms_gateway_credentials()
        return phone_ip, port, username, password

    def _test_send(self) -> None:
        test_phone = get_sms_test_phone()
        if not test_phone:
            QMessageBox.warning(self, "테스트 번호 없음", "설정(⚙)에서 'SMS 테스트 번호'를 먼저 등록해주세요.")
            return
        conn = self._get_connection()
        if not conn:
            return
        phone_ip, port, username, password = conn
        try:
            send_bulk_sms(phone_ip, [test_phone], _build_message("Test"), port, username, password)
            QMessageBox.information(self, "완료", f"{test_phone}으로 테스트 문자를 발송했습니다.")
        except Exception as exc:
            QMessageBox.critical(self, "발송 실패", str(exc))

    def _send(self) -> None:
        selected = self._selected()
        if not selected:
            QMessageBox.warning(self, "선택 없음", "발송할 회원을 선택해주세요.")
            return
        conn = self._get_connection()
        if not conn:
            return
        phone_ip, port, username, password = conn

        reply = QMessageBox.question(
            self, "발송 확인",
            f"선택한 {len(selected)}명에게 문자를 발송합니다.\n계속하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        failed: list[str] = []
        for name, phone in selected:
            try:
                send_bulk_sms(phone_ip, [phone], _build_message(name), port, username, password)
            except Exception:
                failed.append(name)

        if failed:
            QMessageBox.warning(
                self, "일부 실패",
                f"{len(selected) - len(failed)}명 성공, {len(failed)}명 실패\n실패: {', '.join(failed)}"
            )
        else:
            QMessageBox.information(self, "완료", f"{len(selected)}명에게 문자를 발송했습니다.")
            self.accept()
