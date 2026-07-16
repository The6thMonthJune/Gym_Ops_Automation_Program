from __future__ import annotations

from datetime import date

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from src.config.settings import (
    get_consult_spreadsheet_id,
    get_default_manager,
    get_default_part,
    get_gemini_api_key,
    get_google_credentials_path,
    get_new_db_sheet_name,
    get_new_db_spreadsheet_id,
)
from src.services.consultation_service import (
    _DAILY_DATA_END,
    _DAILY_DATA_START,
    _MONTHLY_DATA_START,
    get_client,
    get_or_create_month_sheet,
)
from src.services.new_member_db_service import get_new_db_sheet, transfer_all


class NewMemberDbDialog(QDialog):
    """예약관리 시트 → 신규DB 시트 Gemini 자동 이관 다이얼로그."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("신규DB 자동 이관")
        self.setMinimumWidth(500)
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout()
        root.setSpacing(12)

        desc = QLabel(
            "예약관리 시트의 상담 데이터를 Gemini AI가 분석하여\n"
            "신규DB 시트에 자동으로 이관합니다.\n"
            "전화번호 기준으로 중복 여부를 판별합니다."
        )
        desc.setStyleSheet("color: #374151; font-size: 13px;")
        root.addWidget(desc)

        self._include_daily = QCheckBox("데일리 예약 포함 (rows 4~16, 당일 입력분)")
        self._include_daily.setChecked(True)
        self._include_monthly = QCheckBox("월별 누적 포함 (row 19~)")
        self._include_monthly.setChecked(True)
        root.addWidget(self._include_daily)
        root.addWidget(self._include_monthly)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        root.addWidget(self._progress)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFixedHeight(220)
        self._log.setStyleSheet(
            "background: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 6px; font-size: 12px;"
        )
        root.addWidget(self._log)

        btn_row = QHBoxLayout()
        self._run_btn = QPushButton("이관 시작")
        self._run_btn.setFixedHeight(40)
        self._run_btn.setStyleSheet(
            "QPushButton { background: #1B2B3E; color: white; border: none; "
            "border-radius: 8px; font-size: 14px; font-weight: 700; }"
            "QPushButton:hover { background: #2D3F54; }"
            "QPushButton:disabled { background: #9CA3AF; }"
        )
        self._run_btn.clicked.connect(self._run)

        close_btn = QPushButton("닫기")
        close_btn.setFixedHeight(40)
        close_btn.setStyleSheet(
            "QPushButton { background: #F3F4F6; color: #374151; border: none; "
            "border-radius: 8px; font-size: 14px; }"
            "QPushButton:hover { background: #E5E7EB; }"
        )
        close_btn.clicked.connect(self.accept)

        btn_row.addWidget(self._run_btn)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

        self.setLayout(root)

    def _log_msg(self, msg: str) -> None:
        self._log.append(msg)
        QApplication.processEvents()

    def _run(self) -> None:
        api_key = get_gemini_api_key()
        consult_id = get_consult_spreadsheet_id()
        new_db_id = get_new_db_spreadsheet_id()
        new_db_sheet = get_new_db_sheet_name()

        if not api_key:
            QMessageBox.warning(self, "설정 필요", "설정에서 Gemini API 키를 먼저 입력해주세요.")
            return
        if not consult_id:
            QMessageBox.warning(self, "설정 필요", "설정에서 상담관리 시트 ID를 먼저 입력해주세요.")
            return
        if not new_db_id or not new_db_sheet:
            QMessageBox.warning(self, "설정 필요", "설정에서 신규DB 시트 ID와 시트명을 먼저 입력해주세요.")
            return

        self._run_btn.setEnabled(False)
        self._log.clear()

        defaults = {
            "part": get_default_part(),
            "type": "워크인",
            "manager": get_default_manager(),
            "counselor": get_default_manager(),
        }

        try:
            self._log_msg("구글 시트 연결 중...")
            client = get_client(get_google_credentials_path())
            today = date.today()
            consult_ws = get_or_create_month_sheet(client, consult_id, today.year, today.month)
            new_db_ws = get_new_db_sheet(client, new_db_id, new_db_sheet)
            self._log_msg("연결 완료.\n")

            rows: list[list] = []
            if self._include_daily.isChecked():
                daily = consult_ws.get(f"B{_DAILY_DATA_START}:I{_DAILY_DATA_END}") or []
                rows += [r for r in daily if any(str(c).strip() for c in r)]
            if self._include_monthly.isChecked():
                monthly = consult_ws.get(f"B{_MONTHLY_DATA_START}:I1000") or []
                rows += [r for r in monthly if any(str(c).strip() for c in r)]

            if not rows:
                self._log_msg("이관할 데이터가 없습니다.")
                self._run_btn.setEnabled(True)
                return

            self._log_msg(f"총 {len(rows)}건 분석 시작...\n")
            self._progress.setVisible(True)
            self._progress.setMaximum(len(rows))
            self._progress.setValue(0)

            success, updated, failed = 0, 0, 0
            for i, row in enumerate(rows):
                row = list(row) + [""] * (8 - len(row))
                name = row[1] or f"행 {i + 1}"
                self._log_msg(f"[{i + 1}/{len(rows)}] {name} 분석 중...")

                from src.services.gemini_service import analyze_consultation
                from src.services.new_member_db_service import (
                    append_new_member, find_by_phone, update_consultations,
                )
                row_data = {
                    "reserved_date": row[0], "name": row[1], "phone": row[2],
                    "visit_date": row[3], "category": row[4],
                    "amount": row[5], "is_new": row[6], "notes": row[7],
                }
                try:
                    parsed = analyze_consultation(api_key, row_data, defaults)
                    phone = row[2].strip()
                    existing = find_by_phone(new_db_ws, phone) if phone else None
                    if existing:
                        update_consultations(new_db_ws, existing, parsed.get("상담내역", []))
                        self._log_msg(f"  → 기존 행 상담 업데이트 (row {existing})")
                        updated += 1
                    else:
                        new_row = append_new_member(new_db_ws, parsed)
                        self._log_msg(f"  → 신규 행 추가 (row {new_row})")
                        success += 1
                except Exception as exc:
                    self._log_msg(f"  ✗ 오류: {exc}")
                    failed += 1

                self._progress.setValue(i + 1)

            self._log_msg(
                f"\n완료: 신규 {success}건 · 업데이트 {updated}건 · 실패 {failed}건"
            )

        except Exception as exc:
            self._log_msg(f"오류 발생: {exc}")
            QMessageBox.critical(self, "오류", str(exc))
        finally:
            self._run_btn.setEnabled(True)
