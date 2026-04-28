from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent
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
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.core.file_naming import extract_date_from_filename
from src.services.daily_file_service import create_next_daily_file
from src.services.sales_report_service import build_sales_report_text, read_sales_values
from src.ui.payment_dialog import PaymentDialog
from src.ui.settings_dialog import SettingsDialog
from src.config.constants import APP_NAME
from src.config.settings import (
    load_settings,
    save_settings,
    _KEY_DAILY_FILE,
    _KEY_TOTAL_SALES_FILE,
)

# ── 색상 ────────────────────────────────────────────────────────
_NAVY   = "#1E2D3D"
_BLUE   = "#4A6FA5"
_WHITE  = "#FFFFFF"
_BG     = "#F4F5F7"
_BORDER = "#D1D5DB"

APP_QSS = f"""
QWidget {{ font-family: "Malgun Gothic", "맑은 고딕", sans-serif; }}

/* 카드 */
QFrame#card {{
    background: {_WHITE};
    border: 1px solid #E5E7EB;
    border-radius: 8px;
}}

/* 드롭존 — QLabel 자식도 배경 투명 처리 */
QFrame#drop-zone {{
    background-color: #F0F5FF;
    border: 2px dashed {_BLUE};
    border-radius: 6px;
    min-height: 100px;
}}
QFrame#drop-zone[drag-hover="true"] {{
    background-color: #D6E4FF;
    border-color: #2A5AB3;
}}
QFrame#drop-zone QLabel {{
    background-color: transparent;
    border: none;
}}

/* 파일 경로 박스 */
QFrame#file-path-box {{
    background-color: {_BG};
    border: 1px solid {_BORDER};
    border-radius: 4px;
    min-height: 32px;
    max-height: 32px;
}}
QFrame#file-path-box[has-file="true"] {{
    background-color: #F0F5FF;
    border-color: {_BLUE};
}}
QFrame#file-path-box QLabel {{
    background-color: transparent;
    border: none;
    color: #9CA3AF;
    font-size: 11px;
}}
QFrame#file-path-box[has-file="true"] QLabel {{
    color: {_NAVY};
}}

/* 섹션 라벨 */
QLabel#section-label {{
    font-size: 12px; font-weight: 700; color: {_NAVY};
    background: transparent; border: none;
}}
QLabel#drop-hint {{
    color: #6B7FA8; font-size: 11px;
    background: transparent; border: none;
}}

/* 버튼 공통 */
QPushButton {{ outline: none; }}

QPushButton#btn-browse {{
    background-color: {_BLUE}; color: white; border: none;
    border-radius: 4px; font-size: 11px; font-weight: 700;
    min-width: 72px; max-width: 72px; min-height: 32px; max-height: 32px;
}}
QPushButton#btn-browse:hover {{ background-color: #3B5998; }}

QPushButton#btn-primary {{
    background-color: {_NAVY}; color: white; border: none;
    border-radius: 6px; font-size: 12px; font-weight: 700;
    min-height: 36px; max-height: 36px;
}}
QPushButton#btn-primary:hover {{ background-color: #2A3F56; }}

QPushButton#btn-secondary {{
    background-color: {_BG}; color: #374151;
    border: 1px solid {_BORDER}; border-radius: 6px;
    font-size: 12px; min-height: 36px; max-height: 36px;
}}
QPushButton#btn-secondary:hover {{ background-color: #E9EBF0; }}

QPushButton#btn-expense {{
    background-color: #FFF7ED; color: #EA580C;
    border: 1px solid #FED7AA; border-radius: 6px;
    font-size: 12px; font-weight: 700;
    min-height: 44px; max-height: 44px;
}}
QPushButton#btn-expense:hover {{ background-color: #FFEDD5; }}

QPushButton#btn-payment {{
    background-color: #F0FDF4; color: #16A34A;
    border: 1px solid #BBF7D0; border-radius: 6px;
    font-size: 12px; font-weight: 700;
    min-height: 44px; max-height: 44px;
}}
QPushButton#btn-payment:hover {{ background-color: #DCFCE7; }}

QPushButton#btn-viewer {{
    background-color: #EFF6FF; color: #1D4ED8;
    border: 1px solid #BFDBFE; border-radius: 6px;
    font-size: 12px; font-weight: 700;
    min-height: 44px; max-height: 44px;
}}
QPushButton#btn-viewer:hover {{ background-color: #DBEAFE; }}

QPushButton#btn-settings {{
    background-color: {_WHITE}; color: #6B7280;
    border: 1px solid {_BORDER}; border-radius: 6px;
    font-size: 12px; min-height: 36px; max-height: 36px;
}}
QPushButton#btn-settings:hover {{ background-color: {_BG}; }}

QTextEdit#result-text {{
    background-color: #F9FAFB; border: 1px solid #E5E7EB;
    border-radius: 6px; font-size: 12px; color: {_NAVY};
    padding: 6px;
}}
"""


