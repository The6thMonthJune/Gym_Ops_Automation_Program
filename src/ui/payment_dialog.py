from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
)

from src.services.entry_service import PaymentEntry, write_entry_to_daily, write_entry_to_total_sales
from src.config.settings import get_password
from src.config.constants import PAYMENT_METHODS, SALES_CATEGORIES, LESSON_ONLY_CATEGORIES
from src.ui._kakao_send_widget import KakaoSendWidget
from src.ui.lead_dialog import LeadDialog

_MEMBERSHIP_TYPES = ["신규", "재등", "기존"]
_PAYMENT_METHODS = PAYMENT_METHODS
_CATEGORIES = SALES_CATEGORIES

# 레슨 구분에서만 선택 가능한 종목 (엑셀 수식 인식 기준)
_LESSON_ONLY_CATEGORIES = LESSON_ONLY_CATEGORIES
_LESSON_CATEGORIES = set(_LESSON_ONLY_CATEGORIES)  # 자동 구분 전환 기준


class PaymentDialog(QDialog):
    """
    결제 1건의 정보를 입력받아:
      1) 카톡 매출보고 문구를 생성하고
      2) 데일리 / 총매출 엑셀에 자동 입력한다.
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
        self._excel_saved = False  # 엑셀 저장 완료 여부
        self.setWindowTitle("결제 입력 및 보고 문구 생성")
        self.setMinimumWidth(560)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()

        # ── 센터 / 레슨 구분 ────────────────────────────────────────
        section_group = QGroupBox("매출 구분")
        section_layout = QHBoxLayout()

        self.section_btn_group = QButtonGroup(self)
        self.radio_center = QRadioButton("센터  (B열~)")
        self.radio_lesson = QRadioButton("레슨  (P열~)")
        self.radio_center.setChecked(True)
        self.section_btn_group.addButton(self.radio_center)
        self.section_btn_group.addButton(self.radio_lesson)

        section_layout.addWidget(self.radio_center)
        section_layout.addWidget(self.radio_lesson)
        section_layout.addStretch()
        section_group.setLayout(section_layout)
        layout.addWidget(section_group)

        self.radio_lesson.toggled.connect(self._on_section_changed)

        # ── 결제 정보 입력 ──────────────────────────────────────────
        form_group = QGroupBox("결제 정보")
        form = QFormLayout()

        today = QDate.currentDate()
        self.date_edit = QDateEdit(today)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        form.addRow("날짜:", self.date_edit)

        self.membership_type_combo = QComboBox()
        self.membership_type_combo.addItems(_MEMBERSHIP_TYPES)
        form.addRow("신규/재등:", self.membership_type_combo)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("결제자 이름")
        form.addRow("성함:", self.name_input)

        self.category_combo = QComboBox()
        self.category_combo.addItems(_CATEGORIES)
        self.category_combo.setEditable(True)
        self.category_combo.setPlaceholderText("목록에 없으면 직접 입력")
        self.category_combo.currentTextChanged.connect(self._auto_select_section)
        form.addRow("종목:", self.category_combo)

        self.membership_input = QLineEdit()
        self.membership_input.setPlaceholderText("예: 헬스 3개월, PT 10회 …")
        form.addRow("회원권:", self.membership_input)

        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("숫자만 입력 (예: 300000)")
        form.addRow("금액:", self.amount_input)

        self.payment_method_combo = QComboBox()
        self.payment_method_combo.addItems(_PAYMENT_METHODS)
        form.addRow("결제방법:", self.payment_method_combo)

        self.approval_input = QLineEdit()
        self.approval_input.setPlaceholderText("카드 결제 시 입력 (선택)")
        form.addRow("승인번호:", self.approval_input)

        self.fc_input = QLineEdit()
        self.fc_input.setPlaceholderText("예: 실장, 점장, 부경 … (선택)")
        form.addRow("FC:", self.fc_input)

        self.manager_input = QLineEdit()
        self.manager_input.setPlaceholderText("선택")
        form.addRow("담당:", self.manager_input)

        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("(선택) - 카톡 보고 문구 전용, 엑셀에는 등록되지 않습니다")
        form.addRow("특이사항:", self.note_input)

        form_group.setLayout(form)
        layout.addWidget(form_group)

        # ── 일일권 DB 추가 정보 (종목=일일권일 때만 표시) ──────────────
        self._daypass_group = QGroupBox("일일권 DB 추가 정보")
        dp_form = QFormLayout()

        self._daypass_route_combo = QComboBox()
        self._daypass_route_combo.addItems(
            ["네이버", "지인소개", "플레이스", "휴면회원", "간판", "홍보물", "전화"]
        )
        dp_form.addRow("방문경로:", self._daypass_route_combo)

        self._daypass_phone_input = QLineEdit()
        self._daypass_phone_input.setPlaceholderText("010-XXXX-XXXX (선택)")
        dp_form.addRow("전화번호:", self._daypass_phone_input)

        self._daypass_content_input = QLineEdit()
        self._daypass_content_input.setPlaceholderText("메모 (선택)")
        dp_form.addRow("내용:", self._daypass_content_input)

        self._daypass_group.setLayout(dp_form)
        self._daypass_group.setVisible(False)
        layout.addWidget(self._daypass_group)

        self.category_combo.currentTextChanged.connect(self._toggle_daypass_group)

        # ── 동작 버튼 ────────────────────────────────────────────────
        kakao_button = QPushButton("카톡 문구 생성")
        kakao_button.clicked.connect(self._generate_kakao_message)
        layout.addWidget(kakao_button)

        excel_button = QPushButton("엑셀에 입력 (데일리 + 총매출)")
        excel_button.clicked.connect(self._write_to_excel)
        layout.addWidget(excel_button)

        # ── 결과 출력 ─────────────────────────────────────────────────
        layout.addWidget(QLabel("생성된 카톡 문구:"))
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setMinimumHeight(180)
        layout.addWidget(self.output)

        copy_button = QPushButton("복사")
        copy_button.clicked.connect(self._copy_message)
        layout.addWidget(copy_button)

        self._kakao_widget = KakaoSendWidget(
            self._get_kakao_message,
            close_after_fn=lambda: self._excel_saved,
        )
        layout.addWidget(self._kakao_widget)

        self.setLayout(layout)

    # ── 섹션 자동 선택 ────────────────────────────────────────────

    def _on_section_changed(self, lesson_checked: bool) -> None:
        """레슨/센터 전환 시 종목 콤보박스 목록을 교체한다."""
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        if lesson_checked:
            self.category_combo.addItems(_LESSON_ONLY_CATEGORIES)
            self.category_combo.setEditable(False)
        else:
            self.category_combo.addItems(_CATEGORIES)
            self.category_combo.setEditable(True)
            self.category_combo.setPlaceholderText("목록에 없으면 직접 입력")
        self.category_combo.blockSignals(False)

    def _auto_select_section(self, category: str) -> None:
        """센터 모드에서 종목이 레슨 전용 항목이면 자동으로 레슨으로 전환한다."""
        if self.radio_lesson.isChecked():
            return  # 이미 레슨 모드이면 개입하지 않음
        if category.strip() in _LESSON_CATEGORIES:
            self.radio_lesson.setChecked(True)
        else:
            self.radio_center.setChecked(True)

    def _toggle_daypass_group(self, category: str) -> None:
        self._daypass_group.setVisible(category.strip() == "일일권")

    def _selected_section(self) -> str:
        return "레슨" if self.radio_lesson.isChecked() else "센터"

    # ── 내부 헬퍼 ──────────────────────────────────────────────────

    def _collect_entry(self) -> PaymentEntry | None:
        """폼 입력값을 검증하고 PaymentEntry를 반환한다. 오류 시 None."""
        name = self.name_input.text().strip()
        membership = self.membership_input.text().strip()
        amount_raw = self.amount_input.text().strip().replace(",", "")
        category = self.category_combo.currentText().strip()

        if not name:
            QMessageBox.warning(self, "경고", "성함을 입력해주세요.")
            return None
        if not membership:
            QMessageBox.warning(self, "경고", "회원권 종류를 입력해주세요.")
            return None
        if not amount_raw:
            QMessageBox.warning(self, "경고", "금액을 입력해주세요.")
            return None
        if not category:
            QMessageBox.warning(self, "경고", "종목을 입력해주세요.")
            return None
        if self._selected_section() == "레슨" and category not in _LESSON_CATEGORIES:
            QMessageBox.warning(
                self, "경고",
                f"레슨 구분에서는 종목을 {', '.join(_LESSON_ONLY_CATEGORIES)} 중에서만 선택할 수 있습니다."
            )
            return None

        try:
            amount = int(amount_raw)
        except ValueError:
            QMessageBox.warning(self, "경고", "금액은 숫자만 입력해주세요.")
            return None

        qdate = self.date_edit.date()
        entry_date = date(qdate.year(), qdate.month(), qdate.day())

        return PaymentEntry(
            entry_date=entry_date,
            name=name,
            category=category,
            membership=membership,
            amount=amount,
            payment_method=self.payment_method_combo.currentText(),
            section=self._selected_section(),
            approval_number=self.approval_input.text().strip(),
            fc=self.fc_input.text().strip(),
            manager=self.manager_input.text().strip(),
            note="",  # 특이사항은 카톡 문구 전용, 엑셀에는 기록하지 않음
        )

    # ── 슬롯 ──────────────────────────────────────────────────────

    def _generate_kakao_message(self) -> None:
        entry = self._collect_entry()
        if entry is None:
            return

        note = self.note_input.text().strip()
        message = (
            "📌매출보고📌\n\n"
            f"신규/재등 : {self.membership_type_combo.currentText()}\n"
            f"성함 : {entry.name}\n"
            f"회원권 : {entry.membership}\n"
            f"금액 : {entry.amount:,}원\n"
            f"결제방법: {entry.payment_method}\n"
            f"특이사항: {note}"
        )
        self.output.setPlainText(message)

    def _write_to_excel(self, force: bool = False) -> None:
        entry = self._collect_entry()
        if entry is None:
            return

        errors: list[str] = []
        results: list[str] = []
        duplicates: list[str] = []

        # 데일리 파일 입력
        if not self.daily_file:
            errors.append("데일리 파일이 지정되지 않았습니다.")
        else:
            try:
                row, is_dup = write_entry_to_daily(self.daily_file, entry, force=force)
                if is_dup:
                    duplicates.append("데일리 파일")
                else:
                    results.append(f"데일리 파일: {row}행에 입력 완료")
            except Exception as exc:
                errors.append(f"데일리 파일 오류: {exc}")

        # 총매출 파일 입력
        if not self.total_sales_file:
            errors.append("총매출 파일이 지정되지 않았습니다.")
        else:
            try:
                row, is_dup = write_entry_to_total_sales(
                    self.total_sales_file,
                    entry,
                    password=get_password(),
                    force=force,
                )
                if is_dup:
                    duplicates.append("총매출 파일")
                else:
                    results.append(f"총매출 파일: {row}행에 입력 완료")
            except Exception as exc:
                errors.append(f"총매출 파일 오류: {exc}")

        # 중복 감지 → 강제 입력 여부 확인
        if duplicates and not force:
            msg = (
                f"아래 파일에 같은 날짜·이름·금액의 항목이 이미 존재합니다:\n"
                f"  {', '.join(duplicates)}\n\n"
                "그래도 추가로 입력하시겠습니까?"
            )
            reply = QMessageBox.warning(
                self, "중복 감지",
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._write_to_excel(force=True)
            return

        if errors:
            QMessageBox.critical(self, "오류", "\n".join(errors))
        if results:
            self._excel_saved = True
            daypass_msg = ""
            if self.category_combo.currentText().strip() == "일일권":
                daypass_msg = self._write_to_daypass_db(entry)
            msg = "\n".join(results)
            if daypass_msg:
                msg += f"\n{daypass_msg}"
            QMessageBox.information(self, "완료", msg)
            if self.membership_type_combo.currentText() == "신규":
                dlg = LeadDialog(
                    member_name=self.name_input.text().strip(),
                    contract_date=entry.entry_date,
                    parent=self,
                )
                dlg.exec()

    def _write_to_daypass_db(self, entry: PaymentEntry) -> str:
        """일일권 DB 구글 시트에 기록하고 결과 문자열을 반환한다. 실패 시 경고 다이얼로그를 띄우고 빈 문자열 반환."""
        from src.config.settings import (
            get_daypass_db_spreadsheet_id,
            get_daypass_db_sheet_name,
            get_google_credentials_path,
        )
        from src.services.consultation_service import get_client
        from src.services.daypass_db_service import get_daypass_sheet, append_daypass_entry

        spreadsheet_id = get_daypass_db_spreadsheet_id()
        sheet_name = get_daypass_db_sheet_name()

        if not spreadsheet_id or not sheet_name:
            QMessageBox.warning(
                self, "일일권 DB",
                "설정에서 일일권DB 시트 ID와 시트명을 입력해주세요.\n엑셀 저장은 완료되었습니다.",
            )
            return ""

        try:
            client = get_client(get_google_credentials_path())
            ws = get_daypass_sheet(client, spreadsheet_id, sheet_name)
            row_data = {
                "manager": entry.manager,
                "route": self._daypass_route_combo.currentText(),
                "amount": entry.amount,
                "visit_date": f"{entry.entry_date.month:02d}/{entry.entry_date.day:02d}",
                "name": entry.name,
                "phone": self._daypass_phone_input.text().strip(),
                "content": self._daypass_content_input.text().strip(),
            }
            row_num = append_daypass_entry(ws, row_data)
            return f"일일권 DB: {row_num}행에 기록 완료"
        except Exception as exc:
            QMessageBox.warning(self, "일일권 DB 오류", f"구글 시트 기록 중 오류 발생:\n{exc}")
            return ""

    def _get_kakao_message(self) -> str | None:
        text = self.output.toPlainText().strip()
        return text if text else None

    def _copy_message(self) -> None:
        text = self.output.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "경고", "복사할 문구가 없습니다.")
            return
        QApplication.clipboard().setText(text)
        QMessageBox.information(self, "완료", "문구를 클립보드에 복사했습니다.")
