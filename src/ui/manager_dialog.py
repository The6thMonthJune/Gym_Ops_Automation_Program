from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
)

from src.services.locker_service import count_by_state, load_records
from src.services.sales_report_service import build_sales_report_text, read_sales_values
from src.core.file_naming import extract_date_from_filename


_BTN_STYLE = """
QPushButton {{
    background: {bg}; color: {fg}; font-size: 13px; font-weight: 600;
    border: none; border-radius: 8px; padding: 0 16px;
    text-align: left;
}}
QPushButton:hover {{ background: {hv}; }}
"""
_GRAY = _BTN_STYLE.format(bg="#F3F4F6", fg="#374151", hv="#E5E7EB")


class ManagerDialog(QDialog):
    """실장 기능 모음 다이얼로그."""

    def __init__(self, daily_file: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("실장 기능")
        self.setMinimumWidth(360)
        self._daily_file = daily_file
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout()
        root.setSpacing(8)

        buttons: list[tuple[str, str]] = [
            ("📋  보고 문구 복사", "_copy_report"),
            ("👥  회원 현황 보고", "_member_status"),
            ("📆  만료 임박 회원 조회", "_expiry"),
            ("🌍  외국인 회원 관리", "_foreign"),
            ("📊  유입경로 보고서 생성", "_lead_report"),
            ("🎯  월 목표 카운트다운", "_countdown"),
            ("📱  만료 락카 문자 발송", "_locker_sms"),
        ]

        for row_pair in [buttons[i:i+2] for i in range(0, len(buttons), 2)]:
            row = QHBoxLayout()
            row.setSpacing(8)
            for label, slot_name in row_pair:
                btn = QPushButton(label)
                btn.setFixedHeight(52)
                btn.setStyleSheet(_GRAY)
                btn.clicked.connect(getattr(self, slot_name))
                row.addWidget(btn)
            root.addLayout(row)

        self.setLayout(root)

    def _copy_report(self) -> None:
        if not self._daily_file or not Path(self._daily_file).exists():
            QMessageBox.warning(self, "경고", "메인 화면에서 데일리 파일을 먼저 등록해주세요.")
            return
        try:
            try:
                parsed = extract_date_from_filename(Path(self._daily_file).name)
                report_date = datetime(date.today().year, parsed.month, parsed.day)
            except ValueError:
                report_date = datetime.today()
            sales = read_sales_values(self._daily_file)
            text = build_sales_report_text(report_date, sales)
            QApplication.clipboard().setText(text)
            QMessageBox.information(self, "완료", "보고 문구를 클립보드에 복사했습니다.")
        except Exception as exc:
            QMessageBox.critical(self, "오류", str(exc))

    def _member_status(self) -> None:
        try:
            from src.ui.trend_dialog import TrendDialog
            records = load_records()
            counts = count_by_state(records)
            TrendDialog(counts, self).exec()
        except Exception as exc:
            QMessageBox.critical(self, "오류", str(exc))

    def _expiry(self) -> None:
        from src.ui.membership_expiry_dialog import MembershipExpiryDialog
        MembershipExpiryDialog(parent=self).exec()

    def _foreign(self) -> None:
        from src.ui.foreign_member_dialog import ForeignMemberDialog
        ForeignMemberDialog(parent=self).exec()

    def _lead_report(self) -> None:
        from src.services.lead_report_service import generate_report
        save_path, _ = QFileDialog.getSaveFileName(
            self, "유입경로 보고서 저장",
            f"유입경로_보고서_{date.today().strftime('%Y%m')}.xlsx",
            "Excel 파일 (*.xlsx)",
        )
        if not save_path:
            return
        try:
            out = generate_report(save_path)
            QMessageBox.information(self, "완료", f"보고서가 저장되었습니다.\n{out}")
        except ValueError as exc:
            QMessageBox.warning(self, "데이터 없음", str(exc))
        except Exception as exc:
            QMessageBox.critical(self, "오류", str(exc))

    def _countdown(self) -> None:
        from src.ui.countdown_dialog import CountdownDialog
        if not self._daily_file:
            QMessageBox.warning(self, "파일 미등록", "메인 화면에서 데일리 파일을 먼저 등록해주세요.")
            return
        CountdownDialog(self._daily_file, parent=self).exec()

    def _locker_sms(self) -> None:
        from src.ui.locker_sms_dialog import LockerSmsDialog
        LockerSmsDialog(parent=self).exec()
