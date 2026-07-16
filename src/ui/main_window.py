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
from src.ui.countdown_dialog import CountdownDialog
from src.services.locker_service import (
    count_by_state, find_newly_expired, load_expiry_snapshot,
    load_records, merge_records, save_expiry_snapshot, save_records,
)
from src.ui.trend_dialog import TrendDialog
from src.services.broj_service import parse_xls
from src.services.snapshot_service import save_snapshot
from src.services.lead_report_service import generate_report
from src.ui.payment_dialog import PaymentDialog
from src.ui.settings_dialog import SettingsDialog
from src.config.constants import APP_NAME
from src.config.settings import (
    _KEY_DAILY_FILE,
    _KEY_TOTAL_SALES_FILE,
    get_nateon_webhook_url,
    load_settings,
    save_settings,
)
from src.services.nateon_service import send_webhook
from src.services.schedule_service import HolidayNotificationScheduler, SalesReportScheduler

_NAVY = "#1E2D3D"
_BG = "#F3F4F6"

APP_QSS = """
QWidget {
    font-family: "Malgun Gothic", "맑은 고딕", sans-serif;
    color: #111827;
}
QDialog {
    background-color: #ffffff;
}
QLabel {
    color: #111827;
    background-color: transparent;
}
QCheckBox {
    color: #111827;
    background-color: transparent;
}
QLineEdit {
    background-color: #ffffff;
    color: #111827;
    border: 1px solid #D1D5DB;
    border-radius: 4px;
    padding: 2px 6px;
    selection-background-color: #3B82F6;
    selection-color: #ffffff;
}
QTextEdit {
    background-color: #ffffff;
    color: #111827;
    border: 1px solid #D1D5DB;
    border-radius: 4px;
}
QListWidget {
    background-color: #ffffff;
    color: #111827;
    border: 1px solid #D1D5DB;
    border-radius: 4px;
}
QTableWidget {
    background-color: #ffffff;
    color: #111827;
    gridline-color: #E5E7EB;
}
QHeaderView::section {
    background-color: #F3F4F6;
    color: #374151;
    border: none;
    border-bottom: 1px solid #D1D5DB;
    padding: 4px 8px;
    font-weight: 600;
}
QScrollBar:vertical {
    background: #F3F4F6;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #D1D5DB;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
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

    def __init__(self, emoji: str, text: str, bg: str, hover: str, height: int = 90, parent=None) -> None:
        super().__init__(parent)
        self._bg = bg
        self._hover = hover
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self._paint(bg)

        font_size = 13 if height < 80 else 14
        emoji_size = 18 if height < 80 else 22

        lay = QVBoxLayout()
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(6)
        lay.setContentsMargins(6, 6, 6, 6)

        em = QLabel(emoji)
        em.setAlignment(Qt.AlignCenter)
        em.setStyleSheet(f"font-size: {emoji_size}px; background: transparent; border: none;")

        tx = QLabel(text)
        tx.setAlignment(Qt.AlignCenter)
        tx.setStyleSheet(f"color: white; font-size: {font_size}px; font-weight: 700; background: transparent; border: none;")

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
        self._last_checked_month = date.today().month
        timer = QTimer(self)
        timer.timeout.connect(self._check_date_change)
        timer.start(60_000)
        QTimer.singleShot(2000, self._check_monthly_sheet)
        QTimer.singleShot(1500, self._do_daily_consultation_rollover)
        QTimer.singleShot(3000, self._refresh_visitor_panel)

        self._scheduler = SalesReportScheduler(self)
        self._scheduler.send_triggered.connect(self._auto_send_sales_report)
        self._scheduler.start()
        self._refresh_auto_send_status()

        self._holiday_scheduler = HolidayNotificationScheduler(self)
        self._holiday_scheduler.triggered.connect(self._prompt_holiday_notification)
        self._holiday_scheduler.start()

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
        body_lay.addWidget(self._build_visitor_panel())
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

        self._auto_send_lbl = QLabel()
        self._auto_send_lbl.setStyleSheet("font-size: 11px; background: transparent;")

        lay.addWidget(title)
        lay.addStretch()
        lay.addWidget(self._auto_send_lbl)
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

        # Row 1: 매출 입력 + 지출 입력 (big, h=64)
        row1 = QHBoxLayout()
        row1.setSpacing(10)
        pay_btn = _BigBtn("💳", "매출 입력", "#3B82F6", "#2563EB", height=64)
        pay_btn.clicked.connect(self._open_payment)
        exp_btn = _BigBtn("🧾", "지출 입력", "#F59E0B", "#D97706", height=64)
        exp_btn.clicked.connect(self._open_expense)
        row1.addWidget(pay_btn)
        row1.addWidget(exp_btn)
        lay.addLayout(row1)

        # Row 2: 내역 조회 + 락카 현황 + 상담 입력 (medium, h=56)
        row2 = QHBoxLayout()
        row2.setSpacing(10)
        hist_btn = _BigBtn("📋", "내역 조회", "#8B5CF6", "#7C3AED", height=56)
        hist_btn.clicked.connect(self._open_entry_viewer)
        locker_btn = _BigBtn("🔑", "락카 현황", "#10B981", "#059669", height=56)
        locker_btn.clicked.connect(self._open_locker_dialog)
        consult_btn = _BigBtn("💬", "상담 입력", "#16A34A", "#15803D", height=56)
        consult_btn.clicked.connect(self._open_consultation)
        row2.addWidget(hist_btn)
        row2.addWidget(locker_btn)
        row2.addWidget(consult_btn)
        lay.addLayout(row2)

        # Row 3: slim — 회원 DB + 락카 DB 동기화 + 실장 기능
        _slim_gray = """
            QPushButton { background: #F3F4F6; color: #374151; border: none; border-radius: 8px; font-size: 13px; font-weight: 500; }
            QPushButton:hover { background: #E5E7EB; }
        """
        _slim_navy = """
            QPushButton { background: #1B2B3E; color: white; border: none; border-radius: 8px; font-size: 13px; font-weight: 600; }
            QPushButton:hover { background: #2D3F54; }
        """
        row3 = QHBoxLayout()
        row3.setSpacing(8)
        db_btn = QPushButton("🔄  회원 DB")
        db_btn.setFixedHeight(36)
        db_btn.setStyleSheet(_slim_gray)
        db_btn.clicked.connect(self._update_member_db)
        sync_btn = QPushButton("🔄  락카 DB 동기화")
        sync_btn.setFixedHeight(36)
        sync_btn.setStyleSheet(_slim_gray)
        sync_btn.clicked.connect(self._sync_locker_db)
        mgr_btn = QPushButton("⚙  실장 기능")
        mgr_btn.setFixedHeight(36)
        mgr_btn.setStyleSheet(_slim_navy)
        mgr_btn.clicked.connect(self._open_manager_dialog)
        row3.addWidget(db_btn)
        row3.addWidget(sync_btn)
        row3.addWidget(mgr_btn)
        lay.addLayout(row3)

        widget.setLayout(lay)
        return widget

    def _build_visitor_panel(self) -> QFrame:
        lay = QVBoxLayout()
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(8)

        header = QHBoxLayout()
        header_lbl = QLabel("오늘 방문예정")
        header_lbl.setStyleSheet(
            "color: #111827; font-size: 14px; font-weight: 700; background: transparent; border: none;"
        )
        self._visitor_badge = QLabel("—")
        self._visitor_badge.setStyleSheet(
            "background: #16A34A; color: white; font-size: 11px; font-weight: 700; "
            "border-radius: 8px; padding: 2px 8px;"
        )
        header.addWidget(header_lbl)
        header.addStretch()
        header.addWidget(self._visitor_badge)
        lay.addLayout(header)

        self._visitor_list_widget = QWidget()
        self._visitor_list_widget.setStyleSheet("background: transparent;")
        self._visitor_list_lay = QVBoxLayout()
        self._visitor_list_lay.setContentsMargins(0, 0, 0, 0)
        self._visitor_list_lay.setSpacing(4)
        placeholder = QLabel("스프레드시트 연결 후 표시됩니다.")
        placeholder.setStyleSheet(
            "color: #9CA3AF; font-size: 12px; background: transparent; border: none;"
        )
        self._visitor_list_lay.addWidget(placeholder)
        self._visitor_list_widget.setLayout(self._visitor_list_lay)
        lay.addWidget(self._visitor_list_widget)

        return _shadow_card(lay)

    def _refresh_visitor_panel(self) -> None:
        from src.config.settings import get_consult_spreadsheet_id, get_google_credentials_path
        sid = get_consult_spreadsheet_id()
        if not sid:
            return
        try:
            from src.services.consultation_service import get_todays_visitors
            visitors = get_todays_visitors(sid, get_google_credentials_path())
            while self._visitor_list_lay.count():
                child = self._visitor_list_lay.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            if visitors:
                self._visitor_badge.setText(f"{len(visitors)}명")
                for v in visitors:
                    row_lbl = QLabel(f"👤 {v['name']}  {v['phone']}")
                    row_lbl.setStyleSheet(
                        "color: #374151; font-size: 12px; background: transparent; border: none;"
                    )
                    self._visitor_list_lay.addWidget(row_lbl)
            else:
                self._visitor_badge.setText("0명")
                empty_lbl = QLabel("방문 예정 회원이 없습니다.")
                empty_lbl.setStyleSheet(
                    "color: #9CA3AF; font-size: 12px; background: transparent; border: none;"
                )
                self._visitor_list_lay.addWidget(empty_lbl)
        except Exception:
            pass

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
            self._do_daily_consultation_rollover()
            self._refresh_visitor_panel()
        if today.month != self._last_checked_month:
            self._last_checked_month = today.month
            self._check_monthly_sheet()

    def _check_monthly_sheet(self) -> None:
        if not self._path_total or not Path(self._path_total).exists():
            return
        today = date.today()
        try:
            from src.config.settings import get_password
            from src.services.total_sales_service import (
                find_monthly_expense_sheet_name, find_monthly_sheet_name, open_workbook,
            )
            wb = open_workbook(self._path_total, get_password())
            missing: list[str] = []
            try:
                find_monthly_sheet_name(wb.sheetnames, today.year, today.month)
            except ValueError:
                missing.append("매출")
            try:
                find_monthly_expense_sheet_name(wb.sheetnames, today.year, today.month)
            except ValueError:
                missing.append("지출")
            if missing:
                reply = QMessageBox.question(
                    self,
                    "이번 달 시트 없음",
                    f"총매출 파일에 {today.month}월 {'/'.join(missing)} 시트가 없습니다.\n"
                    "전월 시트를 복사해 자동 생성할까요?",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    self._create_monthly_sheet(today.year, today.month, "매출" in missing, "지출" in missing)
        except Exception:
            pass

    def _create_monthly_sheet(self, year: int, month: int, income: bool = True, expense: bool = True) -> None:
        try:
            from src.services.entry_service import create_monthly_expense_sheet, create_monthly_sheet
            from src.config.settings import get_password
            created: list[str] = []
            if income:
                name = create_monthly_sheet(self._path_total, year, month, get_password())
                created.append(f"매출: {name}")
            if expense:
                name = create_monthly_expense_sheet(self._path_total, year, month, get_password())
                created.append(f"지출: {name}")
            QMessageBox.information(
                self, "완료",
                f"{month}월 시트가 생성되었습니다.\n" + "\n".join(created)
            )
        except Exception as exc:
            QMessageBox.warning(self, "시트 생성 실패", str(exc))

    def _auto_send_sales_report(self) -> None:
        """스케줄러가 트리거하면 매출 보고 문구를 네이트온 웹훅으로 전송한다."""
        webhook_url = get_nateon_webhook_url()
        if not webhook_url:
            return
        if not self._path_daily or not Path(self._path_daily).exists():
            return
        try:
            parsed = extract_date_from_filename(Path(self._path_daily).name)
            report_date = datetime(date.today().year, parsed.month, parsed.day)
        except ValueError:
            report_date = datetime.today()
        try:
            sales = read_sales_values(self._path_daily)
            text = build_sales_report_text(report_date, sales)
            send_webhook(webhook_url, text)
        except Exception:
            pass  # 자동 전송 실패는 조용히 무시 (사용자 방해 안 함)

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
            dlg = TrendDialog(counts, self)
            dlg.exec()
        except Exception as exc:
            QMessageBox.critical(self, "오류", str(exc))

    def _update_member_db(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "브로제이 엑셀 파일 선택", "", "Excel Files (*.xls *.xlsx)"
        )
        if not path:
            return
        try:
            old_snapshot, had_snapshot = load_expiry_snapshot()

            records = parse_xls(path, delete_after=True)
            merged = merge_records(load_records(), records)
            save_records(merged)
            counts = count_by_state(merged)
            save_snapshot(date.today(), counts)
            save_expiry_snapshot(merged)

            from src.services.foreign_member_service import sync_from_locker_records
            sync_from_locker_records(merged)

            total = sum(counts.values())
            locker_count = sum(1 for r in records if r.locker_number > 0)
            QMessageBox.information(
                self, "완료",
                f"회원 DB 업데이트 완료\n"
                f"가져온 인원: {len(records)}명 (락카 배정: {locker_count}명) | 전체 DB: {total}명\n\n"
                f"활성 {counts['active']} · 만료 {counts['expired']} · "
                f"임박 {counts['imminent']} · 홀딩 {counts['holding']} · 미등록 {counts['unassigned']}",
            )

            if had_snapshot:
                newly_expired = find_newly_expired(old_snapshot, merged)
                if newly_expired:
                    self._prompt_newly_expired_locker(newly_expired)

        except Exception as exc:
            QMessageBox.critical(self, "오류", f"파일 파싱 실패:\n{exc}")

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

    def _open_membership_expiry(self) -> None:
        from src.ui.membership_expiry_dialog import MembershipExpiryDialog
        MembershipExpiryDialog(parent=self).exec()

    def _open_countdown(self) -> None:
        if not self._path_daily:
            QMessageBox.warning(self, "파일 미등록", "데일리 파일을 먼저 등록해주세요.")
            return
        CountdownDialog(self._path_daily, parent=self).exec()

    def _open_locker_sms(self) -> None:
        from src.ui.locker_sms_dialog import LockerSmsDialog
        LockerSmsDialog(parent=self).exec()

    def _sync_locker_db(self) -> None:
        import threading
        from PySide6.QtWidgets import QProgressDialog
        from src.config.settings import get_broj_credentials

        username, password = get_broj_credentials()
        if not username or not password:
            QMessageBox.warning(
                self, "설정 필요",
                "설정에서 브로제이 아이디/비밀번호를 먼저 입력해주세요.",
            )
            return

        reply = QMessageBox.question(
            self, "락카 DB 동기화",
            "동기화하는 동안 브로제이에 자동으로 로그인합니다.\n"
            "이 때 현재 열려 있는 브로제이 창에서 로그아웃될 수 있습니다.\n\n"
            "동기화가 끝난 후 브로제이를 새로 고침하거나 다시 로그인해주세요.\n\n"
            "지금 진행하시겠습니까?",
            QMessageBox.Ok | QMessageBox.Cancel,
        )
        if reply != QMessageBox.Ok:
            return

        progress = QProgressDialog(
            "브로제이에서 락카 데이터를 가져오는 중...\n(약 1~2분 소요)", None, 0, 0, self
        )
        progress.setWindowTitle("락카 DB 동기화")
        progress.setWindowModality(Qt.WindowModal)
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()

        errors: list = []
        locker_rows: list = []

        def _run() -> None:
            try:
                from src.services.locker_crawl_service import fetch_locker_records
                rows = fetch_locker_records(username, password)
                locker_rows.extend(rows)
            except Exception as exc:
                errors.append(str(exc))

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        while t.is_alive():
            QApplication.processEvents()
            t.join(timeout=0.1)

        progress.close()

        if errors:
            QMessageBox.critical(self, "동기화 실패", errors[0])
            return

        if not locker_rows:
            QMessageBox.warning(
                self, "동기화 실패",
                "수집된 락카 데이터가 없습니다.\n"
                "브로제이 아이디/비밀번호와 네트워크 연결을 확인해주세요.",
            )
            return

        try:
            from src.services.locker_service import sync_locker_expiries
            updated = sync_locker_expiries(locker_rows)
            QMessageBox.information(
                self, "동기화 완료",
                f"락카 DB 동기화 완료\n"
                f"락카 {len(locker_rows)}개 수집 · {updated}개 레코드 업데이트",
            )
        except Exception as exc:
            QMessageBox.critical(self, "파싱 오류", str(exc))

    def _prompt_newly_expired_locker(self, newly_expired) -> None:
        names = ", ".join(r.member_name for r in newly_expired[:5])
        if len(newly_expired) > 5:
            names += f" 외 {len(newly_expired) - 5}명"
        reply = QMessageBox.question(
            self,
            "신규 락카 만료자 발생",
            f"새로 락카가 만료된 회원이 {len(newly_expired)}명 있습니다.\n"
            f"({names})\n\n"
            "지금 안내 문자를 발송하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            from src.ui.locker_sms_dialog import LockerSmsDialog
            LockerSmsDialog(parent=self).exec()

    def _open_foreign_member(self) -> None:
        from src.ui.foreign_member_dialog import ForeignMemberDialog
        ForeignMemberDialog(parent=self).exec()

    def _open_consultation(self) -> None:
        from src.ui.consultation_dialog import ConsultationDialog
        ConsultationDialog(parent=self).exec()

    def _open_manager_dialog(self) -> None:
        from src.ui.manager_dialog import ManagerDialog
        ManagerDialog(daily_file=self._path_daily, parent=self).exec()

    def _do_daily_consultation_rollover(self) -> None:
        from src.config.settings import (
            get_auto_transfer_rollover, get_consult_spreadsheet_id, get_google_credentials_path,
        )
        sid = get_consult_spreadsheet_id()
        if not sid:
            return
        try:
            from src.services.consultation_service import do_daily_rollover
            do_daily_rollover(sid, get_google_credentials_path())
        except Exception:
            pass
        if get_auto_transfer_rollover():
            QTimer.singleShot(0, self._auto_transfer_new_member_db)

    def _auto_transfer_new_member_db(self) -> None:
        from src.config.settings import (
            get_default_manager, get_default_part, get_gemini_api_key,
            get_google_credentials_path, get_new_db_sheet_name, get_new_db_spreadsheet_id,
        )
        api_key = get_gemini_api_key()
        new_db_id = get_new_db_spreadsheet_id()
        new_db_sheet = get_new_db_sheet_name()
        if not api_key or not new_db_id or not new_db_sheet:
            return
        try:
            from datetime import date
            from src.services.consultation_service import (
                _DAILY_DATA_END, _DAILY_DATA_START, _MONTHLY_DATA_START,
                get_client, get_or_create_month_sheet,
            )
            from src.services.new_member_db_service import get_new_db_sheet as _get_ws, transfer_all
            from src.config.settings import get_consult_spreadsheet_id
            sid = get_consult_spreadsheet_id()
            if not sid:
                return
            client = get_client(get_google_credentials_path())
            today = date.today()
            consult_ws = get_or_create_month_sheet(client, sid, today.year, today.month)
            new_db_ws = _get_ws(client, new_db_id, new_db_sheet)
            daily = consult_ws.get(f"B{_DAILY_DATA_START}:I{_DAILY_DATA_END}") or []
            monthly = consult_ws.get(f"B{_MONTHLY_DATA_START}:I1000") or []
            rows = [r for r in daily + monthly if any(str(c).strip() for c in r)]
            defaults = {
                "part": get_default_part(), "type": "워크인",
                "manager": get_default_manager(), "counselor": get_default_manager(),
            }
            transfer_all(client, consult_ws, new_db_ws, api_key, defaults, rows)
        except Exception:
            pass

    def _prompt_holiday_notification(self) -> None:
        from src.ui.holiday_notification_dialog import HolidayNotificationDialog
        today = date.today()
        HolidayNotificationDialog(today.year, today.month, parent=self).exec()

    def _open_settings(self) -> None:
        SettingsDialog(parent=self).exec()
        self._refresh_auto_send_status()

    def _refresh_auto_send_status(self) -> None:
        if get_nateon_webhook_url():
            self._auto_send_lbl.setText("● 자동전송 ON")
            self._auto_send_lbl.setStyleSheet("font-size: 11px; color: #34D399; background: transparent;")
        else:
            self._auto_send_lbl.setText("● 자동전송 미설정")
            self._auto_send_lbl.setStyleSheet("font-size: 11px; color: #6B7280; background: transparent;")

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
