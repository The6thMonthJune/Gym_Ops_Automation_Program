from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.services.entry_reader_service import (
    ExpenseEntryRow,
    SalesEntryRow,
    calc_total_sales,
    read_expense_entries,
    read_sales_entries,
)
from src.services.entry_editor_service import delete_sales_row, delete_expense_row
from src.core.file_naming import extract_date_from_filename

_NAVY = "#1E2D3D"
_BLUE = "#4A6FA5"
_WHITE = "#FFFFFF"
_BG = "#F4F5F7"
_BORDER = "#D1D5DB"

_ROW_HEIGHT = 36
_HEADER_HEIGHT = 36
_VISIBLE_ROWS = 5

_SALES_HEADERS = ["날짜", "회원명", "종목", "회원권", "금액", "결제방법", "구분", "FC"]
_EXPENSE_HEADERS = ["날짜", "구분", "지출내용", "금액", "결제방법", "담당자", "거래처"]


class EntryViewerDialog(QDialog):
    def __init__(self, daily_file: str | None = None, total_sales_file: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self.daily_file = daily_file
        self.total_sales_file = total_sales_file
        self._sales: list[SalesEntryRow] = []
        self._expenses: list[ExpenseEntryRow] = []
        self._current_tab = "매출"
        self.setWindowTitle("내역 조회·수정")
        self.setMinimumWidth(780)
        self._setup_ui()
        if self.daily_file and Path(self.daily_file).exists():
            self._load_data()

    # ── UI 구성 ──────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 타이틀바
        title_bar = QWidget()
        title_bar.setFixedHeight(48)
        title_bar.setStyleSheet(f"background: {_NAVY};")
        tb_layout = QHBoxLayout()
        tb_layout.setContentsMargins(20, 0, 20, 0)
        title_lbl = QLabel("📋  내역 조회·수정")
        title_lbl.setStyleSheet("color: white; font-size: 13px; font-weight: 700; background: transparent;")
        tb_layout.addWidget(title_lbl)
        title_bar.setLayout(tb_layout)
        root.addWidget(title_bar)

        # 바디
        body = QWidget()
        body.setStyleSheet(f"background: {_BG};")
        body_layout = QVBoxLayout()
        body_layout.setContentsMargins(16, 16, 16, 16)
        body_layout.setSpacing(12)

        body_layout.addWidget(self._build_tab_row())
        body_layout.addWidget(self._build_table())
        body_layout.addWidget(self._build_action_bar())

        body.setLayout(body_layout)
        root.addWidget(body)
        self.setLayout(root)

    def _build_tab_row(self) -> QWidget:
        row = QWidget()
        row.setStyleSheet(f"""
            QWidget {{ background: {_WHITE}; border-radius: 8px; }}
        """)
        layout = QHBoxLayout()
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        self._tab_sales_btn = QPushButton("매출")
        self._tab_sales_btn.setFixedHeight(32)
        self._tab_sales_btn.clicked.connect(lambda: self._switch_tab("매출"))

        self._tab_expense_btn = QPushButton("지출")
        self._tab_expense_btn.setFixedHeight(32)
        self._tab_expense_btn.clicked.connect(lambda: self._switch_tab("지출"))

        layout.addWidget(self._tab_sales_btn)
        layout.addWidget(self._tab_expense_btn)
        layout.addStretch()

        self._total_label = QLabel("오늘 총 매출\n-")
        self._total_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._total_label.setStyleSheet(f"""
            font-size: 13px; color: {_NAVY}; background: transparent; font-weight: bold;
        """)
        layout.addWidget(self._total_label)

        row.setLayout(layout)
        self._refresh_tab_style()
        return row

    def _build_table(self) -> QTableWidget:
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setFixedHeight(_HEADER_HEIGHT)
        self.table.verticalHeader().setDefaultSectionSize(_ROW_HEIGHT)
        self.table.setFixedHeight(_HEADER_HEIGHT + _VISIBLE_ROWS * _ROW_HEIGHT + 2)
        self.table.setShowGrid(True)
        self.table.setStyleSheet(f"""
            QTableWidget {{
                border: 1px solid #E5E7EB;
                border-radius: 8px;
                background: {_WHITE};
                gridline-color: #F3F4F6;
                font-size: 11px;
            }}
            QHeaderView::section {{
                background-color: {_NAVY};
                color: white;
                font-size: 11px;
                font-weight: bold;
                border: none;
                padding: 0 8px;
            }}
            QTableWidget::item:selected {{
                background-color: #EFF6FF;
                color: {_NAVY};
            }}
        """)
        self._set_sales_columns()
        return self.table

    def _build_action_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._notice_lbl = QLabel("행을 선택 후 수정 또는 삭제하세요")
        self._notice_lbl.setStyleSheet(f"color: #9CA3AF; font-size: 11px; background: transparent;")
        layout.addWidget(self._notice_lbl)
        layout.addStretch()

        self._edit_btn = QPushButton("✏  수정")
        self._edit_btn.setFixedHeight(36)
        self._edit_btn.setStyleSheet("""
            QPushButton {
                background-color: #EFF6FF; color: #1D4ED8;
                border: 1px solid #BFDBFE; border-radius: 6px;
                font-size: 12px; font-weight: bold; padding: 0 16px;
            }
            QPushButton:hover { background-color: #DBEAFE; }
            QPushButton:disabled { background-color: #F9FAFB; color: #D1D5DB; border-color: #E5E7EB; }
        """)
        self._edit_btn.setEnabled(False)
        self._edit_btn.clicked.connect(self._on_edit)
        layout.addWidget(self._edit_btn)

        self._delete_btn = QPushButton("🗑  삭제")
        self._delete_btn.setFixedHeight(36)
        self._delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #FEF2F2; color: #DC2626;
                border: 1px solid #FECACA; border-radius: 6px;
                font-size: 12px; font-weight: bold; padding: 0 16px;
            }
            QPushButton:hover { background-color: #FEE2E2; }
            QPushButton:disabled { background-color: #F9FAFB; color: #D1D5DB; border-color: #E5E7EB; }
        """)
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._on_delete)
        layout.addWidget(self._delete_btn)

        bar.setLayout(layout)
        bar.setStyleSheet("background: transparent;")
        return bar

    # ── 탭 전환 ──────────────────────────────────────────────────

    def _switch_tab(self, tab: str) -> None:
        self._current_tab = tab
        self._refresh_tab_style()
        self._refresh_table()

    def _refresh_tab_style(self) -> None:
        active = f"background-color:{_NAVY}; color:white; border:none; border-radius:6px; font-size:12px; font-weight:bold; padding: 0 16px;"
        inactive = f"background-color:{_WHITE}; color:#374151; border:1px solid {_BORDER}; border-radius:6px; font-size:12px; padding: 0 16px;"
        self._tab_sales_btn.setStyleSheet(f"QPushButton {{ {active if self._current_tab == '매출' else inactive} }}")
        self._tab_expense_btn.setStyleSheet(f"QPushButton {{ {inactive if self._current_tab == '매출' else active} }}")

    # ── 데이터 로드 ───────────────────────────────────────────────

    def _load_data(self) -> None:
        try:
            self._sales = read_sales_entries(self.daily_file)
            self._expenses = read_expense_entries(self.daily_file)
        except Exception as exc:
            QMessageBox.warning(self, "데이터 로드 실패", str(exc))
            return
        self._update_total_label()
        self._refresh_table()

    def _update_total_label(self) -> None:
        total = calc_total_sales(self._sales)
        self._total_label.setText(f"오늘 총 매출\n{total:,}원")
        self._total_label.setStyleSheet(f"""
            QLabel {{
                font-size: 13px; color: {_NAVY}; background: transparent;
                font-weight: bold; qproperty-alignment: AlignRight;
            }}
        """)

    def _on_selection_changed(self) -> None:
        has = bool(self.table.selectedItems())
        self._edit_btn.setEnabled(has)
        self._delete_btn.setEnabled(has)

    def _refresh_table(self) -> None:
        self._edit_btn.setEnabled(False)
        self._delete_btn.setEnabled(False)
        if self._current_tab == "매출":
            self._set_sales_columns()
            self._populate_sales()
        else:
            self._set_expense_columns()
            self._populate_expenses()

    # ── 테이블 컬럼 설정 ─────────────────────────────────────────

    def _set_sales_columns(self) -> None:
        self.table.setColumnCount(len(_SALES_HEADERS))
        self.table.setHorizontalHeaderLabels(_SALES_HEADERS)
        header = self.table.horizontalHeader()
        col_widths = [44, 80, 60, 140, 90, 80, 52, 64]
        for i, w in enumerate(col_widths):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(i, w)
        header.setStretchLastSection(True)

    def _set_expense_columns(self) -> None:
        self.table.setColumnCount(len(_EXPENSE_HEADERS))
        self.table.setHorizontalHeaderLabels(_EXPENSE_HEADERS)
        header = self.table.horizontalHeader()
        col_widths = [44, 80, 160, 90, 72, 64, 100]
        for i, w in enumerate(col_widths):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(i, w)
        header.setStretchLastSection(True)

    # ── 테이블 데이터 채우기 ─────────────────────────────────────

    def _populate_sales(self) -> None:
        self.table.setRowCount(len(self._sales))
        for row_idx, entry in enumerate(self._sales):
            bg = "#F9FAFB" if row_idx % 2 else _WHITE
            values = [
                str(entry.day),
                entry.name,
                entry.category,
                entry.membership,
                f"{entry.amount:,}원",
                entry.payment_method,
                entry.section,
                entry.fc,
            ]
            for col_idx, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setBackground(Qt.GlobalColor.white if bg == _WHITE else Qt.GlobalColor.lightGray)
                item.setForeground(Qt.GlobalColor.black)
                self.table.setItem(row_idx, col_idx, item)

        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)

    def _populate_expenses(self) -> None:
        self.table.setRowCount(len(self._expenses))
        for row_idx, entry in enumerate(self._expenses):
            values = [
                str(entry.day),
                entry.category,
                entry.description,
                f"{entry.amount:,}원",
                entry.payment_method,
                entry.manager,
                entry.vendor,
            ]
            for col_idx, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setForeground(Qt.GlobalColor.black)
                self.table.setItem(row_idx, col_idx, item)

        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)

    # ── 수정 ─────────────────────────────────────────────────────

    def _on_edit(self) -> None:
        if not self.table.selectedItems():
            return
        if not self.daily_file:
            QMessageBox.warning(self, "오류", "데일리 파일이 지정되지 않았습니다.")
            return

        from src.ui.entry_edit_dialog import ExpenseEditDialog, SalesEditDialog

        row_idx = self.table.currentRow()
        if self._current_tab == "매출":
            dlg = SalesEditDialog(self._sales[row_idx], self.daily_file,
                                  total_sales_file=self.total_sales_file, parent=self)
        else:
            dlg = ExpenseEditDialog(self._expenses[row_idx], self.daily_file, parent=self)

        if dlg.exec() == dlg.DialogCode.Accepted:
            self._load_data()

    # ── 삭제 ─────────────────────────────────────────────────────

    def _on_delete(self) -> None:
        selected = self.table.selectedItems()
        if not selected:
            return

        row_idx = self.table.currentRow()
        if self._current_tab == "매출":
            entry = self._sales[row_idx]
            name = entry.name
        else:
            entry = self._expenses[row_idx]
            name = entry.description

        reply = QMessageBox.warning(
            self, "삭제 확인",
            f"'{name}' 항목을 데일리 파일에서 삭제합니다.\n\n"
            "⚠️  총매출 파일은 수동으로 수정해야 합니다.\n"
            "계속하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if not self.daily_file:
            QMessageBox.warning(self, "오류", "데일리 파일이 지정되지 않았습니다.")
            return

        try:
            if self._current_tab == "매출":
                delete_sales_row(self.daily_file, entry.row_num, entry.section)
            else:
                delete_expense_row(self.daily_file, entry.row_num)
            QMessageBox.information(self, "완료", "데일리 파일에서 삭제했습니다.")
            self._load_data()
        except Exception as exc:
            QMessageBox.critical(self, "삭제 실패", str(exc))
