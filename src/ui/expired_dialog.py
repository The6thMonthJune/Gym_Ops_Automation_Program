from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.services.locker_service import LockerRecord, get_expired_by_category, load_records

_NAVY = "#1E2D3D"


def _days_since(expiry: date | None) -> str:
    if not expiry:
        return "-"
    delta = (date.today() - expiry).days
    return f"{delta}일 전 만료"


def _membership_label(rec: LockerRecord) -> str:
    return rec.membership_type if rec.membership_type else "-"


def _format_phone(phone: str | None) -> str:
    if not phone:
        return "-"
    d = phone
    if len(d) == 11:
        return f"{d[:3]}-{d[3:7]}-{d[7:]}"
    if len(d) == 10:
        return f"{d[:3]}-{d[3:6]}-{d[6:]}"
    return d


class _MemberRow(QWidget):
    def __init__(self, rec: LockerRecord, shade: bool = False, parent=None):
        super().__init__(parent)
        bg = "#F9FAFB" if shade else "#FFFFFF"
        self.setStyleSheet(f"background: {bg};")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(0)

        def _cell(text: str, width: int, align=Qt.AlignLeft) -> QLabel:
            lbl = QLabel(text)
            lbl.setFixedWidth(width)
            lbl.setAlignment(align | Qt.AlignVCenter)
            lbl.setStyleSheet("background: transparent; font-size: 12px; color: #111827;")
            return lbl

        lay.addWidget(_cell(rec.member_name, 100))
        lay.addWidget(_cell(f"{rec.locker_number}번", 60, Qt.AlignCenter))
        lay.addWidget(_cell(rec.locker_room or "-", 100))
        lay.addWidget(_cell(_days_since(rec.expiry_date), 100))
        lay.addWidget(_cell(_membership_label(rec), 140))
        lay.addWidget(_cell(_format_phone(rec.phone_number), 130))


class _SectionWidget(QWidget):
    def __init__(self, title: str, records: list[LockerRecord], color: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 12)
        lay.setSpacing(0)

        # 헤더 바
        header_bar = QWidget()
        header_bar.setFixedHeight(36)
        header_bar.setStyleSheet(f"background: {color}; border-radius: 6px;")
        h_lay = QHBoxLayout(header_bar)
        h_lay.setContentsMargins(12, 0, 12, 0)

        title_lbl = QLabel(f"{title}  ({len(records)}명)")
        title_lbl.setStyleSheet(
            "color: white; font-size: 13px; font-weight: bold; background: transparent;"
        )
        copy_btn = QPushButton("📋 복사")
        copy_btn.setFixedSize(64, 24)
        copy_btn.setStyleSheet("""
            QPushButton { background: rgba(255,255,255,0.2); color: white;
                          border: none; border-radius: 4px; font-size: 11px; }
            QPushButton:hover { background: rgba(255,255,255,0.35); }
        """)
        copy_btn.clicked.connect(lambda: self._copy(records))
        h_lay.addWidget(title_lbl)
        h_lay.addStretch()
        h_lay.addWidget(copy_btn)
        lay.addWidget(header_bar)

        if not records:
            empty = QLabel("해당 없음")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color: #9CA3AF; font-size: 12px; padding: 12px;")
            lay.addWidget(empty)
            return

        # 컬럼 헤더
        col_header = QWidget()
        col_header.setStyleSheet("background: #F3F4F6;")
        ch_lay = QHBoxLayout(col_header)
        ch_lay.setContentsMargins(12, 4, 12, 4)
        ch_lay.setSpacing(0)
        for text, width in [
            ("이름", 100), ("락카번호", 60), ("구역", 100),
            ("경과", 100), ("보유 회원권", 140), ("휴대폰", 130),
        ]:
            lbl = QLabel(text)
            lbl.setFixedWidth(width)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(
                "background: transparent; font-size: 11px; font-weight: bold; color: #6B7280;"
            )
            ch_lay.addWidget(lbl)
        lay.addWidget(col_header)

        # 회원 행
        for i, rec in enumerate(records):
            lay.addWidget(_MemberRow(rec, shade=(i % 2 == 1)))

    def _copy(self, records: list[LockerRecord]) -> None:
        if not records:
            return
        lines = ["이름\t락카번호\t구역\t경과\t보유회원권\t휴대폰"]
        for r in records:
            lines.append(
                f"{r.member_name}\t{r.locker_number}번\t{r.locker_room or '-'}\t"
                f"{_days_since(r.expiry_date)}\t"
                f"{_membership_label(r)}\t{_format_phone(r.phone_number)}"
            )
        QApplication.clipboard().setText("\n".join(lines))
        QMessageBox.information(self.window(), "완료", "클립보드에 복사되었습니다.")


class ExpiredLockerDialog(QDialog):
    """락카 만료자 명단 다이얼로그."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("락카 만료자 명단")
        self.setMinimumSize(720, 600)
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # 타이틀
        title = QLabel("락카 만료자 명단")
        title.setStyleSheet(
            f"color: {_NAVY}; font-size: 16px; font-weight: bold;"
        )
        root.addWidget(title)

        records = load_records()
        locker_only, both_expired = get_expired_by_category(records)

        # 스크롤 영역
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        container = QWidget()
        container.setStyleSheet("background: #FFFFFF;")
        c_lay = QVBoxLayout(container)
        c_lay.setContentsMargins(0, 0, 0, 0)
        c_lay.setSpacing(0)

        c_lay.addWidget(_SectionWidget(
            "🔑 락카 만료 · 회원권 진행중",
            locker_only,
            "#2563EB",
        ))
        c_lay.addWidget(_SectionWidget(
            "⚠️ 락카 · 회원권 모두 만료",
            both_expired,
            "#DC2626",
        ))
        c_lay.addStretch()

        scroll.setWidget(container)
        root.addWidget(scroll)

        # 하단 안내
        guide = QLabel(
            f"총 만료자: {len(locker_only) + len(both_expired)}명  "
            f"(회원권 진행중 {len(locker_only)}명 · 모두 만료 {len(both_expired)}명)"
        )
        guide.setStyleSheet("color: #6B7280; font-size: 11px;")
        root.addWidget(guide)

        close_btn = QPushButton("닫기")
        close_btn.setFixedHeight(36)
        close_btn.setStyleSheet("""
            QPushButton { background: #1E2D3D; color: white; border: none;
                          border-radius: 8px; font-size: 13px; }
            QPushButton:hover { background: #2A3F56; }
        """)
        close_btn.clicked.connect(self.accept)
        root.addWidget(close_btn)
