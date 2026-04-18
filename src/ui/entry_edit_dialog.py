from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.config.constants import LESSON_ONLY_CATEGORIES, PAYMENT_METHODS, SALES_CATEGORIES
from src.services.entry_editor_service import edit_expense_row, edit_sales_row
from src.services.entry_reader_service import ExpenseEntryRow, SalesEntryRow
from src.services.expense_service import EXPENSE_CATEGORIES, EXPENSE_PAYMENT_METHODS

_NAVY = "#1E2D3D"
_BG = "#F4F5F7"


def _title_bar(text: str) -> QWidget:
    bar = QWidget()
    bar.setFixedHeight(48)
    bar.setStyleSheet(f"background: {_NAVY};")
    layout = QHBoxLayout()
    layout.setContentsMargins(20, 0, 20, 0)
    lbl = QLabel(text)
    lbl.setStyleSheet("color: white; font-size: 13px; font-weight: 700; background: transparent;")
    layout.addWidget(lbl)
    bar.setLayout(layout)
    return bar


def _save_btn() -> QPushButton:
    btn = QPushButton("저장")
    btn.setFixedHeight(36)
    btn.setStyleSheet(f"""
        QPushButton {{
            background-color: {_NAVY}; color: white; border: none;
            border-radius: 6px; font-size: 12px; font-weight: bold;
            padding: 0 20px;
        }}
        QPushButton:hover {{ background-color: #2A3F56; }}
    """)
    return btn


def _cancel_btn() -> QPushButton:
    btn = QPushButton("취소")
    btn.setFixedHeight(36)
    btn.setStyleSheet("""
        QPushButton {
            background-color: #F3F4F6; color: #374151;
            border: 1px solid #D1D5DB; border-radius: 6px;
            font-size: 12px; padding: 0 16px;
        }
        QPushButton:hover { background-color: #E5E7EB; }
    """)
    return btn


class SalesEditDialog(QDialog):
    """선택된 매출 행의 값을 수정하는 폼 다이얼로그."""

    def __init__(self, entry: SalesEntryRow, daily_file: str, parent=None) -> None:
        super().__init__(parent)
        self.entry = entry
        self.daily_file = daily_file
        self.setWindowTitle("매출 내역 수정")
        self.setMinimumWidth(420)
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(_title_bar("✏  매출 내역 수정"))

        body = QWidget()
        body.setStyleSheet(f"background: {_BG};")
        body_layout = QVBoxLayout()
        body_layout.setContentsMargins(20, 16, 20, 16)
        body_layout.setSpacing(12)

        # 읽기 전용 정보
        info = QFormLayout()
        info.addRow("구분:", QLabel(self.entry.section))
        info.addRow("날짜:", QLabel(f"{self.entry.day}일"))
        body_layout.addLayout(info)

        # 수정 가능 필드
        form = QFormLayout()
        form.setSpacing(8)

        self._name = QLineEdit(self.entry.name)
        form.addRow("회원명:", self._name)

        self._category = QComboBox()
        cats = SALES_CATEGORIES if self.entry.section == "센터" else LESSON_ONLY_CATEGORIES
        self._category.addItems(cats)
        if self.entry.category in cats:
            self._category.setCurrentText(self.entry.category)
        else:
            self._category.setEditable(True)
            self._category.addItem(self.entry.category)
            self._category.setCurrentText(self.entry.category)
        form.addRow("종목:", self._category)

        self._membership = QLineEdit(self.entry.membership)
        form.addRow("회원권:", self._membership)

        self._amount = QLineEdit(str(self.entry.amount))
        self._amount.setPlaceholderText("숫자만 입력")
        form.addRow("금액:", self._amount)

        self._payment = QComboBox()
        self._payment.addItems(PAYMENT_METHODS)
        if self.entry.payment_method in PAYMENT_METHODS:
            self._payment.setCurrentText(self.entry.payment_method)
        form.addRow("결제방법:", self._payment)

        self._fc = QLineEdit(self.entry.fc)
        form.addRow("FC:", self._fc)

        self._manager = QLineEdit(self.entry.manager)
        form.addRow("담당:", self._manager)

        body_layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = _cancel_btn()
        cancel.clicked.connect(self.reject)
        save = _save_btn()
        save.clicked.connect(self._on_save)
        btn_row.addWidget(cancel)
        btn_row.addWidget(save)
        body_layout.addLayout(btn_row)

        body.setLayout(body_layout)
        root.addWidget(body)
        self.setLayout(root)

    def _on_save(self) -> None:
        name = self._name.text().strip()
        membership = self._membership.text().strip()
        amount_raw = self._amount.text().strip().replace(",", "")

        if not name:
            QMessageBox.warning(self, "경고", "회원명을 입력해주세요.")
            return
        if not membership:
            QMessageBox.warning(self, "경고", "회원권을 입력해주세요.")
            return
        try:
            amount = int(amount_raw)
        except ValueError:
            QMessageBox.warning(self, "경고", "금액은 숫자만 입력해주세요.")
            return

        try:
            edit_sales_row(
                self.daily_file,
                self.entry.row_num,
                self.entry.section,
                name=name,
                category=self._category.currentText().strip(),
                membership=membership,
                amount=amount,
                payment_method=self._payment.currentText(),
                fc=self._fc.text().strip(),
                manager=self._manager.text().strip(),
            )
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "저장 실패", str(exc))


