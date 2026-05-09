from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from src.services.locker_service import load_records

_NAVY = "#1E2D3D"

_BTN_STYLE = f"""
    QPushButton {{
        background: {_NAVY}; color: white;
        border: none; border-radius: 8px;
        font-size: 13px; font-weight: 600;
        padding: 8px 20px;
    }}
    QPushButton:hover {{ background: #2D3F52; }}
    QPushButton:disabled {{ background: #9CA3AF; }}
"""

_DEFAULT_THRESHOLD = 70


class MembershipExpiryDialog(QDialog):
    """헬스권 만료까지 N일 이하 남은 회원 목록 및 전화번호 추출 다이얼로그."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("헬스권 만료 임박 회원")
        self.resize(580, 500)
        self.setStyleSheet(
            "QDialog { background: #F3F4F6; font-family: 'Malgun Gothic', '맑은 고딕', sans-serif; }"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.setSpacing(12)

        lay.addLayout(self._build_controls())
        lay.addWidget(self._build_table(), 1)
        lay.addLayout(self._build_buttons())

        self._all_records = load_records()
        self._refresh()

    def _build_controls(self) -> QHBoxLayout:
        row = QHBoxLayout()

        lbl = QLabel("기준: 만료까지")
        lbl.setStyleSheet("color: #111827; font-size: 13px;")
        row.addWidget(lbl)

        self._spinbox = QSpinBox()
        self._spinbox.setRange(1, 365)
        self._spinbox.setValue(_DEFAULT_THRESHOLD)
        self._spinbox.setSuffix("일 이하")
        self._spinbox.setFixedWidth(130)
        self._spinbox.setStyleSheet(
            "QSpinBox { background: white; color: #111827; border: 1px solid #D1D5DB; border-radius: 6px; padding: 4px 8px; font-size: 13px; }"
        )
        self._spinbox.valueChanged.connect(self._refresh)
        row.addWidget(self._spinbox)
        row.addStretch()

        self._count_lbl = QLabel()
        self._count_lbl.setStyleSheet("color: #6B7280; font-size: 12px;")
        row.addWidget(self._count_lbl)

        return row

    def _build_table(self) -> QTableWidget:
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["이름", "연락처", "잔여일", "보유 이용권"])
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setStyleSheet("""
            QTableWidget { background: white; border-radius: 8px; border: none; font-size: 13px; }
            QTableWidget::item { padding: 6px; }
            QHeaderView::section { background: #F9FAFB; color: #374151; border-bottom: 1px solid #E5E7EB; font-weight: 600; padding: 6px; }
        """)
        return self._table

    def _build_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()

        self._copy_phone_btn = QPushButton("📋  전화번호 복사")
        self._copy_phone_btn.setStyleSheet(_BTN_STYLE)
        self._copy_phone_btn.clicked.connect(self._copy_phones)

        close_btn = QPushButton("닫기")
        close_btn.setStyleSheet(_BTN_STYLE)
        close_btn.clicked.connect(self.accept)

        row.addWidget(self._copy_phone_btn)
        row.addStretch()
        row.addWidget(close_btn)
        return row

    def _refresh(self) -> None:
        threshold = self._spinbox.value()
        today = date.today()

        filtered: list[tuple] = []
        for r in self._all_records:
            if r.is_holding or not r.expiry_date or not r.membership_type:
                continue
            days = (r.expiry_date - today).days
            if 0 <= days <= threshold:
                filtered.append((r, days))

        filtered.sort(key=lambda x: x[1])

        self._table.setRowCount(len(filtered))
        for i, (r, days) in enumerate(filtered):
            name_item = QTableWidgetItem(r.member_name)
            phone_item = QTableWidgetItem(r.phone_number or "—")
            days_item = QTableWidgetItem(f"{days}일")
            days_item.setTextAlignment(Qt.AlignCenter)
            membership_item = QTableWidgetItem(r.membership_type)

            fg = QColor("#B91C1C") if days < 10 else QColor("#111827")
            for item in (name_item, phone_item, days_item, membership_item):
                item.setForeground(fg)

            self._table.setItem(i, 0, name_item)
            self._table.setItem(i, 1, phone_item)
            self._table.setItem(i, 2, days_item)
            self._table.setItem(i, 3, membership_item)

        self._count_lbl.setText(f"총 {len(filtered)}명")
        self._copy_phone_btn.setEnabled(len(filtered) > 0)

    def _copy_phones(self) -> None:
        phones = [
            self._table.item(i, 1).text()
            for i in range(self._table.rowCount())
            if self._table.item(i, 1).text() != "—"
        ]
        if not phones:
            return
        QApplication.clipboard().setText("\n".join(phones))
        original = self._copy_phone_btn.text()
        self._copy_phone_btn.setText("✓  복사 완료!")
        self._copy_phone_btn.setEnabled(False)
        QTimer.singleShot(1500, lambda: (
            self._copy_phone_btn.setText(original),
            self._copy_phone_btn.setEnabled(True),
        ))
