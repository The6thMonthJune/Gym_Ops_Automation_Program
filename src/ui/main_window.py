from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.core.file_naming import extract_date_from_filename
from src.services.daily_file_service import create_next_daily_file
from src.services.sales_report_service import build_sales_report_text, read_sales_values
from src.services.locker_service import count_by_state, build_member_report_text, load_records
from src.services.lead_report_service import generate_report
from src.ui.payment_dialog import PaymentDialog
from src.ui.settings_dialog import SettingsDialog
from src.config.constants import APP_NAME
from src.config.settings import (
    _KEY_DAILY_FILE,
    _KEY_TOTAL_SALES_FILE,
    load_settings,
    save_settings,
)

_NAVY = "#1E2D3D"
_WHITE = "#FFFFFF"
_BG = "#F3F4F6"

APP_QSS = """
QWidget { font-family: "Malgun Gothic", "맑은 고딕", sans-serif; }
QPushButton { outline: none; }
"""


def _shadow_card(layout) -> QFrame:
    frame = QFrame()
    frame.setObjectName("shadow-card")
    frame.setStyleSheet("QFrame#shadow-card { background: #FFFFFF; border-radius: 12px; }")
    frame.setLayout(layout)
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(8)
    shadow.setOffset(0, 2)
    shadow.setColor(QColor(0, 0, 0, 20))
    frame.setGraphicsEffect(shadow)
    return frame


# ── 파일 경로 행 ──────────────────────────────────────────────────

