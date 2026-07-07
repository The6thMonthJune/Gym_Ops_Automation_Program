from __future__ import annotations

import calendar
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QApplication,
    QDateEdit,
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

from src.services.countdown_service import load_period_settings, save_period_settings
from src.services.sales_report_service import build_countdown_text, read_range_totals


class CountdownDialog(QDialog):
    """
    월 목표 카운트다운 다이얼로그.
    설정한 기간의 데일리 파일을 자동 집계해 카운트다운을 계산한다.
    수동 저장 없이 기간 내 파일을 모두 읽어 합산하므로 주말 매출도 자동 반영된다.
    """

    def __init__(self, path_daily: str, parent=None) -> None:
        super().__init__(parent)
        self._daily_dir = Path(path_daily).parent
        self._load_defaults()
        self.setWindowTitle("월 목표 카운트다운")
        self.setMinimumWidth(380)
        self._setup_ui()
        self._refresh()

    def _load_defaults(self) -> None:
        data = load_period_settings()
        today = date.today()
        last_day = calendar.monthrange(today.year, today.month)[1]

        self._start_date: date = data.get("start_date") or date(today.year, today.month, 1)
        self._end_date: date = data.get("end_date") or date(today.year, today.month, last_day)
        self._center_target: int = data.get("center_target") or 0
        self._pt_target: int = data.get("pt_target") or 0

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setSpacing(10)

        # ── 기간 & 목표 설정 ───────────────────────────────────────
        group = QGroupBox("기간 설정")
        form = QFormLayout()
        form.setSpacing(8)

        date_row = QHBoxLayout()
        self._start_edit = QDateEdit()
        self._start_edit.setCalendarPopup(True)
        self._start_edit.setDisplayFormat("yyyy-MM-dd")
        self._start_edit.setDate(QDate(self._start_date.year, self._start_date.month, self._start_date.day))
        date_row.addWidget(self._start_edit)
        date_row.addWidget(QLabel("~"))
        self._end_edit = QDateEdit()
        self._end_edit.setCalendarPopup(True)
        self._end_edit.setDisplayFormat("yyyy-MM-dd")
        self._end_edit.setDate(QDate(self._end_date.year, self._end_date.month, self._end_date.day))
        date_row.addWidget(self._end_edit)
        form.addRow("기간", date_row)

        self._center_edit = QLineEdit(str(self._center_target))
        self._center_edit.setPlaceholderText("예: 4000000")
        form.addRow("센터 목표 (원)", self._center_edit)

        self._pt_edit = QLineEdit(str(self._pt_target))
        self._pt_edit.setPlaceholderText("예: 1000000")
        form.addRow("피티 목표 (원)", self._pt_edit)

        save_btn = QPushButton("저장")
        save_btn.setFixedHeight(30)
        save_btn.clicked.connect(self._save_settings)
        form.addRow("", save_btn)

        group.setLayout(form)
        layout.addWidget(group)

        # ── 결과 ───────────────────────────────────────────────────
        self._info_lbl = QLabel()
        self._info_lbl.setStyleSheet("color: #9CA3AF; font-size: 10px;")
        layout.addWidget(self._info_lbl)

        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setFixedHeight(145)
        self._preview.setStyleSheet(
            "font-size: 14px; font-family: 'Malgun Gothic', sans-serif;"
        )
        layout.addWidget(self._preview)

        # ── 버튼 ───────────────────────────────────────────────────
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

    def _save_settings(self) -> None:
        try:
            qd = self._start_edit.date()
            start = date(qd.year(), qd.month(), qd.day())
            qd = self._end_edit.date()
            end = date(qd.year(), qd.month(), qd.day())
            center_target = int(self._center_edit.text().replace(",", "").strip() or 0)
            pt_target = int(self._pt_edit.text().replace(",", "").strip() or 0)
        except ValueError:
            QMessageBox.warning(self, "오류", "목표 금액은 숫자만 입력하세요.")
            return

        if start > end:
            QMessageBox.warning(self, "오류", "시작일이 종료일보다 늦을 수 없습니다.")
            return

        save_period_settings(center_target, pt_target, start, end)
        self._start_date = start
        self._end_date = end
        self._center_target = center_target
        self._pt_target = pt_target
        self._refresh()
        QMessageBox.information(self, "완료", "기간 설정이 저장되었습니다.")

    def _refresh(self) -> None:
        try:
            totals = read_range_totals(self._daily_dir, self._start_date, self._end_date)
            text = build_countdown_text(
                totals["center"], totals["pt"],
                self._center_target, self._pt_target,
            )
            self._preview.setPlainText(text)
            s = self._start_date
            e = self._end_date
            self._info_lbl.setText(
                f"{s.month}.{s.day} ~ {e.month}.{e.day}  |  데일리 파일 자동 집계"
            )
        except Exception as exc:
            self._preview.setPlainText(f"오류: {exc}")

    def _copy(self) -> None:
        text = self._preview.toPlainText()
        if not text or text.startswith("오류:"):
            QMessageBox.warning(self, "오류", "먼저 갱신을 눌러주세요.")
            return
        QApplication.clipboard().setText(text)
        QMessageBox.information(self, "완료", "클립보드에 복사했습니다.")
