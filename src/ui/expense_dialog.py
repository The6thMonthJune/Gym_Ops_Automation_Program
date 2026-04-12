from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from src.services.expense_service import (
    EXPENSE_CATEGORIES,
    EXPENSE_PAYMENT_METHODS,
    ExpenseEntry,
    write_expense_to_daily,
    write_expense_to_total,
)
from src.config.settings import get_password, get_expense_daily_sheet


class ExpenseDialog(QDialog):
    """
    지출 1건을 입력받아:
      1) 카톡 지출보고 문구를 생성하고
      2) 데일리 / 총매출 지출 시트에 자동 입력한다.
    """

    def __init__(
        self,
        daily_file: str | None = None,
        total_sales_file: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.daily_file = daily_file
        self.total_sales_file = total_sales_file
        self.setWindowTitle("지출 입력 및 보고 문구 생성")
        self.setMinimumWidth(520)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()

        # ── 입력 폼 ──────────────────────────────────────────────────
        form_group = QGroupBox("지출 정보")
        form = QFormLayout()

        today = QDate.currentDate()
        self.date_edit = QDateEdit(today)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        form.addRow("일자:", self.date_edit)

        self.category_combo = QComboBox()
        self.category_combo.addItems(EXPENSE_CATEGORIES)
        form.addRow("구분:", self.category_combo)

        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("예: 청테이프 2개")
        form.addRow("지출내용:", self.description_input)

        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("숫자만 입력 (예: 4960)")
        form.addRow("금액:", self.amount_input)

        self.payment_combo = QComboBox()
        self.payment_combo.addItems(EXPENSE_PAYMENT_METHODS)
        form.addRow("결제:", self.payment_combo)

        self.manager_input = QLineEdit()
        self.manager_input.setPlaceholderText("예: 인포, 실장")
        form.addRow("담당자:", self.manager_input)

        self.vendor_input = QLineEdit()
        self.vendor_input.setPlaceholderText("예: 삼육오마트 일산 중산점")
        form.addRow("거래처:", self.vendor_input)

        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("없으면 공란")
        form.addRow("기타:", self.note_input)

        form_group.setLayout(form)
        layout.addWidget(form_group)

        # ── 버튼 ─────────────────────────────────────────────────────
        kakao_btn = QPushButton("카톡 문구 생성")
        kakao_btn.clicked.connect(self._generate_message)
        layout.addWidget(kakao_btn)

        excel_btn = QPushButton("엑셀에 입력 (데일리 + 총매출)")
        excel_btn.clicked.connect(self._write_to_excel)
        layout.addWidget(excel_btn)

        # ── 출력 ─────────────────────────────────────────────────────
        layout.addWidget(QLabel("생성된 카톡 문구:"))
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setMinimumHeight(200)
        layout.addWidget(self.output)

        copy_btn = QPushButton("복사")
        copy_btn.clicked.connect(self._copy_message)
        layout.addWidget(copy_btn)

        self.setLayout(layout)

    # ── 내부 헬퍼 ────────────────────────────────────────────────────

    def _collect_entry(self) -> ExpenseEntry | None:
        description = self.description_input.text().strip()
        amount_raw = self.amount_input.text().strip().replace(",", "")
        manager = self.manager_input.text().strip()
        vendor = self.vendor_input.text().strip()

        if not description:
            QMessageBox.warning(self, "경고", "지출내용을 입력해주세요.")
            return None
        if not amount_raw:
            QMessageBox.warning(self, "경고", "금액을 입력해주세요.")
            return None
        try:
            amount = int(amount_raw)
        except ValueError:
            QMessageBox.warning(self, "경고", "금액은 숫자만 입력해주세요.")
            return None

        qdate = self.date_edit.date()
        entry_date = date(qdate.year(), qdate.month(), qdate.day())

        return ExpenseEntry(
            entry_date=entry_date,
            category=self.category_combo.currentText(),
            description=description,
            amount=amount,
            payment_method=self.payment_combo.currentText(),
            manager=manager,
            vendor=vendor,
            note=self.note_input.text().strip(),
        )

    # ── 슬롯 ─────────────────────────────────────────────────────────

    def _generate_message(self) -> None:
        entry = self._collect_entry()
        if entry is None:
            return

        msg = (
            "📌지출보고📌\n\n"
            f"일자: {entry.entry_date.strftime('%Y.%m.%d')}\n"
            f"구분: {entry.category}\n"
            f"지출내용: {entry.description}\n"
            f"금액 : ₩{entry.amount:,}\n"
            f"결제방법: {entry.payment_method}\n"
            f"담당자: {entry.manager}\n"
            f"거래처: {entry.vendor}"
        )
        if entry.note:
            msg += f"\n기타: {entry.note}"
        self.output.setPlainText(msg)

    def _write_to_excel(self) -> None:
        entry = self._collect_entry()
        if entry is None:
            return

        sheet_name = get_expense_daily_sheet()
        if not sheet_name:
            QMessageBox.warning(
                self, "경고",
                "지출 시트 이름이 설정되지 않았습니다.\n⚙ 설정에서 '지출 시트 이름'을 입력해주세요."
            )
            return

        errors: list[str] = []
        results: list[str] = []

        if not self.daily_file:
            errors.append("데일리 파일이 지정되지 않았습니다.")
        else:
            try:
                row = write_expense_to_daily(self.daily_file, sheet_name, entry)
                results.append(f"데일리 파일: {row}행에 입력 완료")
            except Exception as exc:
                errors.append(f"데일리 파일 오류: {exc}")

        if not self.total_sales_file:
            errors.append("총매출 파일이 지정되지 않았습니다.")
        else:
            try:
                row = write_expense_to_total(
                    self.total_sales_file, entry, password=get_password()
                )
                results.append(f"총매출 파일: {row}행에 입력 완료")
            except Exception as exc:
                errors.append(f"총매출 파일 오류: {exc}")

        if errors:
            QMessageBox.critical(self, "오류", "\n".join(errors))
        if results:
            QMessageBox.information(self, "완료", "\n".join(results))

    def _copy_message(self) -> None:
        text = self.output.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "경고", "복사할 문구가 없습니다.")
            return
        QApplication.clipboard().setText(text)
        QMessageBox.information(self, "완료", "문구를 클립보드에 복사했습니다.")
