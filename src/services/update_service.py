"""GitHub Release에서 새 EXE를 내려받아 자기 자신을 교체하는 자동 업데이트.

게임 런처처럼 프로그램이 스스로 최신 버전을 확인하고 받아서 재시작한다.
센터 PC에 직접 가지 않아도 태그만 푸시하면 다음 실행 때 반영된다.

윈도우는 '실행 중인 EXE를 덮어쓰는 것'은 막지만 '이름을 바꾸는 것'은 허용한다.
그래서 현재 EXE를 .old로 밀어내고 그 자리에 새 EXE를 놓는 방식을 쓴다.
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import requests

from src.config.constants import APP_VERSION

_REPO = "The6thMonthJune/Gym_Ops_Automation_Program"
_LATEST_API = f"https://api.github.com/repos/{_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{_REPO}/releases/latest"
_ASSET_NAME = "GymOps.exe"
_TIMEOUT = 10
_CHUNK = 256 * 1024
_HEADERS = {
    "User-Agent": f"GymOps/{APP_VERSION}",
    "Accept": "application/vnd.github+json",
}


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    download_url: str
    size: int
    notes: str
    page_url: str


# ── 버전 비교 ──────────────────────────────────────────────────────────────────

def parse_version(text: str) -> tuple[int, ...]:
    """'v3.0.11' → (3, 0, 11). 숫자가 아닌 조각은 0으로 취급한다."""
    cleaned = text.strip().lstrip("vV").split("-")[0].split("+")[0]
    parts = []
    for chunk in cleaned.split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) if parts else (0,)


def is_newer(latest: str, current: str = APP_VERSION) -> bool:
    a, b = parse_version(latest), parse_version(current)
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


# ── 실행 환경 ──────────────────────────────────────────────────────────────────

def is_frozen() -> bool:
    """PyInstaller EXE로 실행 중인지. 개발 환경에서는 자동 업데이트를 돌리지 않는다."""
    return bool(getattr(sys, "frozen", False))


def current_exe() -> Path:
    return Path(sys.executable).resolve()


def _backup_path() -> Path:
    exe = current_exe()
    return exe.with_name(exe.name + ".old")


def _download_path() -> Path:
    exe = current_exe()
    return exe.with_name(exe.name + ".download")


def cleanup_leftovers() -> None:
    """지난 업데이트가 남긴 .old / .download 파일을 정리한다.

    교체 직후에는 이전 프로세스가 아직 .old를 붙잡고 있을 수 있어 실패할 수 있다.
    그때는 그냥 넘어가고 다음 실행에서 지운다.
    """
    if not is_frozen():
        return  # 개발 환경에서는 sys.executable이 파이썬 인터프리터다
    for leftover in (_backup_path(), _download_path()):
        try:
            leftover.unlink(missing_ok=True)
        except OSError:
            pass


# ── 확인 · 다운로드 · 적용 ──────────────────────────────────────────────────────

def fetch_latest_release(timeout: int = _TIMEOUT) -> ReleaseInfo | None:
    """GitHub 최신 릴리스 정보를 읽는다. EXE 자산이 없으면 None."""
    # urllib 대신 requests를 쓴다. 구글 시트 연동이 이미 requests로 동작하므로
    # 센터 PC에서 인증서·프록시 설정이 검증된 경로다.
    response = requests.get(_LATEST_API, headers=_HEADERS, timeout=timeout)
    response.raise_for_status()
    payload = response.json()

    tag = str(payload.get("tag_name") or "")
    asset = next(
        (a for a in payload.get("assets", []) if a.get("name") == _ASSET_NAME), None
    )
    if not tag or not asset or not asset.get("browser_download_url"):
        return None

    return ReleaseInfo(
        version=tag.lstrip("vV"),
        download_url=str(asset["browser_download_url"]),
        size=int(asset.get("size") or 0),
        notes=str(payload.get("body") or "").strip(),
        page_url=str(payload.get("html_url") or RELEASES_PAGE),
    )


def check_for_update(timeout: int = _TIMEOUT) -> ReleaseInfo | None:
    """현재 버전보다 새 릴리스가 있으면 반환. 없거나 확인에 실패하면 None.

    네트워크가 끊긴 센터에서도 프로그램이 멀쩡히 켜져야 하므로 예외를 삼킨다.
    """
    try:
        release = fetch_latest_release(timeout)
    except Exception:
        return None
    return release if release and is_newer(release.version) else None


def download_release(release: ReleaseInfo, progress=None) -> Path:
    """새 EXE를 EXE 폴더 옆에 받는다. progress(받은_바이트, 전체_바이트) 콜백.

    같은 폴더에 받아야 마지막 교체가 같은 볼륨 안에서의 이름 변경으로 끝난다.
    """
    target = _download_path()
    target.unlink(missing_ok=True)

    with requests.get(
        release.download_url, headers=_HEADERS, timeout=_TIMEOUT, stream=True
    ) as response:
        response.raise_for_status()
        total = int(response.headers.get("Content-Length") or release.size or 0)
        received = 0
        with target.open("wb") as out:
            for chunk in response.iter_content(_CHUNK):
                out.write(chunk)
                received += len(chunk)
                if progress:
                    progress(received, total)

    if release.size and target.stat().st_size != release.size:
        target.unlink(missing_ok=True)
        raise OSError("다운로드가 중간에 끊겼습니다. 네트워크를 확인하고 다시 시도해주세요.")

    return target


def apply_update(new_exe: Path) -> Path:
    """받은 EXE를 현재 EXE 자리에 놓는다. 실패하면 원래대로 되돌린다."""
    exe = current_exe()
    backup = _backup_path()

    try:
        backup.unlink(missing_ok=True)
    except OSError:
        pass

    exe.rename(backup)
    try:
        Path(new_exe).replace(exe)
    except Exception:
        backup.rename(exe)  # 롤백: 교체 실패해도 기존 EXE는 살아 있어야 한다
        raise
    return exe


# PyInstaller onefile 부트로더가 자식에게 물려주면 안 되는 환경변수.
# _MEIPASS2가 설정된 채로 새 EXE를 띄우면 "압축은 이미 풀렸다"고 판단해
# 부모의 임시 폴더를 그대로 쓴다. 곧이어 부모가 종료되며 그 폴더를 지우기 때문에
# 자식은 뒤늦게 불러오는 모듈부터 ModuleNotFoundError로 깨진다.
_PYI_ENV_PREFIXES = ("_MEIPASS", "_PYI")


def _clean_child_env() -> dict[str, str]:
    """새 프로세스가 자기 몫의 압축을 새로 풀도록 부트로더 변수를 걷어낸다."""
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(_PYI_ENV_PREFIXES)
    }


def restart(exe: Path | None = None) -> None:
    """새 EXE를 띄운다. 호출한 쪽에서 현재 프로세스를 종료해야 한다."""
    subprocess.Popen(
        [str(exe or current_exe())], close_fds=True, env=_clean_child_env()
    )
