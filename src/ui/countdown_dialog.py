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
from src.services.countdown_service import compute_running, load_countdown, save_countdown
from src.services.sales_report_service import build_countdown_text, read_daily_section_totals


class CountdownDialog(QDialog):
    """
    월 목표 카운트다운 다이얼로그.
    데일리 파일의 오늘 매출 + JSON 누적 기준선을 합산해 보고 문구를 생성한다.
    저장 시 기준선을 갱신하여 다음 날 이어받을 수 있다.
    """

    def __init__(self, path_daily: str, parent=None) -> None:
        super().__init__(parent)
        self._path_daily = path_daily
        self._baseline_center = 0
        self._baseline_pt = 0
        self._running_center = 0
        self._running_pt = 0

        center_target, pt_target = get_monthly_targets()
        self._center_target = center_target
        self._pt_target = pt_target

        self.setWindowTitle("월 목표 카운트다운")
        self.setMinimumWidth(320)
        self._setup_ui()
        self._refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setSpacing(10)

        target_lbl = QLabel(
            f"이번 달 목표 — 센터: {self._center_target:,}원 / 피티: {self._pt_target:,}원"
        )
        target_lbl.setStyleSheet("color: #6B7280; font-size: 11px;")
        layout.addWidget(target_lbl)

        self._info_lbl = QLabel()
        self._info_lbl.setStyleSheet("color: #9CA3AF; font-size: 10px;")
        layout.addWidget(self._info_lbl)

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
        save_copy_btn = QPushButton("📋  저장하고 복사")
        save_copy_btn.setFixedHeight(36)
        save_copy_btn.clicked.connect(self._save_and_copy)
        reset_btn = QPushButton("🔄  초기화")
        reset_btn.setFixedHeight(36)
        reset_btn.setStyleSheet(
            "QPushButton { background: #F3F4F6; color: #6B7280; border: none; border-radius: 6px; }"
            "QPushButton:hover { background: #E5E7EB; }"
        )
        reset_btn.clicked.connect(self._reset)
        btn_row.addWidget(refresh_btn)
        btn_row.addWidget(save_copy_btn)
        btn_row.addWidget(reset_btn)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    def _refresh(self) -> None:
        try:
            daily = read_daily_section_totals(self._path_daily)
            data = load_countdown()
            running_center, running_pt, baseline_center, baseline_pt = compute_running(
                data, daily["center"], daily["pt"]
            )
            self._running_center = running_center
            self._running_pt = running_pt
            self._baseline_center = baseline_center
            self._baseline_pt = baseline_pt

            text = build_countdown_text(
                daily["center"], daily["pt"],
                self._center_target, self._pt_target,
                running_center, running_pt,
            )
            self._preview.setPlainText(text)

            saved_date = data.get("date", "없음")
            self._info_lbl.setText(
                f"오늘 센터 {daily['center']:,}원 / 피티 {daily['pt']:,}원  |  기준 저장: {saved_date}"
            )
        except Exception as exc:
            self._preview.setPlainText(f"오류: {exc}")

    def _reset(self) -> None:
        reply = QMessageBox.question(
            self, "초기화 확인",
            "누적 합산을 0으로 초기화하시겠습니까?\n새 달이 시작됐거나 목표를 새로 설정할 때 사용하세요.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        save_countdown(0, 0, 0, 0)
        self._baseline_center = 0
        self._baseline_pt = 0
        self._running_center = 0
        self._running_pt = 0
        self._refresh()
        QMessageBox.information(self, "완료", "초기화되었습니다.")

    def _save_and_copy(self) -> None:
        text = self._preview.toPlainText()
        if not text or text.startswith("오류:"):
            QMessageBox.warning(self, "오류", "먼저 갱신을 눌러주세요.")
            return
        save_countdown(
            self._baseline_center,
            self._baseline_pt,
            self._running_center,
            self._running_pt,
        )
        QApplication.clipboard().setText(text)
        self._refresh()
        QMessageBox.information(self, "완료", "저장하고 클립보드에 복사했습니다.")
