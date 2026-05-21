from __future__ import annotations

from datetime import date

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from src.config.settings import get_monthly_targets, get_password
from src.services.sales_report_service import build_countdown_text, read_monthly_totals_by_section


class CountdownDialog(QDialog):
    """
    월 목표 카운트다운 보고 다이얼로그.
    총매출 파일에서 이번 달 센터/피티 누적 매출을 읽어 목표 잔여액을 표시한다.
    """

    def __init__(self, path_total: str, parent=None) -> None:
        super().__init__(parent)
        self._path_total = path_total
        self.setWindowTitle("월 목표 카운트다운")
        self.setMinimumWidth(320)
        self._setup_ui()
        self._refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setSpacing(10)

        guide = QLabel("이번 달 누적 매출과 목표 잔여액을 표시합니다.")
        guide.setStyleSheet("color: #6B7280; font-size: 11px;")
        layout.addWidget(guide)

        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setFixedHeight(160)
        self._text_edit.setStyleSheet(
            "font-size: 14px; font-family: 'Malgun Gothic', sans-serif;"
        )
        layout.addWidget(self._text_edit)

        btn_row = QHBoxLayout()
        copy_btn = QPushButton("📋  복사")
        copy_btn.setFixedHeight(36)
        copy_btn.clicked.connect(self._copy)
        refresh_btn = QPushButton("↻  갱신")
        refresh_btn.setFixedHeight(36)
        refresh_btn.clicked.connect(self._refresh)
        btn_row.addWidget(copy_btn)
        btn_row.addWidget(refresh_btn)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    def _refresh(self) -> None:
        today = date.today()
        password = get_password()
        center_target, pt_target = get_monthly_targets()
        try:
            totals = read_monthly_totals_by_section(
                self._path_total, today.year, today.month, password
            )
            text = build_countdown_text(
                totals["center"], totals["pt"], center_target, pt_target
            )
            self._text_edit.setPlainText(text)
        except Exception as exc:
            self._text_edit.setPlainText(f"오류: {exc}")

    def _copy(self) -> None:
        text = self._text_edit.toPlainText()
        if text and not text.startswith("오류:"):
            QApplication.clipboard().setText(text)
            QMessageBox.information(self, "완료", "클립보드에 복사되었습니다.")
