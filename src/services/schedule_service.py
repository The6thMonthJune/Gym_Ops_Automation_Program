from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import QObject, QTimer, Signal

import holidays as holidays_lib

# 평일 전송 시각 (시, 분)
WEEKDAY_SEND_TIME = (23, 30)
# 주말·공휴일 전송 시각 (시, 분)
HOLIDAY_SEND_TIME = (19, 30)


def _is_holiday(d: date) -> bool:
    """주말 또는 한국 공휴일이면 True를 반환한다."""
    if d.weekday() >= 5:  # 토(5), 일(6)
        return True
    try:
        kr = holidays_lib.KR(years=d.year)
        return d in kr
    except Exception:
        return False  # holidays 라이브러리 오류 시 평일로 처리


def get_send_time(d: date) -> tuple[int, int]:
    """날짜에 따른 전송 시각 (시, 분)을 반환한다."""
    return HOLIDAY_SEND_TIME if _is_holiday(d) else WEEKDAY_SEND_TIME


class HolidayNotificationScheduler(QObject):
    """매월 1일 오전 10시에 공휴일 SMS 발송 다이얼로그 표시를 트리거하는 스케줄러."""

    triggered = Signal()  # (year, month) 대신 signal만 발생, 수신측이 date.today() 참조

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._last_triggered_month: str | None = None

        self._timer = QTimer(self)
        self._timer.setInterval(30_000)
        self._timer.timeout.connect(self._check)

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _check(self) -> None:
        from src.services.holiday_notification_service import is_handled

        now = datetime.now()
        today = now.date()

        if today.day != 1:
            return

        month_key = today.strftime("%Y-%m")
        if self._last_triggered_month == month_key:
            return
        if is_handled(today.year, today.month):
            self._last_triggered_month = month_key
            return

        # 매월 1일 오전 10시 이후 트리거
        if now.hour >= 10:
            self._last_triggered_month = month_key
            self.triggered.emit()


class SalesReportScheduler(QObject):
    """매일 지정 시각에 매출 보고 자동 전송을 트리거하는 스케줄러."""

    send_triggered = Signal()  # 전송 시각 도달 시 발생

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._last_sent_date: date | None = None

        self._timer = QTimer(self)
        self._timer.setInterval(30_000)  # 30초마다 체크
        self._timer.timeout.connect(self._check)

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _check(self) -> None:
        now = datetime.now()
        today = now.date()

        if self._last_sent_date == today:
            return

        h, m = get_send_time(today)
        if now.hour == h and now.minute == m:
            self._last_sent_date = today
            self.send_triggered.emit()
