from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCharts import (
    QChart,
    QChartView,
    QDateTimeAxis,
    QLineSeries,
    QValueAxis,
)
from PySide6.QtCore import QDateTime, QMargins, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from src.services.locker_service import build_member_report_text
from src.services.snapshot_service import load_all_snapshots

_NAVY = "#1E2D3D"

_BTN_STYLE = f"""
    QPushButton {{
        background: {_NAVY}; color: white;
        border: none; border-radius: 8px;
        font-size: 13px; font-weight: 600;
        padding: 8px 20px;
    }}
    QPushButton:hover {{ background: #2D3F52; }}
    QPushButton:disabled {{ background: #9CA3AF; }}
"""

_RADIO_STYLE = """
    QRadioButton { font-size: 13px; color: #374151; spacing: 6px; }
    QRadioButton::indicator { width: 15px; height: 15px; }
"""

# 상태별 (배경색, 글자색, 표시명)
_CARD_META = [
    ("active_display", "#EFF6FF", "#1D4ED8", "활성"),
    ("expired",        "#FEF2F2", "#B91C1C", "만료"),
    ("holding",        "#FFFBEB", "#B45309", "홀딩"),
    ("scheduled",      "#F5F3FF", "#6D28D9", "예정"),
    ("unassigned",     "#F9FAFB", "#374151", "미등록"),
]

# 꺾은선 시리즈 (key, 표시명, 색상)
_SERIES_META = [
    ("active_display", "활성", "#3B82F6"),
    ("expired",        "만료", "#EF4444"),
    ("holding",        "홀딩", "#F59E0B"),
    ("unassigned",     "미등록", "#9CA3AF"),
]


def _snap_val(snap: dict, key: str) -> int:
    if key == "active_display":
        return snap.get("active", 0) + snap.get("imminent", 0)
    return snap.get(key, 0)