# ── 드롭존 위젯 ──────────────────────────────────────────────────

class DropZone(QFrame):
    """점선 드롭 영역. 파일을 드롭하거나 직접 setText로 경로 설정 가능."""

    file_dropped = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("drop-zone")
        self.setAcceptDrops(True)

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(4)
        layout.setContentsMargins(12, 12, 12, 12)

        icon = QLabel("↑")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(f"font-size: 20px; color: {_BLUE}; background: transparent;")

        hint = QLabel("오늘 날짜의 엑셀 파일을 여기에 드래그하거나\n'파일 선택'을 눌러주세요")
        hint.setObjectName("drop-hint")
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)

        layout.addWidget(icon)
        layout.addWidget(hint)
        self.setLayout(layout)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            if any(u.toLocalFile().endswith(".xlsx") for u in event.mimeData().urls()):
                self.setProperty("drag-hover", "true")
                self._refresh_style()
                event.acceptProposedAction()
                return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self.setProperty("drag-hover", "false")
        self._refresh_style()

    def dropEvent(self, event: QDropEvent) -> None:
        self.setProperty("drag-hover", "false")
        self._refresh_style()
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.toLocalFile().endswith(".xlsx")]
        if paths:
            self.file_dropped.emit(paths[0])

    def _refresh_style(self) -> None:
        self.style().unpolish(self)
        self.style().polish(self)


# ── 파일 경로 표시 위젯 ──────────────────────────────────────────

