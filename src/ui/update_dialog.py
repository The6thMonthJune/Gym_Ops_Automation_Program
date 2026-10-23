"""자동 업데이트 UI. 확인·다운로드는 모두 백그라운드 스레드에서 돌린다."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from src.config.constants import APP_VERSION
from src.config.settings import get_update_skip_version, set_update_skip_version
from src.services import update_service
from src.services.update_service import ReleaseInfo

_BTN = """
QPushButton {{
    background: {bg}; color: white; font-size: 13px; font-weight: 700;
    border: none; border-radius: 8px; padding: 8px 14px;
}}
QPushButton:hover {{ background: {hv}; }}
QPushButton:disabled {{ background: #9CA3AF; }}
"""
_GREEN = _BTN.format(bg="#16A34A", hv="#15803D")
_GRAY = (
    "QPushButton { background: #F3F4F6; color: #374151; border: none;"
    " border-radius: 8px; padding: 8px 14px; }"
    "QPushButton:hover { background: #E5E7EB; }"
)


class _CheckThread(QThread):
    """새 버전 확인. 실패 사유를 함께 돌려줘야 '최신 버전'과 구분할 수 있다."""

    done = Signal(object, str)  # (최신 릴리스 | None, 실패 사유)

    def run(self) -> None:
        try:
            self.done.emit(update_service.fetch_latest_release(), "")
        except Exception as exc:
            self.done.emit(None, f"{type(exc).__name__}: {exc}")


class _DownloadThread(QThread):
    progress = Signal(int, int)  # 받은 바이트, 전체 바이트
    done = Signal(object)        # Path
    failed = Signal(str)

    def __init__(self, release: ReleaseInfo, parent=None) -> None:
        super().__init__(parent)
        self._release = release

    def run(self) -> None:
        try:
            path = update_service.download_release(
                self._release, progress=lambda got, total: self.progress.emit(got, total)
            )
        except Exception as exc:
            self.failed.emit(str(exc) or exc.__class__.__name__)
            return
        self.done.emit(path)


class UpdateDialog(QDialog):
    """새 버전 안내 → 다운로드 → EXE 교체 → 재시작."""

    def __init__(self, release: ReleaseInfo, parent=None) -> None:
        super().__init__(parent)
        self._release = release
        self._thread: _DownloadThread | None = None
        self.setWindowTitle("업데이트")
        self.setMinimumWidth(420)
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout()
        root.setSpacing(12)

        headline = QLabel(f"새 버전 v{self._release.version} 이 나왔습니다.")
        headline.setStyleSheet("font-size: 15px; font-weight: 700;")
        root.addWidget(headline)

        root.addWidget(QLabel(f"현재 버전: v{APP_VERSION}"))

        if self._release.notes:
            notes = QTextEdit()
            notes.setReadOnly(True)
            notes.setPlainText(self._release.notes)
            notes.setFixedHeight(120)
            root.addWidget(notes)

        self._status = QLabel(f"내려받을 용량: {self._release.size / 1_048_576:.0f} MB")
        self._status.setStyleSheet("color: #6B7280; font-size: 12px;")
        root.addWidget(self._status)

        self._bar = QProgressBar()
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(8)
        self._bar.hide()
        root.addWidget(self._bar)

        row = QHBoxLayout()
        self._skip_btn = QPushButton("이 버전 건너뛰기")
        self._skip_btn.setStyleSheet(_GRAY)
        self._skip_btn.clicked.connect(self._skip)

        self._later_btn = QPushButton("나중에")
        self._later_btn.setStyleSheet(_GRAY)
        self._later_btn.clicked.connect(self.reject)

        self._install_btn = QPushButton("지금 업데이트")
        self._install_btn.setStyleSheet(_GREEN)
        self._install_btn.clicked.connect(self._start_download)

        row.addWidget(self._skip_btn)
        row.addStretch()
        row.addWidget(self._later_btn)
        row.addWidget(self._install_btn)
        root.addLayout(row)

        self.setLayout(root)

    # ── 다운로드 ──────────────────────────────────────────────────

    def _start_download(self) -> None:
        self._install_btn.setEnabled(False)
        self._skip_btn.setEnabled(False)
        self._later_btn.setEnabled(False)
        self._bar.show()
        self._status.setText("내려받는 중…")

        self._thread = _DownloadThread(self._release, self)
        self._thread.progress.connect(self._on_progress)
        self._thread.done.connect(self._on_downloaded)
        self._thread.failed.connect(self._on_failed)
        self._thread.start()

    def _on_progress(self, got: int, total: int) -> None:
        if total:
            self._bar.setMaximum(total)
            self._bar.setValue(got)
        self._status.setText(f"내려받는 중… {got / 1_048_576:.0f} / {total / 1_048_576:.0f} MB")

    def _on_failed(self, message: str) -> None:
        self._bar.hide()
        self._restore_buttons()
        self._offer_manual(f"업데이트에 실패했습니다.\n\n{message}")

    def _on_downloaded(self, path: Path) -> None:
        self._status.setText("설치하는 중…")
        try:
            exe = update_service.apply_update(path)
        except Exception as exc:
            self._bar.hide()
            self._restore_buttons()
            self._offer_manual(
                "새 버전을 설치하지 못했습니다.\n"
                "백신이 막았거나 프로그램 폴더에 쓰기 권한이 없을 수 있습니다.\n\n"
                f"{exc}"
            )
            return

        QMessageBox.information(
            self, "업데이트 완료",
            f"v{self._release.version} 설치가 끝났습니다.\n프로그램을 다시 시작합니다."
        )
        update_service.restart(exe)
        self.accept()
        QApplication.quit()

    def _restore_buttons(self) -> None:
        for btn in (self._install_btn, self._skip_btn, self._later_btn):
            btn.setEnabled(True)

    def _offer_manual(self, message: str) -> None:
        """자동 설치가 막히면 릴리스 페이지를 열어 직접 받게 안내한다."""
        box = QMessageBox(QMessageBox.Warning, "업데이트 실패", message, parent=self)
        open_btn = box.addButton("직접 받기", QMessageBox.AcceptRole)
        box.addButton("닫기", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl(self._release.page_url))

    def _skip(self) -> None:
        set_update_skip_version(self._release.version)
        self.reject()


# ── 외부 진입점 ────────────────────────────────────────────────────

class UpdateChecker:
    """부모 위젯에 붙어 백그라운드로 새 버전을 확인하고 안내 창을 띄운다.

    참조를 들고 있지 않으면 QThread가 중간에 수거되므로 부모가 보관해야 한다.
    """

    def __init__(self, parent) -> None:
        self._parent = parent
        self._thread: _CheckThread | None = None
        self._silent = True

    def start(self, silent: bool = True) -> None:
        """silent=True면 새 버전이 있을 때만 창을 띄운다(시작 시 자동 확인용)."""
        if self._thread and self._thread.isRunning():
            return
        if silent and not update_service.is_frozen():
            return  # 개발 환경에서는 자동 확인하지 않는다

        self._silent = silent
        self._thread = _CheckThread(self._parent)
        self._thread.done.connect(self._on_checked)
        self._thread.start()

    def _on_checked(self, release: ReleaseInfo | None, error: str) -> None:
        if error:
            self._report(
                "업데이트 확인 실패",
                "최신 버전 정보를 가져오지 못했습니다.\n"
                "인터넷 연결이나 방화벽을 확인해주세요.\n\n"
                f"{error}",
                offer_page=True,
            )
            return

        if release is None:
            self._report(
                "업데이트 확인 실패",
                "최신 릴리스에서 GymOps.exe 파일을 찾지 못했습니다.",
                offer_page=True,
            )
            return

        if not update_service.is_newer(release.version):
            self._report(
                "업데이트",
                f"현재 최신 버전입니다.\n\n"
                f"설치된 버전: v{APP_VERSION}\n"
                f"서버 최신 버전: v{release.version}",
            )
            return

        if self._silent and release.version == get_update_skip_version():
            return

        if not update_service.is_frozen():
            self._report(
                "업데이트",
                f"새 버전 v{release.version} 이 있습니다.\n"
                "개발 환경에서는 자동 설치하지 않습니다.",
                always=True,
            )
            return

        UpdateDialog(release, parent=self._parent).exec()

    def _report(self, title: str, message: str, offer_page: bool = False,
                always: bool = False) -> None:
        """수동 확인일 때만 결과를 알린다. 자동 확인은 조용히 넘어간다."""
        if self._silent and not always:
            return
        if not offer_page:
            QMessageBox.information(self._parent, title, message)
            return

        box = QMessageBox(QMessageBox.Warning, title, message, parent=self._parent)
        open_btn = box.addButton("릴리스 페이지 열기", QMessageBox.AcceptRole)
        box.addButton("닫기", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl(update_service.RELEASES_PAGE))