class _SlimFileRow(QFrame):
    browse_clicked = Signal()

    def __init__(self, label: str, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(34)
        self.setObjectName("slim-row")
        self.setStyleSheet("""
            QFrame#slim-row { background: #F9FAFB; border-radius: 6px; border: 1px solid #E5E7EB; }
            QLabel { background: transparent; border: none; }
        """)

        lay = QHBoxLayout()
        lay.setContentsMargins(10, 0, 8, 0)
        lay.setSpacing(8)

        type_lbl = QLabel(label)
        type_lbl.setFixedWidth(58)
        type_lbl.setStyleSheet("color: #6B7280; font-size: 11px; background: transparent; border: none;")

        self._path_lbl = QLabel("파일 미등록")
        self._path_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._path_lbl.setStyleSheet("color: #9CA3AF; font-size: 11px; background: transparent; border: none;")

        browse_btn = QPushButton("📂")
        browse_btn.setFixedSize(24, 24)
        browse_btn.setStyleSheet("""
            QPushButton { background: transparent; border: none; font-size: 13px; }
            QPushButton:hover { background: #E5E7EB; border-radius: 4px; }
        """)
        browse_btn.clicked.connect(self.browse_clicked)

        lay.addWidget(type_lbl)
        lay.addWidget(self._path_lbl, 1)
        lay.addWidget(browse_btn)
        self.setLayout(lay)

    def set_path(self, path: str) -> None:
        if path:
            self._path_lbl.setText(Path(path).name)
            self._path_lbl.setStyleSheet(
                "color: #3B82F6; font-size: 11px; font-weight: 500; background: transparent; border: none;"
            )
        else:
            self._path_lbl.setText("파일 미등록")
            self._path_lbl.setStyleSheet(
                "color: #9CA3AF; font-size: 11px; background: transparent; border: none;"
            )


# ── 큰 바로가기 버튼 ──────────────────────────────────────────────

class _BigBtn(QFrame):
    clicked = Signal()

    def __init__(self, emoji: str, text: str, bg: str, hover: str, parent=None) -> None:
        super().__init__(parent)
        self._bg = bg
        self._hover = hover
        self.setFixedHeight(90)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self._paint(bg)

        lay = QVBoxLayout()
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(8)
        lay.setContentsMargins(8, 8, 8, 8)

        em = QLabel(emoji)
        em.setAlignment(Qt.AlignCenter)
        em.setStyleSheet("font-size: 22px; background: transparent; border: none;")

        tx = QLabel(text)
        tx.setAlignment(Qt.AlignCenter)
        tx.setStyleSheet("color: white; font-size: 14px; font-weight: 700; background: transparent; border: none;")

        lay.addWidget(em)
        lay.addWidget(tx)
        self.setLayout(lay)

    def _paint(self, color: str) -> None:
        self.setStyleSheet(f"""
            QFrame {{ background: {color}; border-radius: 12px; }}
            QLabel {{ background: transparent; border: none; }}
        """)

    def enterEvent(self, event) -> None:
        self._paint(self._hover)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._paint(self._bg)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# ── 메인 윈도우 ──────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setStyleSheet(APP_QSS)
        self.setAcceptDrops(True)
        self._path_daily = ""
        self._path_total = ""
        self._setup_ui()
        self._load_saved_paths()
        self._auto_setup_today_file()
        self._ensure_next_file_exists()
        self._refresh_sales()

        self._last_checked_date = date.today()
        timer = QTimer(self)
        timer.timeout.connect(self._check_date_change)
        timer.start(60_000)

    # ── UI 구성 ───────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        central = QWidget()
        central.setStyleSheet(f"background: {_BG};")

        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_title_bar())

        body = QWidget()
        body.setStyleSheet(f"background: {_BG};")
        body_lay = QVBoxLayout()
        body_lay.setContentsMargins(14, 14, 14, 14)
        body_lay.setSpacing(12)
        body_lay.addWidget(self._build_file_section())
        body_lay.addWidget(self._build_sales_card())
        body_lay.addWidget(self._build_shortcuts())
        body_lay.addStretch()
        body.setLayout(body_lay)

        root.addWidget(body)
        central.setLayout(root)
        self.setCentralWidget(central)

    def _build_title_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(48)
        bar.setStyleSheet(f"background: {_NAVY};")

        lay = QHBoxLayout()
        lay.setContentsMargins(16, 0, 16, 0)

        title = QLabel(APP_NAME)
        title.setStyleSheet(
            "color: white; font-size: 12px; font-weight: 700; background: transparent;"
        )

        settings_btn = QPushButton("⚙")
        settings_btn.setFixedSize(32, 32)
        settings_btn.setStyleSheet("""
            QPushButton { background: transparent; border: none; color: #9CA3AF; font-size: 16px; }
            QPushButton:hover { color: white; }
        """)
        settings_btn.clicked.connect(self._open_settings)

        lay.addWidget(title)
        lay.addStretch()
        lay.addWidget(settings_btn)
        bar.setLayout(lay)
        return bar

    def _build_file_section(self) -> QFrame:
        lay = QVBoxLayout()
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(8)

        section_lbl = QLabel("파일 경로")
        section_lbl.setStyleSheet(
            "color: #9CA3AF; font-size: 10px; font-weight: 600; background: transparent; border: none;"
        )
        lay.addWidget(section_lbl)

        self._daily_path_row = _SlimFileRow("데일리 파일")
        self._daily_path_row.browse_clicked.connect(self._browse_daily)
        lay.addWidget(self._daily_path_row)

        self._total_path_row = _SlimFileRow("총매출 파일")
        self._total_path_row.browse_clicked.connect(self._browse_total)
        lay.addWidget(self._total_path_row)

        return _shadow_card(lay)

    def _build_sales_card(self) -> QFrame:
        lay = QVBoxLayout()
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        # 헤더
        header = QHBoxLayout()
        header_title = QLabel("오늘 매출 요약")
        header_title.setStyleSheet(
            "color: #111827; font-size: 14px; font-weight: 700; background: transparent; border: none;"
        )
        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedSize(28, 28)
        refresh_btn.setStyleSheet("""
            QPushButton { background: #F3F4F6; border: none; border-radius: 6px; font-size: 14px; color: #6B7280; }
            QPushButton:hover { background: #E5E7EB; }
        """)
        refresh_btn.clicked.connect(self._refresh_sales)
        header.addWidget(header_title)
        header.addStretch()
        header.addWidget(refresh_btn)
        lay.addLayout(header)

        # 통계 그리드
        row1 = QHBoxLayout()
        row1.setSpacing(10)
        cash_frame, self._cash_lbl = self._make_stat_frame("현금")
        card_frame, self._card_lbl = self._make_stat_frame("카드")
        row1.addWidget(cash_frame)
        row1.addWidget(card_frame)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        acct_frame, self._transfer_lbl = self._make_stat_frame("계좌")
        total_frame, self._total_lbl = self._make_stat_frame("총합", is_total=True)
        row2.addWidget(acct_frame)
        row2.addWidget(total_frame)
        lay.addLayout(row2)

        # 버튼 행
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        _btn_style = """
            QPushButton { background: #F3F4F6; color: #374151; border: none; border-radius: 8px; font-size: 13px; font-weight: 500; }
            QPushButton:hover { background: #E5E7EB; }
        """
        copy_btn = QPushButton("📋  보고 문구 복사")
        copy_btn.setFixedHeight(36)
        copy_btn.setStyleSheet(_btn_style)
        copy_btn.clicked.connect(self._copy_report)
        member_btn = QPushButton("👥  회원 현황 보고")
        member_btn.setFixedHeight(36)
        member_btn.setStyleSheet(_btn_style)
        member_btn.clicked.connect(self._copy_member_report)
        btn_row.addWidget(copy_btn)
        btn_row.addWidget(member_btn)
        lay.addLayout(btn_row)

        return _shadow_card(lay)

    def _make_stat_frame(self, label: str, is_total: bool = False) -> tuple[QFrame, QLabel]:
        frame = QFrame()
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bg = "#EFF6FF" if is_total else "#F9FAFB"
        frame.setObjectName("total-stat" if is_total else "stat")
        frame.setStyleSheet(f"""
            QFrame#{"total-stat" if is_total else "stat"} {{ background: {bg}; border-radius: 8px; }}
            QLabel {{ background: transparent; border: none; }}
        """)

        lay = QVBoxLayout()
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(4)

        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"color: {'#3B82F6' if is_total else '#6B7280'}; font-size: 11px; font-weight: {'600' if is_total else '500'};"
        )

        val_lbl = QLabel("—")
        val_lbl.setStyleSheet(
            f"color: {'#1D4ED8' if is_total else '#111827'}; font-size: 20px; font-weight: 700;"
        )

        lay.addWidget(lbl)
        lay.addWidget(val_lbl)
        frame.setLayout(lay)
        return frame, val_lbl

    def _build_shortcuts(self) -> QWidget:
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")

        lay = QVBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        lbl = QLabel("바로가기")
        lbl.setStyleSheet(
            "color: #9CA3AF; font-size: 10px; font-weight: 600; background: transparent; border: none;"
        )
        lay.addWidget(lbl)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        pay_btn = _BigBtn("💳", "매출 입력", "#3B82F6", "#2563EB")
        pay_btn.clicked.connect(self._open_payment)
        exp_btn = _BigBtn("🧾", "지출 입력", "#F59E0B", "#D97706")
        exp_btn.clicked.connect(self._open_expense)
        row1.addWidget(pay_btn)
        row1.addWidget(exp_btn)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        hist_btn = _BigBtn("📋", "내역 조회", "#8B5CF6", "#7C3AED")
        hist_btn.clicked.connect(self._open_entry_viewer)
        locker_btn = _BigBtn("🔑", "락카 현황", "#10B981", "#059669")
        locker_btn.clicked.connect(self._open_locker_dialog)
        row2.addWidget(hist_btn)
        row2.addWidget(locker_btn)
        lay.addLayout(row2)

        report_btn = QPushButton("📊  유입경로 보고서 생성")
        report_btn.setFixedHeight(36)
        report_btn.setStyleSheet("""
            QPushButton { background: #F3F4F6; color: #374151; border: none; border-radius: 8px; font-size: 13px; font-weight: 500; }
            QPushButton:hover { background: #E5E7EB; }
        """)
        report_btn.clicked.connect(self._generate_lead_report)
        lay.addWidget(report_btn)

        widget.setLayout(lay)
        return widget

    # ── 드래그 앤 드롭 (데일리 파일) ──────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            if any(u.toLocalFile().endswith(".xlsx") for u in event.mimeData().urls()):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [
            u.toLocalFile()
            for u in event.mimeData().urls()
            if u.toLocalFile().endswith(".xlsx")
        ]
        if paths:
            self._set_daily_path(paths[0])

    # ── 경로 관리 ─────────────────────────────────────────────────

    def _set_daily_path(self, path: str) -> None:
        self._path_daily = path
        self._daily_path_row.set_path(path)
        self._save_paths()
        self._ensure_next_file_exists()
        self._refresh_sales()

    def _set_total_path(self, path: str) -> None:
        self._path_total = path
        self._total_path_row.set_path(path)
        self._save_paths()

    def _browse_daily(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "데일리 엑셀 파일 선택", "", "Excel Files (*.xlsx)")
        if path:
            self._set_daily_path(path)

    def _browse_total(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "총매출 엑셀 파일 선택", "", "Excel Files (*.xlsx)")
        if path:
            self._set_total_path(path)

    # ── 자동 오늘 파일 설정 ───────────────────────────────────────

    def _auto_setup_today_file(self) -> None:
        saved = self._path_daily
        if not saved:
            return
        if not Path(saved).exists():
            QMessageBox.warning(
                self, "자동 파일 생성 실패",
                f"저장된 데일리 파일 경로를 찾을 수 없습니다.\n\n{saved}\n\n파일을 다시 선택해주세요."
            )
            return
        try:
            parsed = extract_date_from_filename(Path(saved).name)
            today = date.today()
            if parsed.to_date(today.year) == today:
                return

            old_str = f"{parsed.month}.{parsed.day}"
            new_str = f"{today.month}.{today.day}"
            today_path = Path(saved).parent / Path(saved).name.replace(old_str, new_str, 1)

            if today_path.exists():
                self._set_daily_path(str(today_path))
            else:
                created = create_next_daily_file(saved)
                self._set_daily_path(str(created))
                QMessageBox.information(
                    self, "자동 생성",
                    f"오늘 날짜 파일이 없어 자동으로 생성했습니다:\n{created.name}"
                )
        except Exception as exc:
            QMessageBox.warning(self, "자동 파일 생성 실패", str(exc))

    def _ensure_next_file_exists(self) -> None:
        saved = self._path_daily
        if not saved or not Path(saved).exists():
            return
        try:
            parsed = extract_date_from_filename(Path(saved).name)
            if parsed.to_date(date.today().year) != date.today():
                return
            create_next_daily_file(saved)
        except FileExistsError:
            pass
        except Exception as exc:
            QMessageBox.warning(self, "내일 파일 생성 실패", str(exc))

    def _check_date_change(self) -> None:
        today = date.today()
        if today != self._last_checked_date:
            self._last_checked_date = today
            self._auto_setup_today_file()

    # ── 매출 요약 ─────────────────────────────────────────────────

    def _refresh_sales(self) -> None:
        if not self._path_daily or not Path(self._path_daily).exists():
            for lbl in (self._cash_lbl, self._card_lbl, self._transfer_lbl, self._total_lbl):
                lbl.setText("—")
            return
        try:
            sales = read_sales_values(self._path_daily)
            fmt = lambda v: f"{int(v):,}원" if v is not None else "—"
            self._cash_lbl.setText(fmt(sales["cash"]))
            self._card_lbl.setText(fmt(sales["card"]))
            self._transfer_lbl.setText(fmt(sales["transfer"]))
            self._total_lbl.setText(fmt(sales["total"]))
        except Exception:
            for lbl in (self._cash_lbl, self._card_lbl, self._transfer_lbl, self._total_lbl):
                lbl.setText("—")

    def _copy_report(self) -> None:
        if not self._path_daily:
            QMessageBox.warning(self, "경고", "데일리 엑셀 파일을 선택해주세요.")
            return
        try:
            try:
                parsed = extract_date_from_filename(Path(self._path_daily).name)
                report_date = datetime(date.today().year, parsed.month, parsed.day)
            except ValueError:
                report_date = datetime.today()
            sales = read_sales_values(self._path_daily)
            text = build_sales_report_text(report_date, sales)
            QApplication.clipboard().setText(text)
            QMessageBox.information(self, "완료", "보고 문구를 클립보드에 복사했습니다.")
        except Exception as exc:
            QMessageBox.critical(self, "오류", str(exc))

    def _copy_member_report(self) -> None:
        try:
            records = load_records()
            counts = count_by_state(records)
            text = build_member_report_text(date.today(), counts)
            QApplication.clipboard().setText(text)
            QMessageBox.information(self, "완료", "회원 현황 보고 문구를 클립보드에 복사했습니다.")
        except Exception as exc:
            QMessageBox.critical(self, "오류", str(exc))

    def _generate_lead_report(self) -> None:
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "유입경로 보고서 저장",
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

    # ── 날짜 불일치 차단 ──────────────────────────────────────────

    def _check_daily_date(self) -> bool:
        if not self._path_daily:
            return True
        try:
            parsed = extract_date_from_filename(Path(self._path_daily).name)
            today = date.today()
            if parsed.month != today.month or parsed.day != today.day:
                QMessageBox.warning(
                    self, "날짜 불일치",
                    f"데일리 파일 날짜({parsed.month}월 {parsed.day}일)와 "
                    f"오늘 날짜({today.month}월 {today.day}일)가 다릅니다.\n\n"
                    "올바른 날짜의 데일리 파일을 선택한 후 다시 시도하세요.",
                )
                return False
        except ValueError:
            pass
        return True

    # ── 기능 슬롯 ─────────────────────────────────────────────────

    def _open_payment(self) -> None:
        if not self._check_daily_date():
            return
        PaymentDialog(
            daily_file=self._path_daily or None,
            total_sales_file=self._path_total or None,
            parent=self,
        ).exec()

    def _open_expense(self) -> None:
        if not self._check_daily_date():
            return
        from src.ui.expense_dialog import ExpenseDialog
        ExpenseDialog(
            daily_file=self._path_daily or None,
            total_sales_file=self._path_total or None,
            parent=self,
        ).exec()

    def _open_entry_viewer(self) -> None:
        from src.ui.entry_viewer_dialog import EntryViewerDialog
        EntryViewerDialog(
            daily_file=self._path_daily or None,
            total_sales_file=self._path_total or None,
            parent=self,
        ).exec()

    def _open_locker_dialog(self) -> None:
        from src.ui.locker_dialog import LockerDialog
        LockerDialog(parent=self).exec()

    def _open_settings(self) -> None:
        SettingsDialog(parent=self).exec()

    # ── 설정 저장/불러오기 ────────────────────────────────────────

    def _load_saved_paths(self) -> None:
        s = load_settings()
        if path := s.get(_KEY_DAILY_FILE):
            self._path_daily = path
            self._daily_path_row.set_path(path)
        if path := s.get(_KEY_TOTAL_SALES_FILE):
            self._path_total = path
            self._total_path_row.set_path(path)

    def _save_paths(self) -> None:
        s = load_settings()
        s[_KEY_DAILY_FILE] = self._path_daily
        s[_KEY_TOTAL_SALES_FILE] = self._path_total
        save_settings(s)
