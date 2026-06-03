from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from src.config.settings import get_phone_ip, get_sms_gateway_credentials, get_sms_test_phone
from src.services.holiday_notification_service import (
    get_active_foreign_phones,
    mark_handled,
)
from src.services.holiday_service import (
    HolidayInfo,
    build_sms_text,
    get_month_holidays,
)
from src.services.sms_gateway_service import send_bulk_sms


class HolidayNotificationDialog(QDialog):
    """
    매월 1일 공휴일 SMS 발송 확인 다이얼로그.
    holidays.KR()로 자동 감지한 공휴일 외에 임시공휴일을 수동 추가할 수 있다.
    """

    def __init__(self, year: int, month: int, parent=None) -> None:
        super().__init__(parent)
        self._year = year
        self._month = month
        self._extras: list[HolidayInfo] = []

        self.setWindowTitle(f"{month}월 공휴일 SMS 발송")
        self.setMinimumWidth(440)
        self._setup_ui()
        self._refresh_preview()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setSpacing(10)

        # 안내
        guide = QLabel(f"이번 달({self._month}월) 공휴일 문자를 활성 회원에게 발송하시겠습니까?")
        guide.setStyleSheet("font-size: 13px; font-weight: 600;")
        layout.addWidget(guide)

        # 자동 감지 공휴일
        layout.addWidget(QLabel("자동 감지된 공휴일:"))
        self._auto_list = QListWidget()
        self._auto_list.setFixedHeight(90)
        self._auto_list.setSelectionMode(QListWidget.NoSelection)
        auto_holidays = get_month_holidays(self._year, self._month)
        if auto_holidays:
            for h in auto_holidays:
                self._auto_list.addItem(f"{h.date.month}/{h.date.day} {h.name_ko} / {h.name_en}")
        else:
            item = QListWidgetItem("이번 달 공휴일 없음")
            item.setForeground(Qt.gray)
            self._auto_list.addItem(item)
        layout.addWidget(self._auto_list)

        # 임시공휴일 추가
        layout.addWidget(QLabel("추가 임시공휴일 (선거일, 갑작스러운 공휴일 등):"))

        self._extra_list = QListWidget()
        self._extra_list.setFixedHeight(70)
        layout.addWidget(self._extra_list)

        input_row = QHBoxLayout()
        self._date_input = QLineEdit()
        self._date_input.setPlaceholderText("날짜 (예: 6/3)")
        self._date_input.setFixedWidth(80)
        self._ko_input = QLineEdit()
        self._ko_input.setPlaceholderText("한국어 이름 (예: 지방선거일)")
        self._en_input = QLineEdit()
        self._en_input.setPlaceholderText("English name (e.g. Local Election Day)")
        add_btn = QPushButton("추가")
        add_btn.setFixedWidth(48)
        add_btn.clicked.connect(self._add_extra)
        del_btn = QPushButton("삭제")
        del_btn.setFixedWidth(48)
        del_btn.clicked.connect(self._del_extra)
        input_row.addWidget(self._date_input)
        input_row.addWidget(self._ko_input)
        input_row.addWidget(self._en_input)
        input_row.addWidget(add_btn)
        input_row.addWidget(del_btn)
        layout.addLayout(input_row)

        # 미리보기
        layout.addWidget(QLabel("발송 문구 미리보기:"))
        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setFixedHeight(180)
        self._preview.setStyleSheet(
            "font-size: 13px; font-family: 'Malgun Gothic', sans-serif;"
        )
        layout.addWidget(self._preview)

        # 버튼
        btn_row = QHBoxLayout()
        test_btn = QPushButton("🧪  테스트 발송")
        test_btn.setFixedHeight(38)
        test_btn.setStyleSheet(
            "QPushButton { background: #F3F4F6; color: #374151; border: none; border-radius: 8px; font-size: 13px; }"
            "QPushButton:hover { background: #E5E7EB; }"
        )
        test_btn.clicked.connect(self._test_send)
        send_btn = QPushButton("📨  발송하기")
        send_btn.setFixedHeight(38)
        send_btn.setStyleSheet(
            "QPushButton { background: #3B82F6; color: white; border: none; border-radius: 8px; font-size: 13px; font-weight: 600; }"
            "QPushButton:hover { background: #2563EB; }"
        )
        send_btn.clicked.connect(self._send)
        skip_btn = QPushButton("이번 달 건너뛰기")
        skip_btn.setFixedHeight(38)
        skip_btn.setStyleSheet(
            "QPushButton { background: #F3F4F6; color: #6B7280; border: none; border-radius: 8px; font-size: 13px; }"
            "QPushButton:hover { background: #E5E7EB; }"
        )
        skip_btn.clicked.connect(self._skip)
        btn_row.addWidget(test_btn)
        btn_row.addWidget(send_btn)
        btn_row.addWidget(skip_btn)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    def _add_extra(self) -> None:
        date_str = self._date_input.text().strip()
        name_ko = self._ko_input.text().strip()
        name_en = self._en_input.text().strip()

        if not date_str or not name_ko or not name_en:
            QMessageBox.warning(self, "입력 오류", "날짜, 한국어 이름, 영어 이름을 모두 입력해주세요.")
            return

        try:
            parts = date_str.replace("-", "/").split("/")
            if len(parts) == 2:
                m, d = int(parts[0]), int(parts[1])
            else:
                raise ValueError
            h_date = date(self._year, m, d)
        except (ValueError, TypeError):
            QMessageBox.warning(self, "입력 오류", "날짜 형식이 올바르지 않습니다. 예: 6/3")
            return

        holiday = HolidayInfo(date=h_date, name_ko=name_ko, name_en=name_en, is_extra=True)
        self._extras.append(holiday)
        self._extra_list.addItem(f"{m}/{d} {name_ko} / {name_en}")
        self._date_input.clear()
        self._ko_input.clear()
        self._en_input.clear()
        self._refresh_preview()

    def _del_extra(self) -> None:
        row = self._extra_list.currentRow()
        if row >= 0:
            self._extra_list.takeItem(row)
            self._extras.pop(row)
            self._refresh_preview()

    def _refresh_preview(self) -> None:
        holidays = get_month_holidays(self._year, self._month, self._extras)
        text = build_sms_text(holidays)
        self._preview.setPlainText(text if text else "(이번 달 공휴일 없음 — 발송 불필요)")

    def _test_send(self) -> None:
        """설정에 저장된 테스트 번호 1개로만 발송해 문구를 확인한다."""
        test_phone = get_sms_test_phone()
        if not test_phone:
            QMessageBox.warning(
                self, "테스트 번호 없음",
                "설정(⚙)에서 'SMS 테스트 번호'를 먼저 등록해주세요."
            )
            return

        phone_ip = get_phone_ip()
        if not phone_ip:
            QMessageBox.warning(self, "설정 오류", "설정에서 센터폰 IP를 먼저 등록해주세요.")
            return

        holidays = get_month_holidays(self._year, self._month, self._extras)
        sms_text = build_sms_text(holidays) or "(이번 달 공휴일 없음)"
        port, username, password = get_sms_gateway_credentials()

        try:
            send_bulk_sms(phone_ip, [test_phone], sms_text, port, username, password)
            QMessageBox.information(self, "완료", f"{test_phone}으로 테스트 문자를 발송했습니다.")
        except Exception as exc:
            QMessageBox.critical(self, "발송 실패", str(exc))

    def _send(self) -> None:
        holidays = get_month_holidays(self._year, self._month, self._extras)
        if not holidays:
            reply = QMessageBox.question(
                self, "공휴일 없음",
                "이번 달 공휴일이 없습니다. 그래도 발송하시겠습니까?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        phone_ip = get_phone_ip()
        if not phone_ip:
            QMessageBox.warning(self, "설정 오류", "설정에서 센터폰 IP를 먼저 등록해주세요.")
            return

        phones = get_active_foreign_phones()
        if not phones:
            QMessageBox.warning(
                self, "외국인 회원 없음",
                "등록된 활성 외국인 회원이 없습니다.\n'외국인 회원 관리'에서 먼저 등록해주세요."
            )
            return

        sms_text = build_sms_text(holidays)
        port, username, password = get_sms_gateway_credentials()

        reply = QMessageBox.question(
            self,
            "발송 확인",
            f"외국인 회원 {len(phones)}명에게 문자를 발송합니다.\n계속하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            send_bulk_sms(phone_ip, phones, sms_text, port, username, password)
            mark_handled(self._year, self._month)
            QMessageBox.information(
                self, "완료",
                f"{len(phones)}명에게 공휴일 안내 문자를 발송했습니다."
            )
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "발송 실패", str(exc))

    def _skip(self) -> None:
        mark_handled(self._year, self._month)
        self.reject()
