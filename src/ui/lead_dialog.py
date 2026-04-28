from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from src.services.lead_service import CHANNELS, MemberLead, save_lead


class LeadDialog(QDialog):
    """
    신규 회원 가입 시 유입경로와 거주지를 입력받는 다이얼로그.
    매출 입력에서 '신규' 선택 후 엑셀 저장 완료 시 자동으로 팝업된다.
    """

    def __init__(
        self,
        member_name: str,
        contract_date: date,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.member_name = member_name
        self.contract_date = contract_date
        self.setWindowTitle("신규 회원 정보 입력")
        self.setMinimumWidth(360)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setSpacing(12)

        # 안내 문구
        guide = QLabel(f"<b>{self.member_name}</b> 회원님의 추가 정보를 입력해주세요.")
        guide.setAlignment(Qt.AlignCenter)
        layout.addWidget(guide)

        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapAllRows)

        # 가입경로 라디오 버튼
        self._channel_group = QButtonGroup(self)
        channel_row = QHBoxLayout()
        channel_row.setSpacing(8)
        self._channel_radios: dict[str, QRadioButton] = {}
        for ch in CHANNELS:
            rb = QRadioButton(ch)
            self._channel_group.addButton(rb)
            channel_row.addWidget(rb)
            self._channel_radios[ch] = rb
        self._channel_radios[CHANNELS[0]].setChecked(True)
        channel_widget = QWidget()
        channel_widget.setLayout(channel_row)
        form.addRow("가입경로:", channel_widget)

        # 기타 세부 입력 (기타 선택 시 활성화)
        self._detail_input = QLineEdit()
        self._detail_input.setPlaceholderText("기타 경로 입력 (선택)")
        self._detail_input.setEnabled(False)
        form.addRow("", self._detail_input)
        self._channel_radios["기타"].toggled.connect(
            lambda checked: self._detail_input.setEnabled(checked)
        )

        # 거주지역
        self._district_input = QLineEdit()
        self._district_input.setPlaceholderText("예: 중산동, 화정동 …")
        form.addRow("거주지역:", self._district_input)

        layout.addLayout(form)

        # 버튼
        btn_row = QHBoxLayout()
        save_btn = QPushButton("저장")
        save_btn.clicked.connect(self._save)
        skip_btn = QPushButton("건너뛰기")
        skip_btn.clicked.connect(self.reject)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(skip_btn)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    def _selected_channel(self) -> str:
        for ch, rb in self._channel_radios.items():
            if rb.isChecked():
                return ch
        return CHANNELS[0]

    def _save(self) -> None:
        channel = self._selected_channel()
        detail = self._detail_input.text().strip() if channel == "기타" else None
        district = self._district_input.text().strip() or None

        lead = MemberLead(
            member_name=self.member_name,
            contract_date=self.contract_date,
            channel=channel,
            channel_detail=detail,
            residence_district=district,
            registration_type="신규",
            source="manual",
        )
        try:
            save_lead(lead)
            QMessageBox.information(self, "완료", "유입경로가 저장되었습니다.")
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "오류", str(exc))
