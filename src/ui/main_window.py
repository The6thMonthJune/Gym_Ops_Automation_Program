from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.core.file_naming import extract_date_from_filename
from src.services.daily_file_service import create_next_daily_file
from src.services.sales_report_service import (
    build_sales_report_text,
    read_sales_values,
)
from src.ui.payment_dialog import PaymentDialog
from src.ui.settings_dialog import SettingsDialog
from src.config.constants import APP_NAME
from src.config.settings import (
    load_settings,
    save_settings,
    _KEY_TEMPLATE_FILE,
    _KEY_DAILY_FILE,
    _KEY_TOTAL_SALES_FILE,
)


class FileDropLineEdit(QLineEdit):
    """
    드래그 & 드롭과 파일 탐색기 선택을 모두 지원하는 파일 경로 입력 위젯.
    .xlsx 파일만 허용하며, 여러 파일을 드롭하면 첫 번째만 사용한다.
    """

    def __init__(self, placeholder: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setPlaceholderText(placeholder)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        mime = event.mimeData()
        if mime.hasUrls():
            paths = [u.toLocalFile() for u in mime.urls()]
            if any(p.endswith(".xlsx") for p in paths):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [u.toLocalFile() for u in event.mimeData().urls()]
        xlsx_paths = [p for p in paths if p.endswith(".xlsx")]
        if xlsx_paths:
            self.setText(xlsx_paths[0])


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)

        placeholder = "파일을 드래그하거나 '파일 선택' 버튼을 누르세요"
        self.template_file_input = FileDropLineEdit(placeholder=placeholder)
        self.report_file_input = FileDropLineEdit(placeholder=placeholder)
        self.total_sales_file_input = FileDropLineEdit(placeholder=placeholder)
        self.report_output = QTextEdit()
        self.report_output.setReadOnly(True)

        self._setup_ui()
        self._load_saved_paths()

        # 경로가 바뀔 때마다 자동 저장
        self.template_file_input.textChanged.connect(self._save_paths)
        self.report_file_input.textChanged.connect(self._save_paths)
        self.total_sales_file_input.textChanged.connect(self._save_paths)

    def _setup_ui(self) -> None:
        central_widget = QWidget()
        main_layout = QVBoxLayout()

        # ── 다음 날짜 파일 생성 ───────────────────────────────────────
        main_layout.addWidget(QLabel("기준 엑셀 파일"))
        main_layout.addLayout(self._build_file_row(
            self.template_file_input, self.handle_select_template_file
        ))
        create_button = QPushButton("다음 날짜 파일 생성")
        create_button.clicked.connect(self.handle_create_next_file)
        main_layout.addWidget(create_button)

        main_layout.addSpacing(8)

        # ── 매출 보고 문구 생성 ──────────────────────────────────────
        main_layout.addWidget(QLabel("데일리 엑셀 파일"))
        main_layout.addLayout(self._build_file_row(
            self.report_file_input, self.handle_select_report_file
        ))
        report_button = QPushButton("매출 보고 문구 생성")
        report_button.clicked.connect(self.handle_generate_report)
        main_layout.addWidget(report_button)

        main_layout.addWidget(QLabel("생성 결과"))
        main_layout.addWidget(self.report_output)

        copy_button = QPushButton("복사")
        copy_button.clicked.connect(self.handle_copy_report)
        main_layout.addWidget(copy_button)

        main_layout.addSpacing(8)

        # ── 지출 입력 ────────────────────────────────────────────────
        expense_button = QPushButton("💸 지출 입력 및 카톡 문구 생성")
        expense_button.clicked.connect(self.handle_open_expense_dialog)
        main_layout.addWidget(expense_button)

        main_layout.addSpacing(4)

        # ── 결제 입력 ────────────────────────────────────────────────
        main_layout.addWidget(QLabel("총매출 엑셀 파일"))
        main_layout.addLayout(self._build_file_row(
            self.total_sales_file_input, self.handle_select_total_sales_file
        ))
        payment_button = QPushButton("📌 결제 입력 및 카톡 문구 생성")
        payment_button.clicked.connect(self.handle_open_payment_dialog)
        main_layout.addWidget(payment_button)

        main_layout.addSpacing(8)

        settings_button = QPushButton("⚙ 설정")
        settings_button.clicked.connect(self.handle_open_settings)
        main_layout.addWidget(settings_button)

        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

    def _build_file_row(self, line_edit: FileDropLineEdit, handler) -> QHBoxLayout:
        layout = QHBoxLayout()
        browse_button = QPushButton("파일 선택")
        browse_button.clicked.connect(handler)
        layout.addWidget(line_edit)
        layout.addWidget(browse_button)
        return layout

    # ── 파일 선택 슬롯 ─────────────────────────────────────────────

    def handle_select_template_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "기준 엑셀 파일 선택", "", "Excel Files (*.xlsx)"
        )
        if path:
            self.template_file_input.setText(path)

    def handle_select_report_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "데일리 엑셀 파일 선택", "", "Excel Files (*.xlsx)"
        )
        if path:
            self.report_file_input.setText(path)

    def handle_select_total_sales_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "총매출 엑셀 파일 선택", "", "Excel Files (*.xlsx)"
        )
        if path:
            self.total_sales_file_input.setText(path)

    # ── 기능 슬롯 ──────────────────────────────────────────────────

    def handle_create_next_file(self) -> None:
        source_file = self.template_file_input.text().strip()
        if not source_file:
            QMessageBox.warning(self, "경고", "기준 엑셀 파일을 선택해주세요.")
            return
        try:
            created_path = create_next_daily_file(source_file)
            QMessageBox.information(self, "완료", f"다음 날짜 파일 생성 완료:\n{created_path}")
        except Exception as exc:
            QMessageBox.critical(self, "오류", str(exc))

    def handle_generate_report(self) -> None:
        report_file = self.report_file_input.text().strip()
        if not report_file:
            QMessageBox.warning(self, "경고", "데일리 엑셀 파일을 선택해주세요.")
            return
        try:
            try:
                parsed = extract_date_from_filename(Path(report_file).name)
                report_date = datetime(date.today().year, parsed.month, parsed.day)
            except ValueError:
                report_date = datetime.today()

            sales = read_sales_values(report_file)
            report_text = build_sales_report_text(report_date, sales)
            self.report_output.setPlainText(report_text)
        except Exception as exc:
            QMessageBox.critical(self, "오류", str(exc))

    def handle_open_settings(self) -> None:
        SettingsDialog(parent=self).exec()

    def handle_open_expense_dialog(self) -> None:
        from src.ui.expense_dialog import ExpenseDialog
        dialog = ExpenseDialog(
            daily_file=self.report_file_input.text().strip() or None,
            total_sales_file=self.total_sales_file_input.text().strip() or None,
            parent=self,
        )
        dialog.exec()

    def handle_open_payment_dialog(self) -> None:
        dialog = PaymentDialog(
            daily_file=self.report_file_input.text().strip() or None,
            total_sales_file=self.total_sales_file_input.text().strip() or None,
            parent=self,
        )
        dialog.exec()

    def _load_saved_paths(self) -> None:
        settings = load_settings()
        if path := settings.get(_KEY_TEMPLATE_FILE):
            self.template_file_input.setText(path)
        if path := settings.get(_KEY_DAILY_FILE):
            self.report_file_input.setText(path)
        if path := settings.get(_KEY_TOTAL_SALES_FILE):
            self.total_sales_file_input.setText(path)

    def _save_paths(self) -> None:
        save_settings({
            _KEY_TEMPLATE_FILE: self.template_file_input.text().strip(),
            _KEY_DAILY_FILE: self.report_file_input.text().strip(),
            _KEY_TOTAL_SALES_FILE: self.total_sales_file_input.text().strip(),
        })

    def handle_copy_report(self) -> None:
        text = self.report_output.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "경고", "복사할 문구가 없습니다.")
            return
        QApplication.clipboard().setText(text)
        QMessageBox.information(self, "완료", "문구를 클립보드에 복사했습니다.")
