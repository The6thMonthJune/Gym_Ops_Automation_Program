from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
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

from src.services.daily_file_service import create_next_daily_file
from src.services.sales_report_service import (
    build_sales_report_text,
    read_sales_values,
)
from src.config.constants import APP_NAME


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)

        self.template_file_input = QLineEdit()
        self.report_file_input = QLineEdit()
        self.report_output = QTextEdit()
        self.report_output.setReadOnly(True)

        self._setup_ui()

    def _setup_ui(self) -> None:
        central_widget = QWidget()
        main_layout = QVBoxLayout()

        main_layout.addWidget(QLabel("기준 엑셀 파일"))
        main_layout.addLayout(self._build_template_file_row())

        create_button = QPushButton("다음 날짜 파일 생성")
        create_button.clicked.connect(self.handle_create_next_file)
        main_layout.addWidget(create_button)

        main_layout.addWidget(QLabel("보고용 엑셀 파일"))
        main_layout.addLayout(self._build_report_file_row())

        report_button = QPushButton("매출 보고 문구 생성")
        report_button.clicked.connect(self.handle_generate_report)
        main_layout.addWidget(report_button)

        main_layout.addWidget(QLabel("생성 결과"))
        main_layout.addWidget(self.report_output)

        copy_button = QPushButton("복사")
        copy_button.clicked.connect(self.handle_copy_report)
        main_layout.addWidget(copy_button)

        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

    def _build_template_file_row(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        browse_button = QPushButton("파일 선택")
        browse_button.clicked.connect(self.handle_select_template_file)

        layout.addWidget(self.template_file_input)
        layout.addWidget(browse_button)
        return layout

    def _build_report_file_row(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        browse_button = QPushButton("파일 선택")
        browse_button.clicked.connect(self.handle_select_report_file)

        layout.addWidget(self.report_file_input)
        layout.addWidget(browse_button)
        return layout

    def handle_select_template_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "기준 엑셀 파일 선택",
            "",
            "Excel Files (*.xlsx)",
        )
        if file_path:
            self.template_file_input.setText(file_path)

    def handle_select_report_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "보고용 엑셀 파일 선택",
            "",
            "Excel Files (*.xlsx)",
        )
        if file_path:
            self.report_file_input.setText(file_path)

    def handle_create_next_file(self) -> None:
        source_file = self.template_file_input.text().strip()
        if not source_file:
            QMessageBox.warning(self, "경고", "기준 엑셀 파일을 선택해주세요.")
            return

        try:
            created_path = create_next_daily_file(source_file)
            QMessageBox.information(
                self,
                "완료",
                f"다음 날짜 파일 생성 완료:\n{created_path}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "오류", str(exc))

    def handle_generate_report(self) -> None:
        report_file = self.report_file_input.text().strip()
        if not report_file:
            QMessageBox.warning(self, "경고", "보고용 엑셀 파일을 선택해주세요.")
            return

        try:
            sales = read_sales_values(report_file)
            report_text = build_sales_report_text(datetime.today(), sales)
            self.report_output.setPlainText(report_text)
        except Exception as exc:
            QMessageBox.critical(self, "오류", str(exc))

    def handle_copy_report(self) -> None:
        text = self.report_output.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "경고", "복사할 문구가 없습니다.")
            return

        clipboard = self.clipboard()
        clipboard.setText(text)
        QMessageBox.information(self, "완료", "문구를 클립보드에 복사했습니다.")
