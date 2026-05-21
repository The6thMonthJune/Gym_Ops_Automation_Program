from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from src.config.settings import get_monthly_targets
from src.services.countdown_service import load_countdown, save_countdown
from src.services.sales_report_service import build_countdown_text


class CountdownDialog(QDialog):
    """월 목표 카운트다운 다이얼로그. 센터/피티 매출을 직접 입력하면 보고 문구를 생성한다."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("월 목표 카운트다운")
        self.setMinimumWidth(340)
        self._setup_ui()
        self._load_last()

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

        form = QFormLayout()
        self._center_input = QLineEdit()
        self._center_input.setPlaceholderText("예: 8500000")
        self._center_input.textChanged.connect(self._update_preview)
        form.addRow("센터 누적 매출 (원):", self._center_input)

        self._pt_input = QLineEdit()
        self._pt_input.setPlaceholderText("예: 7200000")
        self._pt_input.textChanged.connect(self._update_preview)
        form.addRow("피티 누적 매출 (원):", self._pt_input)
        layout.addLayout(form)

        self._last_lbl = QLabel()
        self._last_lbl.setStyleSheet("color: #9CA3AF; font-size: 10px;")
        self._last_lbl.setAlignment(Qt.AlignRight)
        layout.addWidget(self._last_lbl)

        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setFixedHeight(160)
        self._preview.setStyleSheet(
            "font-size: 14px; font-family: 'Malgun Gothic', sans-serif;"
        )
        layout.addWidget(self._preview)

        btn_row = QHBoxLayout()
        copy_btn = QPushButton("📋  복사하고 저장")
        copy_btn.setFixedHeight(36)
        copy_btn.clicked.connect(self._copy_and_save)
        btn_row.addWidget(copy_btn)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    def _load_last(self) -> None:
        data = load_countdown()
        if data.get("center") is not None:
            self._center_input.setText(str(data["center"]))
        if data.get("pt") is not None:
            self._pt_input.setText(str(data["pt"]))
        if saved_date := data.get("date"):
            self._last_lbl.setText(f"마지막 저장: {saved_date}")

    def _parse_inputs(self) -> tuple[int, int] | None:
        try:
            center = int(self._center_input.text().replace(",", "").strip() or 0)
            pt = int(self._pt_input.text().replace(",", "").strip() or 0)
            return center, pt
        except ValueError:
            return None

    def _update_preview(self) -> None:
        parsed = self._parse_inputs()
        if parsed is None:
            self._preview.setPlainText("숫자만 입력해주세요.")
            return
        center, pt = parsed
        text = build_countdown_text(center, pt, self._center_target, self._pt_target)
        self._preview.setPlainText(text)

    def _copy_and_save(self) -> None:
        parsed = self._parse_inputs()
        if parsed is None:
            QMessageBox.warning(self, "입력 오류", "숫자만 입력해주세요.")
            return
        center, pt = parsed
        text = build_countdown_text(center, pt, self._center_target, self._pt_target)
        QApplication.clipboard().setText(text)
        save_countdown(center, pt)
        self._load_last()
        QMessageBox.information(self, "완료", "클립보드에 복사하고 저장했습니다.")