class ExpenseEditDialog(QDialog):
    """선택된 지출 행의 값을 수정하는 폼 다이얼로그."""

    def __init__(self, entry: ExpenseEntryRow, daily_file: str, parent=None) -> None:
        super().__init__(parent)
        self.entry = entry
        self.daily_file = daily_file
        self.setWindowTitle("지출 내역 수정")
        self.setMinimumWidth(420)
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(_title_bar("✏  지출 내역 수정"))

        body = QWidget()
        body.setStyleSheet(f"background: {_BG};")
        body_layout = QVBoxLayout()
        body_layout.setContentsMargins(20, 16, 20, 16)
        body_layout.setSpacing(12)

        info = QFormLayout()
        info.addRow("날짜:", QLabel(f"{self.entry.day}일"))
        body_layout.addLayout(info)

        form = QFormLayout()
        form.setSpacing(8)

        self._category = QComboBox()
        self._category.addItems(EXPENSE_CATEGORIES)
        if self.entry.category in EXPENSE_CATEGORIES:
            self._category.setCurrentText(self.entry.category)
        form.addRow("구분:", self._category)

        self._description = QLineEdit(self.entry.description)
        form.addRow("지출내용:", self._description)

        self._amount = QLineEdit(str(self.entry.amount))
        self._amount.setPlaceholderText("숫자만 입력")
        form.addRow("금액:", self._amount)

        self._payment = QComboBox()
        self._payment.addItems(EXPENSE_PAYMENT_METHODS)
        if self.entry.payment_method in EXPENSE_PAYMENT_METHODS:
            self._payment.setCurrentText(self.entry.payment_method)
        form.addRow("결제방법:", self._payment)

        self._manager = QLineEdit(self.entry.manager)
        form.addRow("담당자:", self._manager)

        self._vendor = QLineEdit(self.entry.vendor)
        form.addRow("거래처:", self._vendor)

        body_layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = _cancel_btn()
        cancel.clicked.connect(self.reject)
        save = _save_btn()
        save.clicked.connect(self._on_save)
        btn_row.addWidget(cancel)
        btn_row.addWidget(save)
        body_layout.addLayout(btn_row)

        body.setLayout(body_layout)
        root.addWidget(body)
        self.setLayout(root)

    def _on_save(self) -> None:
        description = self._description.text().strip()
        amount_raw = self._amount.text().strip().replace(",", "")

        if not description:
            QMessageBox.warning(self, "경고", "지출내용을 입력해주세요.")
            return
        try:
            amount = int(amount_raw)
        except ValueError:
            QMessageBox.warning(self, "경고", "금액은 숫자만 입력해주세요.")
            return

        try:
            edit_expense_row(
                self.daily_file,
                self.entry.row_num,
                category=self._category.currentText(),
                description=description,
                amount=amount,
                payment_method=self._payment.currentText(),
                manager=self._manager.text().strip(),
                vendor=self._vendor.text().strip(),
            )
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "저장 실패", str(exc))
