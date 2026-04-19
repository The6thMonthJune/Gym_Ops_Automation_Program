from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import Qt, QMarginsF
from PySide6.QtGui import QPageLayout, QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.services.brogej_service import LockerRecord, parse_xls
from src.services.locker_service import (
    SECTIONS,
    LockerCell,
    build_grid,
    get_locker_json_path,
    get_unassigned,
    load_records,
    save_records,
)
from src.config.settings import load_settings, save_settings

_KEY_LAST_XLS_DIR = "last_xls_dir"

_NAVY   = "#1E2D3D"
_BLUE   = "#4A6FA5"
_WHITE  = "#FFFFFF"
_BG     = "#F4F5F7"
_BORDER = "#D1D5DB"

_COLORS: dict[str, dict[str, str]] = {
    "active":    {"bg": "#DCFCE7", "border": "#BBF7D0", "num": "#166534", "name": "#14532D", "sub": "#16A34A"},
    "imminent":  {"bg": "#FEE2E2", "border": "#FECACA", "num": "#7F1D1D", "name": "#991B1B", "sub": "#DC2626"},
    "expired":   {"bg": "#F9FAFB", "border": "#D1D5DB", "num": "#9CA3AF", "name": "#6B7280", "sub": "#9CA3AF"},
    "empty":     {"bg": "#F3F4F6", "border": "#E5E7EB", "num": "#D1D5DB", "name": "#9CA3AF", "sub": "#D1D5DB"},
    "unassigned":{"bg": "#FEF9C3", "border": "#FDE047", "num": "#713F12", "name": "#854D0E", "sub": "#A16207"},
}

_SECTION_COLORS = ["#1E2D3D", "#4A6FA5", "#374151"]


class _CellWidget(QFrame):
    def __init__(self, number: int, cell: LockerCell | None, parent=None):
        super().__init__(parent)
        state = cell.state if cell else "empty"
        c = _COLORS.get(state, _COLORS["empty"])

        self.setFixedSize(46, 66)
        self.setStyleSheet(f"""
            QFrame {{
                background: {c['bg']};
                border: 1px solid {c['border']};
                border-radius: 3px;
            }}
            QLabel {{ background: transparent; border: none; }}
        """)

        vlay = QVBoxLayout(self)
        vlay.setContentsMargins(1, 2, 1, 2)
        vlay.setSpacing(0)

        num_lbl = QLabel(str(number))
        num_lbl.setAlignment(Qt.AlignCenter)
        num_lbl.setStyleSheet(
            f"font-size: 8px; font-weight: bold; color: {c['num']};"
        )
        vlay.addWidget(num_lbl)

        vlay.addStretch()

        name_text = cell.member_name if cell and cell.member_name else ""
        name_lbl = QLabel(name_text)
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setWordWrap(True)
        name_lbl.setStyleSheet(
            f"font-size: 8px; font-weight: bold; color: {c['name']};"
        )
        vlay.addWidget(name_lbl)

        vlay.addStretch()

        if cell:
            if cell.days_remaining is not None:
                sub_text = f"{cell.days_remaining}일" if cell.days_remaining >= 0 else "만료"
            elif cell.state == "expired":
                sub_text = "만료"
            else:
                sub_text = ""
        else:
            sub_text = "빈 칸"

        sub_lbl = QLabel(sub_text)
        sub_lbl.setAlignment(Qt.AlignCenter)
        sub_lbl.setStyleSheet(f"font-size: 8px; color: {c['sub']};")
        vlay.addWidget(sub_lbl)


class _SectionWidget(QWidget):
    def __init__(self, section: dict, grid: dict[int, LockerCell], color: str, parent=None):
        super().__init__(parent)
        vlay = QVBoxLayout(self)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(6)

        # 헤더
        header = QFrame()
        header.setFixedHeight(28)
        header.setStyleSheet(f"background: {color}; border-radius: 4px;")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(10, 0, 10, 0)
        title = QLabel(
            f"🔒  {section['name']}  "
            f"({section['start']}~{section['end']}, "
            f"{section['cols']}×{section['rows']})"
        )
        title.setStyleSheet(
            "color: white; font-size: 11px; font-weight: bold; background: transparent;"
        )
        h_lay.addWidget(title)
        vlay.addWidget(header)

        # 그리드 (열-우선 배치)
        grid_widget = QWidget()
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(2)

        rows  = section["rows"]
        start = section["start"]
        end   = section["end"]

        for n in range(start, end + 1):
            rel = n - start
            col = rel // rows
            row = rel % rows
            grid_layout.addWidget(_CellWidget(n, grid.get(n)), row, col)

        vlay.addWidget(grid_widget)


class LockerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("락카 관리")
        self.setMinimumWidth(1180)
        self.setStyleSheet(f"""
            QDialog {{ background: {_BG}; font-family: "Malgun Gothic", sans-serif; }}
            QPushButton {{ outline: none; }}
        """)

        self._records: list[LockerRecord] = []
        self._xls_path: str = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 타이틀바
        title_bar = QFrame()
        title_bar.setFixedHeight(48)
        title_bar.setStyleSheet(f"background: {_NAVY};")
        tb_lay = QHBoxLayout(title_bar)
        tb_lay.setContentsMargins(20, 0, 20, 0)
        tb_lbl = QLabel("🔐  락카 관리")
        tb_lbl.setStyleSheet(
            "color: white; font-size: 13px; font-weight: bold; background: transparent;"
        )
        tb_lay.addWidget(tb_lbl)
        root.addWidget(title_bar)

        # 본문 스크롤
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        body = QWidget()
        body.setStyleSheet(f"background: {_BG};")
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(16, 16, 16, 16)
        body_lay.setSpacing(12)

        body_lay.addWidget(self._build_import_card())
        body_lay.addWidget(self._build_legend())

        # 그리드 컨테이너
        self._grid_container = QWidget()
        self._grid_container.setStyleSheet("background: transparent;")
        gc_lay = QVBoxLayout(self._grid_container)
        gc_lay.setContentsMargins(0, 0, 0, 0)
        gc_lay.setSpacing(16)
        body_lay.addWidget(self._grid_container)

        # 미배정 카드
        self._unassigned_card = self._build_unassigned_card()
        body_lay.addWidget(self._unassigned_card)

        body_lay.addWidget(self._build_bottom_bar())
        body_lay.addStretch()

        scroll.setWidget(body)
        root.addWidget(scroll)

        self._refresh_grid()

    # ── 카드 빌더 ─────────────────────────────────────────────────

    def _build_import_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {_WHITE};
                border: 1px solid #E5E7EB;
                border-radius: 8px;
            }}
        """)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(8)

        lbl = QLabel("브로제이 엑셀 데이터 가져오기")
        lbl.setStyleSheet(
            "color: #374151; font-size: 11px; font-weight: bold; background: transparent; border: none;"
        )
        lay.addWidget(lbl)

        row = QHBoxLayout()
        row.setSpacing(8)

        self._xls_label = QLabel("가져올 .xls 파일을 선택하세요")
        self._xls_label.setStyleSheet(f"""
            color: #9CA3AF; font-size: 11px;
            background: {_BG}; border: 1px solid {_BORDER};
            border-radius: 4px; padding: 6px 10px;
        """)
        row.addWidget(self._xls_label, 1)

        browse_btn = QPushButton("파일 선택")
        browse_btn.setFixedSize(80, 32)
        browse_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_BLUE}; color: white; border: none;
                border-radius: 4px; font-size: 11px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #3B5998; }}
        """)
        browse_btn.clicked.connect(self._browse_xls)
        row.addWidget(browse_btn)

        self._import_btn = QPushButton("가져오기")
        self._import_btn.setFixedSize(80, 32)
        self._import_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_NAVY}; color: white; border: none;
                border-radius: 4px; font-size: 11px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #2A3F56; }}
        """)
        self._import_btn.clicked.connect(self._import_xls)
        row.addWidget(self._import_btn)

        lay.addLayout(row)
        return card

    def _build_legend(self) -> QWidget:
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(widget)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)

        lbl = QLabel("상태:")
        lbl.setStyleSheet("color: #374151; font-size: 11px; font-weight: bold; background: transparent;")
        lay.addWidget(lbl)

        for state, text in [
            ("active",     "활성"),
            ("imminent",   "만료 임박"),
            ("expired",    "만료"),
            ("empty",      "빈 칸"),
            ("unassigned", "미배정"),
        ]:
            c = _COLORS[state]
            dot = QFrame()
            dot.setFixedSize(12, 12)
            dot.setStyleSheet(
                f"QFrame {{ background: {c['bg']}; border: 1px solid {c['border']}; border-radius: 2px; }}"
            )
            text_lbl = QLabel(text)
            text_lbl.setStyleSheet("color: #374151; font-size: 11px; background: transparent;")

            item = QWidget()
            item.setStyleSheet("background: transparent;")
            item_lay = QHBoxLayout(item)
            item_lay.setContentsMargins(0, 0, 0, 0)
            item_lay.setSpacing(4)
            item_lay.addWidget(dot)
            item_lay.addWidget(text_lbl)
            lay.addWidget(item)

        lay.addStretch()

        self._sync_label = QLabel("")
        self._sync_label.setStyleSheet("color: #9CA3AF; font-size: 10px; background: transparent;")
        lay.addWidget(self._sync_label)

        return widget

    def _build_unassigned_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {_WHITE};
                border: 1px solid #FDE047;
                border-radius: 8px;
            }}
        """)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(4)

        header = QLabel("⚠️  미배정 회원 (결제 완료, 락카 미배정)")
        header.setStyleSheet(
            "color: #854D0E; font-size: 11px; font-weight: bold; background: transparent; border: none;"
        )
        lay.addWidget(header)

        self._unassigned_text = QLabel("")
        self._unassigned_text.setWordWrap(True)
        self._unassigned_text.setStyleSheet(
            "color: #713F12; font-size: 11px; background: transparent; border: none;"
        )
        lay.addWidget(self._unassigned_text)

        card.setVisible(False)
        return card

    def _build_bottom_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(52)
        bar.setStyleSheet(f"background: {_WHITE}; border-radius: 8px;")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(8)

        lay.addStretch()

        refresh_btn = QPushButton("↺  새로고침")
        refresh_btn.setFixedSize(100, 38)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_BG}; color: #374151;
                border: 1px solid {_BORDER}; border-radius: 6px; font-size: 12px;
            }}
            QPushButton:hover {{ background: #E9EBF0; }}
        """)
        refresh_btn.clicked.connect(self._refresh_grid)
        lay.addWidget(refresh_btn)

        print_btn = QPushButton("🖨️  인쇄")
        print_btn.setFixedSize(110, 38)
        print_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_BG}; color: #374151;
                border: 1px solid {_BORDER}; border-radius: 6px;
                font-size: 12px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #E9EBF0; }}
        """)
        print_btn.clicked.connect(self._print_grid)
        lay.addWidget(print_btn)

        lay.addStretch()
        return bar

    # ── 슬롯 ──────────────────────────────────────────────────────

    def _browse_xls(self) -> None:
        s = load_settings()
        start_dir = s.get(_KEY_LAST_XLS_DIR, "")
        path, _ = QFileDialog.getOpenFileName(
            self, "브로제이 엑셀 파일 선택", start_dir, "Excel Files (*.xls *.xlsx)"
        )
        if not path:
            return
        self._xls_path = path
        self._xls_label.setText(Path(path).name)
        self._xls_label.setStyleSheet(f"""
            color: {_NAVY}; font-size: 11px;
            background: #F0F5FF; border: 1px solid {_BLUE};
            border-radius: 4px; padding: 6px 10px;
        """)
        s[_KEY_LAST_XLS_DIR] = str(Path(path).parent)
        save_settings(s)

    def _import_xls(self) -> None:
        if not self._xls_path:
            QMessageBox.warning(self, "경고", "파일을 먼저 선택해주세요.")
            return
        if not Path(self._xls_path).exists():
            QMessageBox.warning(self, "오류", "선택한 파일이 존재하지 않습니다.")
            return

        self._import_btn.setEnabled(False)
        self._import_btn.setText("처리 중...")
        try:
            records = parse_xls(self._xls_path, delete_after=False)  # 디버그 중 삭제 비활성화
            with_num   = [r for r in records if r.locker_number > 0]
            unassigned = [r for r in records if r.locker_number <= 0 and r.has_key]
            QMessageBox.information(
                self, "파싱 결과 (디버그)",
                f"총 파싱: {len(records)}명\n"
                f"락커번호 있음: {len(with_num)}명\n"
                f"미배정(결제만): {len(unassigned)}명\n\n"
                f"락커번호 샘플: {[r.locker_number for r in records[:5]]}\n"
                f"구역 샘플: {[r.locker_room for r in records[:5]]}"
            )
            save_records(records)
            self._xls_path = ""
            self._xls_label.setText(f"가져오기 완료 — {len(records)}명")
            self._xls_label.setStyleSheet(f"""
                color: #166534; font-size: 11px;
                background: #DCFCE7; border: 1px solid #BBF7D0;
                border-radius: 4px; padding: 6px 10px;
            """)
            self._refresh_grid()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일 파싱 실패:\n{e}")
        finally:
            self._import_btn.setEnabled(True)
            self._import_btn.setText("가져오기")

    def _refresh_grid(self) -> None:
        self._records = load_records()
        grid = build_grid(self._records)
        unassigned = get_unassigned(self._records)

        # 기존 섹션 위젯 교체
        lay = self._grid_container.layout()
        while lay.count():
            item = lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, section in enumerate(SECTIONS):
            color = _SECTION_COLORS[i % len(_SECTION_COLORS)]
            lay.addWidget(_SectionWidget(section, grid, color))

        # 미배정 카드
        if unassigned:
            self._unassigned_text.setText(
                ", ".join(r.member_name for r in unassigned)
            )
            self._unassigned_card.setVisible(True)
        else:
            self._unassigned_card.setVisible(False)

        # 마지막 동기화 시각
        json_path = get_locker_json_path()
        if json_path.exists():
            dt = datetime.fromtimestamp(json_path.stat().st_mtime)
            self._sync_label.setText(f"마지막 동기화: {dt.strftime('%Y.%m.%d %H:%M')}")

    def _print_grid(self) -> None:
        html = self._build_print_html()
        doc = QTextDocument()
        doc.setHtml(html)

        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageLayout(QPageLayout(
            QPageSize(QPageSize.A4),
            QPageLayout.Landscape,
            QMarginsF(10, 10, 10, 10),
        ))

        dlg = QPrintDialog(printer, self)
        if dlg.exec() == QPrintDialog.Accepted:
            doc.print_(printer)

    # ── HTML 인쇄 생성 ────────────────────────────────────────────

    def _build_print_html(self) -> str:
        grid = build_grid(self._records)

        cell_styles = {
            state: f"background:{c['bg']};border:1px solid {c['border']};color:{c['name']};"
            for state, c in _COLORS.items()
        }

        html = """<html><head><style>
body { font-family: 'Malgun Gothic', sans-serif; font-size: 8pt; }
table { border-collapse: collapse; margin: 4px 0; }
.sec-title { font-size: 10pt; font-weight: bold; margin: 8px 0 4px 0; }
td { width: 44px; height: 56px; text-align: center; vertical-align: middle;
     font-size: 7pt; border-radius: 2px; padding: 1px; }
</style></head><body>"""

        html += f"<p style='font-size:9pt;font-weight:bold;'>락카 현황 — {date.today().strftime('%Y년 %m월 %d일')}</p>"

        for section in SECTIONS:
            rows  = section["rows"]
            start = section["start"]
            end   = section["end"]

            html += f"<div class='sec-title'>{section['name']} ({start}~{end})</div><table>"
            for r in range(rows):
                html += "<tr>"
                for col in range(section["cols"]):
                    n = start + col * rows + r
                    if n > end:
                        html += "<td></td>"
                        continue
                    cell = grid.get(n)
                    state = cell.state if cell else "empty"
                    style = cell_styles[state]
                    name  = cell.member_name if cell else ""
                    if cell and cell.days_remaining is not None:
                        sub = f"{cell.days_remaining}일" if cell.days_remaining >= 0 else "만료"
                    elif cell and cell.state == "expired":
                        sub = "만료"
                    elif not cell:
                        sub = "빈 칸"
                    else:
                        sub = ""
                    html += (
                        f'<td style="{style}">'
                        f'<div style="font-size:6pt;font-weight:bold;">{n}</div>'
                        f'<div style="font-size:7pt;font-weight:bold;">{name}</div>'
                        f'<div style="font-size:6pt;">{sub}</div>'
                        f'</td>'
                    )
                html += "</tr>"
            html += "</table>"

        html += "</body></html>"
        return html