class FilePathRow(QWidget):
    """파일 경로 라벨 + 파일 선택 버튼 행."""

    browse_clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._box = QFrame()
        self._box.setObjectName("file-path-box")
        box_layout = QHBoxLayout()
        box_layout.setContentsMargins(10, 0, 10, 0)
        self._label = QLabel("파일이 등록되면 여기에 파일명이 표시됩니다")
        self._label.setObjectName("path-text")
        box_layout.addWidget(self._label)
        self._box.setLayout(box_layout)

        browse_btn = QPushButton("파일 선택")
        browse_btn.setFixedSize(72, 32)
        browse_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_BLUE}; color: white; border: none;
                border-radius: 4px; font-size: 11px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #3B5998; }}
        """)
        browse_btn.clicked.connect(self.browse_clicked)

        layout.addWidget(self._box)
        layout.addWidget(browse_btn)
        self.setLayout(layout)

    def set_path(self, path: str) -> None:
        has = bool(path)
        display = Path(path).name if has else "파일이 등록되면 여기에 파일명이 표시됩니다"
        self._label.setText(display)
        self._label.setProperty("has-file", "true" if has else "false")
        self._box.setProperty("has-file", "true" if has else "false")
        for w in (self._label, self._box):
            w.style().unpolish(w)
            w.style().polish(w)


# ── 카드 팩토리 ──────────────────────────────────────────────────

def _card(layout: QVBoxLayout | QHBoxLayout) -> QFrame:
    frame = QFrame()
    frame.setObjectName("card")
    frame.setLayout(layout)
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(8)
    shadow.setOffset(0, 2)
    shadow.setColor(QColor(0, 0, 0, 20))
    frame.setGraphicsEffect(shadow)
    return frame


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("section-label")
    return lbl


# ── 메인 윈도우 ──────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setStyleSheet(APP_QSS)
        self._path_daily = ""
        self._path_total = ""
        self._setup_ui()
        self._load_saved_paths()
        self._auto_setup_today_file()
        self._ensure_next_file_exists()

        self._last_checked_date = date.today()
        timer = QTimer(self)
        timer.timeout.connect(self._check_date_change)
        timer.start(60_000)

    # ── UI 구성 ────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        central.setStyleSheet(f"background: {_BG};")

        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 타이틀바
        root.addWidget(self._build_title_bar())

        # 본문 스크롤 영역
        body = QWidget()
        body.setStyleSheet(f"background: {_BG};")
        body_layout = QVBoxLayout()
        body_layout.setContentsMargins(16, 16, 16, 16)
        body_layout.setSpacing(12)

        body_layout.addWidget(self._build_daily_card())
        body_layout.addWidget(self._build_result_card())
        body_layout.addWidget(self._build_action_card())
        body_layout.addWidget(self._build_total_card())
        body_layout.addWidget(self._build_locker_card())
        body_layout.addWidget(self._build_settings_btn())

        body.setLayout(body_layout)
        root.addWidget(body)

        central.setLayout(root)
        self.setCentralWidget(central)

    def _build_title_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(48)
        bar.setStyleSheet(f"background: {_NAVY};")
        layout = QHBoxLayout()
        layout.setContentsMargins(20, 0, 20, 0)
        title = QLabel(APP_NAME)
        title.setStyleSheet("color: white; font-size: 13px; font-weight: 700; background: transparent;")
        layout.addWidget(title)
        bar.setLayout(layout)
        return bar

    def _build_daily_card(self) -> QFrame:
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        layout.addWidget(_section_label("📅  데일리 엑셀 파일"))

        self._drop_zone = DropZone()
        self._drop_zone.file_dropped.connect(self._set_daily_path)
        layout.addWidget(self._drop_zone)

        self._daily_path_row = FilePathRow()
        self._daily_path_row.browse_clicked.connect(self._browse_daily)
        layout.addWidget(self._daily_path_row)

        report_btn = QPushButton("↗  매출 보고 문구 생성")
        report_btn.setFixedHeight(36)
        report_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_NAVY}; color: white; border: none;
                border-radius: 6px; font-size: 12px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #2A3F56; }}
        """)
        report_btn.clicked.connect(self._generate_report)
        layout.addWidget(report_btn)

        return _card(layout)

    def _build_result_card(self) -> QFrame:
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        layout.addWidget(_section_label("💬  생성 결과"))

        self._result_text = QTextEdit()
        self._result_text.setObjectName("result-text")
        self._result_text.setReadOnly(True)
        self._result_text.setFixedHeight(140)
        self._result_text.setPlaceholderText("매출 보고 문구 생성 버튼을 누르면 여기에 네이트온 문구가 표시됩니다.")
        layout.addWidget(self._result_text)

        copy_btn = QPushButton("📋  복사")
        copy_btn.setFixedHeight(36)
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_BG}; color: #374151;
                border: 1px solid {_BORDER}; border-radius: 6px; font-size: 12px;
            }}
            QPushButton:hover {{ background-color: #E9EBF0; }}
        """)
        copy_btn.clicked.connect(self._copy_report)
        layout.addWidget(copy_btn)

        return _card(layout)

    def _build_action_card(self) -> QFrame:
        layout = QHBoxLayout()
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        expense_btn = QPushButton("🧾  지출 입력")
        expense_btn.setObjectName("btn-expense")
        expense_btn.clicked.connect(self._open_expense)

        payment_btn = QPushButton("💳  결제 입력")
        payment_btn.setObjectName("btn-payment")
        payment_btn.clicked.connect(self._open_payment)

        viewer_btn = QPushButton("📋  내역 조회")
        viewer_btn.setObjectName("btn-viewer")
        viewer_btn.clicked.connect(self._open_entry_viewer)

        layout.addWidget(expense_btn)
        layout.addWidget(payment_btn)
        layout.addWidget(viewer_btn)

        return _card(layout)

    def _build_total_card(self) -> QFrame:
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        layout.addWidget(_section_label("🗄  총매출 엑셀 파일"))

        self._total_path_row = FilePathRow()
        self._total_path_row.browse_clicked.connect(self._browse_total)
        layout.addWidget(self._total_path_row)

        return _card(layout)

    def _build_locker_card(self) -> QFrame:
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        layout.addWidget(_section_label("🔐  락카 관리"))

        locker_btn = QPushButton("🔒  락카 현황 열기")
        locker_btn.setFixedHeight(44)
        locker_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #EEF2FF; color: #4338CA;
                border: 1px solid #C7D2FE; border-radius: 6px;
                font-size: 12px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #E0E7FF; }}
        """)
        locker_btn.clicked.connect(self._open_locker_dialog)
        layout.addWidget(locker_btn)

        return _card(layout)

    def _build_settings_btn(self) -> QPushButton:
        btn = QPushButton("⚙  설정")
        btn.setFixedHeight(36)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_WHITE}; color: #6B7280;
                border: 1px solid {_BORDER}; border-radius: 6px; font-size: 12px;
            }}
            QPushButton:hover {{ background-color: {_BG}; }}
        """)
        btn.clicked.connect(self._open_settings)
        return btn

    # ── 경로 관리 ──────────────────────────────────────────────

    def _set_daily_path(self, path: str) -> None:
        self._path_daily = path
        self._daily_path_row.set_path(path)
        self._save_paths()
        self._ensure_next_file_exists()

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

    # ── 자동 오늘 파일 설정 ────────────────────────────────────

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
            new_str  = f"{today.month}.{today.day}"
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
        """오늘 파일이 등록된 상태에서 내일 날짜 파일을 미리 생성한다."""
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

    # ── 기능 슬롯 ──────────────────────────────────────────────

    def _generate_report(self) -> None:
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
            self._result_text.setPlainText(build_sales_report_text(report_date, sales))
        except Exception as exc:
            QMessageBox.critical(self, "오류", str(exc))

    def _copy_report(self) -> None:
        text = self._result_text.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "경고", "복사할 문구가 없습니다.")
            return
        QApplication.clipboard().setText(text)
        QMessageBox.information(self, "완료", "문구를 클립보드에 복사했습니다.")

    def _check_daily_date(self) -> bool:
        """데일리 파일의 날짜가 오늘 날짜와 일치하는지 확인한다.
        불일치하면 경고창을 표시하고 False를 반환한다."""
        if not self._path_daily:
            return True  # 파일 미지정은 다이얼로그 내부에서 처리
        try:
            parsed = extract_date_from_filename(Path(self._path_daily).name)
            today = date.today()
            if parsed.month != today.month or parsed.day != today.day:
                file_date = f"{parsed.month}월 {parsed.day}일"
                today_str = f"{today.month}월 {today.day}일"
                QMessageBox.warning(
                    self,
                    "날짜 불일치",
                    f"데일리 파일 날짜({file_date})와 오늘 날짜({today_str})가 다릅니다.\n\n"
                    "올바른 날짜의 데일리 파일을 선택한 후 다시 시도하세요.",
                )
                return False
        except ValueError:
            pass  # 파일명에서 날짜를 읽을 수 없으면 통과
        return True

    def _open_expense(self) -> None:
        if not self._check_daily_date():
            return
        from src.ui.expense_dialog import ExpenseDialog
        ExpenseDialog(
            daily_file=self._path_daily or None,
            total_sales_file=self._path_total or None,
            parent=self,
        ).exec()

    def _open_payment(self) -> None:
        if not self._check_daily_date():
            return
        PaymentDialog(
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

    # ── 설정 저장/불러오기 ─────────────────────────────────────

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
