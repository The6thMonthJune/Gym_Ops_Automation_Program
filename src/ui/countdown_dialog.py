from __future__ import annotations

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

from src.config.settings import get_monthly_targets
from src.services.sales_report_service import build_countdown_text, read_daily_section_totals


class CountdownDialog(QDialog):
    """월 목표 카운트다운 다이얼로그. 데일리 파일에서 센터/레슨 매출을 읽어 보고 문구를 생성한다."""

    def __init__(self, path_daily: str, parent=None) -> None:
        super().__init__(parent)
        self._path_daily = path_daily
        self.setWindowTitle("월 목표 카운트다운")
        self.setMinimumWidth(320)
        self._setup_ui()
        self._refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setSpacing(10)

        center_target, pt_target = get_monthly_targets()
        self._center_target = center_target
        self._pt_target = pt_target

        target_lbl = QLabel(
            f"이번 달 목표 — 센터: {center_target:,}원 / 피티: {pt_target:,}원"
        )
        target_lbl.setStyleSheet("color: #6B7280; font-size: 11px;")
        layout.addWidget(target_lbl)

        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setFixedHeight(160)
        self._preview.setStyleSheet(
            "font-size: 14px; font-family: 'Malgun Gothic', sans-serif;"
        )
        layout.addWidget(self._preview)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("↻  갱신")
        refresh_btn.setFixedHeight(36)
        refresh_btn.clicked.connect(self._refresh)
        copy_btn = QPushButton("📋  복사")
        copy_btn.setFixedHeight(36)
        copy_btn.clicked.connect(self._copy)
        btn_row.addWidget(refresh_btn)
        btn_row.addWidget(copy_btn)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    def _refresh(self) -> None:
        try:
            totals = read_daily_section_totals(self._path_daily)
            text = build_countdown_text(
                totals["center"], totals["pt"],
                self._center_target, self._pt_target,
            )
            self._preview.setPlainText(text)
        except Exception as exc:
            self._preview.setPlainText(f"오류: {exc}")

    def _copy(self) -> None:
        text = self._preview.toPlainText()
        if text and not text.startswith("오류:"):
            QApplication.clipboard().setText(text)
            QMessageBox.information(self, "완료", "클립보드에 복사되었습니다.")