class TrendDialog(QDialog):
    def __init__(self, counts: dict[str, int], parent=None):
        super().__init__(parent)
        self.setWindowTitle("회원 현황 및 변화 추세")
        self.resize(740, 640)
        self.setStyleSheet("QDialog { background: #F3F4F6; font-family: 'Malgun Gothic', '맑은 고딕', sans-serif; }")

        self._counts = counts
        self._snapshots = load_all_snapshots()
        self._period = "day"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.setSpacing(14)

        lay.addWidget(self._build_header())
        lay.addWidget(self._build_cards())
        lay.addWidget(self._build_period_selector())

        self._chart_container = QWidget()
        self._chart_lay = QVBoxLayout(self._chart_container)
        self._chart_lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._chart_container, 1)

        lay.addWidget(self._build_buttons())

        self._refresh_chart()

    # ── 헤더 ──────────────────────────────────────────────────────────────
    def _build_header(self) -> QLabel:
        today = date.today()
        lbl = QLabel(f"리와인드 중산점 유효회원  ({today.year}년 {today.month}월 {today.day}일)")
        lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: #111827;")
        return lbl

    # ── 상태 카드 ─────────────────────────────────────────────────────────
    def _build_cards(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        c = self._counts
        values = {
            "active_display": c.get("active", 0) + c.get("imminent", 0),
            "expired":        c.get("expired", 0),
            "holding":        c.get("holding", 0),
            "scheduled":      c.get("scheduled", 0),
            "unassigned":     c.get("unassigned", 0),
        }
        total = sum(c.values())

        for key, bg, fg, label in _CARD_META:
            card = QWidget()
            card.setStyleSheet(f"background: {bg}; border-radius: 8px;")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(10, 10, 10, 10)
            cl.setSpacing(2)

            n_lbl = QLabel(str(values[key]))
            n_lbl.setAlignment(Qt.AlignCenter)
            n_lbl.setStyleSheet(f"font-size: 22px; font-weight: 700; color: {fg}; background: transparent;")

            t_lbl = QLabel(label)
            t_lbl.setAlignment(Qt.AlignCenter)
            t_lbl.setStyleSheet(f"font-size: 12px; color: {fg}; background: transparent;")

            cl.addWidget(n_lbl)
            cl.addWidget(t_lbl)
            lay.addWidget(card)

        # 총 카드
        total_card = QWidget()
        total_card.setStyleSheet(f"background: {_NAVY}; border-radius: 8px;")
        tl = QVBoxLayout(total_card)
        tl.setContentsMargins(10, 10, 10, 10)
        tl.setSpacing(2)
        tn = QLabel(str(total))
        tn.setAlignment(Qt.AlignCenter)
        tn.setStyleSheet("font-size: 22px; font-weight: 700; color: #FFFFFF; background: transparent;")
        tt = QLabel("총")
        tt.setAlignment(Qt.AlignCenter)
        tt.setStyleSheet("font-size: 12px; color: #93C5FD; background: transparent;")
        tl.addWidget(tn)
        tl.addWidget(tt)
        lay.addWidget(total_card)

        return w

    # ── 기간 선택 ─────────────────────────────────────────────────────────
    def _build_period_selector(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)

        self._btn_group = QButtonGroup(self)
        periods = [("전일 대비", "day"), ("전주 대비", "week"), ("전월 대비", "month")]
        for i, (label, key) in enumerate(periods):
            rb = QRadioButton(label)
            rb.setChecked(i == 0)
            rb.setStyleSheet(_RADIO_STYLE)
            rb.toggled.connect(lambda checked, k=key: checked and self._set_period(k))
            self._btn_group.addButton(rb, i)
            lay.addWidget(rb)

        lay.addStretch()
        return w

    def _set_period(self, period: str) -> None:
        self._period = period
        self._refresh_chart()

    # ── 차트 ──────────────────────────────────────────────────────────────
    def _refresh_chart(self) -> None:
        for i in reversed(range(self._chart_lay.count())):
            item = self._chart_lay.itemAt(i)
            if item and item.widget():
                item.widget().deleteLater()

        snaps = self._snapshots
        if not snaps:
            self._chart_lay.addWidget(self._placeholder(
                "데이터가 없습니다.\n회원 DB 업데이트 후 추세를 확인할 수 있습니다."
            ))
            return

        today = date.today()
        if self._period == "day":
            cutoff = today - timedelta(days=1)
            msg = "어제 데이터가 없습니다. 내일 다시 확인해주세요."
        elif self._period == "week":
            cutoff = today - timedelta(days=6)
            msg = "7일치 데이터가 부족합니다. 며칠 후 다시 확인해주세요."
        else:
            cutoff = today - timedelta(days=29)
            msg = "30일치 데이터가 부족합니다. 데이터가 쌓이면 확인할 수 있습니다."

        filtered = [s for s in snaps if date.fromisoformat(s["date"]) >= cutoff]

        if len(filtered) < 2:
            self._chart_lay.addWidget(self._placeholder(
                f"데이터가 더 쌓이면 추세를 확인할 수 있습니다.\n({msg})"
            ))
            return

        chart = self._build_chart(filtered)
        view = QChartView(chart)
        view.setRenderHint(QPainter.Antialiasing)
        view.setStyleSheet("background: white; border-radius: 10px;")
        self._chart_lay.addWidget(view)

    def _placeholder(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(
            "color: #9CA3AF; font-size: 13px; background: white;"
            " border-radius: 10px; padding: 40px;"
        )
        return lbl

    def _build_chart(self, snaps: list[dict]) -> QChart:
        chart = QChart()
        chart.legend().setVisible(True)
        chart.legend().setAlignment(Qt.AlignBottom)
        chart.setAnimationOptions(QChart.SeriesAnimations)
        chart.setMargins(QMargins(4, 4, 4, 4))
        chart.setBackgroundRoundness(8)

        all_series: list[QLineSeries] = []
        min_dt = max_dt = None
        min_val = float("inf")
        max_val = float("-inf")

        for key, name, color in _SERIES_META:
            series = QLineSeries()
            series.setName(name)
            pen = series.pen()
            pen.setColor(QColor(color))
            pen.setWidth(2)
            series.setPen(pen)

            for snap in snaps:
                d = date.fromisoformat(snap["date"])
                val = _snap_val(snap, key)
                ms = QDateTime(d.year, d.month, d.day, 12, 0, 0).toMSecsSinceEpoch()
                series.append(ms, val)

                if min_dt is None or d < min_dt:
                    min_dt = d
                if max_dt is None or d > max_dt:
                    max_dt = d
                min_val = min(min_val, val)
                max_val = max(max_val, val)

            chart.addSeries(series)
            all_series.append(series)

        # X축 (날짜)
        axis_x = QDateTimeAxis()
        axis_x.setFormat("M/d")
        axis_x.setLabelsFont(self.font())
        min_qdt = QDateTime(min_dt.year, min_dt.month, min_dt.day, 0, 0, 0)
        max_qdt = QDateTime(max_dt.year, max_dt.month, max_dt.day, 23, 59, 59)
        axis_x.setRange(min_qdt, max_qdt)
        chart.addAxis(axis_x, Qt.AlignBottom)

        # Y축 (회원 수)
        axis_y = QValueAxis()
        padding = max(10, (max_val - min_val) * 0.12)
        axis_y.setRange(max(0, min_val - padding), max_val + padding)
        axis_y.setLabelFormat("%d")
        axis_y.setTitleText("회원 수")
        axis_y.setLabelsFont(self.font())
        chart.addAxis(axis_y, Qt.AlignLeft)

        for s in all_series:
            s.attachAxis(axis_x)
            s.attachAxis(axis_y)

        return chart

    # ── 하단 버튼 ─────────────────────────────────────────────────────────
    def _build_buttons(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self._img_btn = QPushButton("📷  이미지 복사")
        self._img_btn.setStyleSheet(_BTN_STYLE)
        self._img_btn.clicked.connect(self._copy_image)

        self._txt_btn = QPushButton("📋  문구 복사")
        self._txt_btn.setStyleSheet(_BTN_STYLE)
        self._txt_btn.clicked.connect(self._copy_text)

        lay.addStretch()
        lay.addWidget(self._img_btn)
        lay.addWidget(self._txt_btn)
        return w

    def _copy_image(self) -> None:
        pixmap = self.grab()
        QApplication.clipboard().setPixmap(pixmap)
        self._flash_btn(self._img_btn, "✓  복사 완료!")

    def _copy_text(self) -> None:
        text = build_member_report_text(date.today(), self._counts)
        QApplication.clipboard().setText(text)
        self._flash_btn(self._txt_btn, "✓  복사 완료!")

    def _flash_btn(self, btn: QPushButton, msg: str) -> None:
        original = btn.text()
        btn.setText(msg)
        btn.setEnabled(False)
        QTimer.singleShot(1500, lambda: (btn.setText(original), btn.setEnabled(True)))
