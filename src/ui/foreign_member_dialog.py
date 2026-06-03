from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from src.services.foreign_member_service import (
    add_foreign_member,
    load_foreign_members,
    remove_foreign_member,
)

_STATE_KO = {
    "active": "활성",
    "imminent": "임박",
    "expired": "만료",
    "holding": "홀딩",
    "unknown": "미확인",
}


class ForeignMemberDialog(QDialog):
    """
    외국인 회원 등록/삭제 다이얼로그.
    이름과 전화번호를 직접 등록하며, 회원 DB 업데이트 시 상태가 자동 갱신된다.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("외국인 회원 관리")
        self.setMinimumWidth(500)
        self._setup_ui()
        self._refresh_table()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setSpacing(10)

        guide = QLabel(
            "브로제이에서 외국인/내국인 구분이 없으므로 여기서 직접 등록합니다.\n"
            "회원 DB 업데이트 시 활성/만료 상태가 자동으로 갱신됩니다."
        )
        guide.setStyleSheet("color: #6B7280; font-size: 11px;")
        layout.addWidget(guide)

        # 테이블
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["이름", "전화번호", "상태", "만료일"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setFixedHeight(200)
        layout.addWidget(self._table)

        # 입력 행
        input_row = QHBoxLayout()
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("이름 (예: John Smith)")
        self._phone_input = QLineEdit()
        self._phone_input.setPlaceholderText("전화번호 (예: 01012345678)")
        add_btn = QPushButton("추가")
        add_btn.setFixedWidth(60)
        add_btn.clicked.connect(self._add)
        del_btn = QPushButton("삭제")
        del_btn.setFixedWidth(60)
        del_btn.clicked.connect(self._remove)
        input_row.addWidget(self._name_input)
        input_row.addWidget(self._phone_input)
        input_row.addWidget(add_btn)
        input_row.addWidget(del_btn)
        layout.addLayout(input_row)

        hint = QLabel("※ 상태는 '회원 DB 업데이트' 후 자동으로 갱신됩니다.")
        hint.setStyleSheet("color: #9CA3AF; font-size: 10px;")
        layout.addWidget(hint)

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self.setLayout(layout)

    def _refresh_table(self) -> None:
        members = load_foreign_members()
        self._table.setRowCount(len(members))
        for row, m in enumerate(members):
            self._table.setItem(row, 0, QTableWidgetItem(m.name))
            self._table.setItem(row, 1, QTableWidgetItem(m.phone_number))
            state_ko = _STATE_KO.get(m.membership_state, m.membership_state)
            state_item = QTableWidgetItem(state_ko)
            if m.membership_state == "active":
                state_item.setForeground(Qt.darkGreen)
            elif m.membership_state == "expired":
                state_item.setForeground(Qt.red)
            self._table.setItem(row, 2, state_item)
            expiry_str = m.expiry_date.strftime("%Y.%m.%d") if m.expiry_date else "-"
            self._table.setItem(row, 3, QTableWidgetItem(expiry_str))
        self._table.resizeColumnsToContents()

    def _add(self) -> None:
        name = self._name_input.text().strip()
        phone = self._phone_input.text().strip().replace("-", "")
        if not name or not phone:
            QMessageBox.warning(self, "입력 오류", "이름과 전화번호를 모두 입력해주세요.")
            return
        if not phone.isdigit():
            QMessageBox.warning(self, "입력 오류", "전화번호는 숫자만 입력해주세요.")
            return
        add_foreign_member(name, phone)
        self._name_input.clear()
        self._phone_input.clear()
        self._refresh_table()

    def _remove(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "선택 없음", "삭제할 회원을 선택해주세요.")
            return
        phone = self._table.item(row, 1).text()
        name = self._table.item(row, 0).text()
        reply = QMessageBox.question(
            self, "삭제 확인",
            f"{name} ({phone})을 외국인 회원 목록에서 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            remove_foreign_member(phone)
            self._refresh_table()
