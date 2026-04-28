from __future__ import annotations

from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.services import adb_service
from src.config.settings import get_phone_ip

_BTN_STYLE = """
QPushButton {{
    background-color: {bg};
    color: white;
    font-size: 14px;
    font-weight: bold;
    border-radius: 8px;
    border: none;
    padding: 8px 0;
}}
QPushButton:hover {{ background-color: {hover}; }}
QPushButton:pressed {{ background-color: {pressed}; }}
QPushButton:disabled {{ background-color: #9CA3AF; }}
"""

_ALBA_STYLE = _BTN_STYLE.format(bg="#3B82F6", hover="#2563EB", pressed="#1D4ED8")
_JIKWON_STYLE = _BTN_STYLE.format(bg="#F59E0B", hover="#D97706", pressed="#B45309")


class KakaoSendWidget(QWidget):
    """알바방 / 직원방 카톡 자동 전송 버튼 위젯."""

    def __init__(self, get_message_fn, parent=None) -> None:
        super().__init__(parent)
        self._get_message = get_message_fn  # () -> str | None
        self._setup_ui()

    def _setup_ui(self) -> None:
        group = QGroupBox("📱 카톡 자동 전송")
        inner = QVBoxLayout()

        self._status_lbl = QLabel()
        self.refresh_status()
        inner.addWidget(self._status_lbl)

        note = QLabel("※ 설정에서 센터폰 IP를 먼저 입력하세요")
        note.setStyleSheet("color: #888888; font-size: 11px;")
        inner.addWidget(note)

        btn_row = QHBoxLayout()

        alba_btn = QPushButton("알바방 전송")
        alba_btn.setMinimumHeight(54)
        alba_btn.setStyleSheet(_ALBA_STYLE)
        alba_btn.clicked.connect(lambda: self._send("알바"))

        jikwon_btn = QPushButton("직원방 전송")
        jikwon_btn.setMinimumHeight(54)
        jikwon_btn.setStyleSheet(_JIKWON_STYLE)
        jikwon_btn.clicked.connect(lambda: self._send("직원"))

        btn_row.addWidget(alba_btn)
        btn_row.addWidget(jikwon_btn)
        inner.addLayout(btn_row)

        group.setLayout(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(group)

    def refresh_status(self) -> None:
        ip = get_phone_ip()
        if not ip:
            self._status_lbl.setText("● 센터폰 IP 미설정 (설정에서 입력)")
            self._status_lbl.setStyleSheet("color: #EF4444; font-weight: bold;")
            return
        if adb_service.is_reachable(ip):
            self._status_lbl.setText(f"● 센터폰 연결됨 ({ip})")
            self._status_lbl.setStyleSheet("color: #22C55E; font-weight: bold;")
        else:
            self._status_lbl.setText(f"● 센터폰 미연결 ({ip})")
            self._status_lbl.setStyleSheet("color: #EF4444; font-weight: bold;")

    def _send(self, target: str) -> None:
        message = self._get_message()
        if not message:
            QMessageBox.warning(self.window(), "경고", "먼저 카톡 문구를 생성해주세요.")
            return

        ip = get_phone_ip()
        if not ip:
            QMessageBox.warning(
                self.window(), "설정 필요",
                "⚙ 설정에서 센터폰 IP를 먼저 입력해주세요."
            )
            return

        try:
            adb_service.send_kakao(ip, target, message)
            QMessageBox.information(
                self.window(), "전송 완료", f"{target}방으로 전송했습니다."
            )
            self.window().accept()
        except Exception as exc:
            QMessageBox.critical(self.window(), "전송 실패", str(exc))
