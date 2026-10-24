from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from typing import Callable

from src.config.settings import _SETTINGS_DIR
from src.services.broj_service import LockerRecord

_EDGE_DRIVER_PAGE = "https://developer.microsoft.com/ko-kr/microsoft-edge/tools/webdriver/"
# Selenium Manager가 쓰는 msedgedriver.azureedge.net 은 폐기돼 더 이상 응답하지 않는다.
# 공식 배포 서버에서 직접 받는다.
_EDGEDRIVER_BASE = "https://msedgedriver.microsoft.com"

_BROJ_BASE = "https://crm.broj.co.kr"

# 순서대로 처리할 섹션: (내부명, 드롭다운 검색 키워드)
# 모든 섹션을 드롭다운으로 명시적 선택 — 기본값 가정 시 남자 탈의실 누락 발생
_SECTIONS = [
    ("남자 탈의실", "남자 탈의실 락카"),
    ("회원복 락카", "회원복 락카"),
    ("메인 락카",   "메인 락카"),
]


# ── Edge 드라이버 준비 ─────────────────────────────────────────────────────────
# msedgedriver는 설치된 엣지와 메이저 버전이 같아야 한다. 빌드 시 번들한 드라이버는
# 센터 PC의 엣지가 자동 업데이트되는 순간 어긋나므로, 버전을 확인해서 맞을 때만 쓰고
# 아니면 Selenium Manager가 엣지에 맞는 드라이버를 내려받게 한다.

def _major(text: str) -> int | None:
    match = re.search(r"(\d+)\.\d+\.\d+", text or "")
    return int(match.group(1)) if match else None


def _exe_version(path: Path) -> str:
    """실행 파일의 --version 출력. 창 없는 앱에서 콘솔이 깜빡이지 않게 한다."""
    try:
        done = subprocess.run(
            [str(path), "--version"],
            capture_output=True, text=True, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return ""
    return (done.stdout or done.stderr or "").strip()


def _installed_edge_major() -> int | None:
    """설치된 엣지의 메이저 버전. 레지스트리 → 설치 폴더 순으로 확인한다."""
    try:
        import winreg
    except ImportError:
        return None

    for root, key, value_name in (
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Edge\BLBeacon", "version"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients"
         r"\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}", "pv"),
    ):
        try:
            with winreg.OpenKey(root, key) as handle:
                major = _major(str(winreg.QueryValueEx(handle, value_name)[0]))
            if major is not None:
                return major
        except OSError:
            continue

    # 레지스트리가 비어 있으면 설치 폴더의 버전 디렉터리 이름에서 읽는다
    for base in (
        r"C:\Program Files (x86)\Microsoft\Edge\Application",
        r"C:\Program Files\Microsoft\Edge\Application",
    ):
        folder = Path(base)
        if not folder.exists():
            continue
        majors = [_major(child.name) for child in folder.iterdir() if child.is_dir()]
        if found := [m for m in majors if m is not None]:
            return max(found)
    return None


def _edge_driver_candidates() -> list[Path]:
    """우선순위: 설정 폴더(사용자가 직접 넣은 것) → 빌드 번들 → EXE 옆 drivers."""
    paths = [_SETTINGS_DIR / "msedgedriver.exe"]
    if getattr(sys, "frozen", False):
        paths.append(Path(sys._MEIPASS) / "drivers" / "msedgedriver.exe")
        paths.append(Path(sys.executable).parent / "drivers" / "msedgedriver.exe")
    else:
        paths.append(Path(__file__).parents[2] / "drivers" / "msedgedriver.exe")
    return [p for p in paths if p.exists()]


def _driver_platform() -> str:
    """내려받을 드라이버 아키텍처. 대부분 win64다."""
    import platform

    machine = (os.environ.get("PROCESSOR_ARCHITECTURE") or platform.machine() or "").upper()
    return "arm64" if "ARM" in machine else "win64"


def _edge_driver_url(version: str) -> str:
    return f"{_EDGEDRIVER_BASE}/{version}/edgedriver_{_driver_platform()}.zip"


def _latest_driver_version(major: int, timeout: int = 15) -> str:
    """설치된 엣지 메이저에 맞는 드라이버 버전 문자열. 응답은 UTF-16으로 온다."""
    import requests

    response = requests.get(f"{_EDGEDRIVER_BASE}/LATEST_RELEASE_{major}", timeout=timeout)
    response.raise_for_status()
    try:
        version = response.content.decode("utf-16").strip()
    except UnicodeDecodeError:
        version = response.text.strip()
    if not re.fullmatch(r"\d+(\.\d+)+", version):
        raise RuntimeError(f"드라이버 버전 응답을 해석하지 못했습니다: {version[:40]!r}")
    return version


def _download_edge_driver(major: int, log: Callable[[str], None]) -> Path:
    """엣지 메이저에 맞는 msedgedriver를 내려받아 설정 폴더에 둔다.

    한 번 받으면 버전별 폴더에 남겨 다음 실행 때 그대로 쓴다.
    """
    import io
    import zipfile

    import requests

    version = _latest_driver_version(major)
    target_dir = _SETTINGS_DIR / "webdriver" / version
    target = target_dir / "msedgedriver.exe"
    if target.exists():
        log(f"받아둔 드라이버 사용 ({version})")
        return target

    url = _edge_driver_url(version)
    log(f"드라이버 내려받는 중... ({version})")
    response = requests.get(url, timeout=120)
    response.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        name = next(
            (n for n in archive.namelist() if n.endswith("msedgedriver.exe")), None
        )
        if name is None:
            raise RuntimeError("내려받은 압축 파일에 msedgedriver.exe가 없습니다.")
        target_dir.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.read(name))

    log(f"드라이버 준비 완료 ({version})")
    return target


def _driver_cache_dir() -> Path:
    """Selenium Manager가 받은 드라이버를 보관할 폴더. 다음 실행 때 재사용된다."""
    cache = _SETTINGS_DIR / "webdriver"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _ensure_selenium_manager() -> None:
    """EXE 안에 번들된 Selenium Manager 실행 파일 위치를 환경변수로 알려준다.

    selenium은 패키지 경로 기준으로 이 바이너리를 찾는데, PyInstaller 번들에서는
    탐색에 실패할 수 있다. 미리 잡아두면 자동 다운로드 경로가 끊기지 않는다.
    """
    if os.getenv("SE_MANAGER_PATH") or not getattr(sys, "frozen", False):
        return
    binary = (
        Path(sys._MEIPASS) / "selenium" / "webdriver" / "common"
        / "windows" / "selenium-manager.exe"
    )
    if binary.exists():
        os.environ["SE_MANAGER_PATH"] = str(binary)


def _driver_help_text(edge_major: int | None, exc: Exception) -> str:
    edge_label = str(edge_major) if edge_major else "확인 불가"
    try:
        direct = _edge_driver_url(_latest_driver_version(edge_major)) if edge_major else ""
    except Exception:
        direct = ""

    lines = [
        "락카 동기화에 쓸 엣지 드라이버를 준비하지 못했습니다.",
        "",
        f"설치된 엣지 버전: {edge_label}",
        "인터넷이 막혀 있거나 백신이 드라이버 다운로드를 차단했을 수 있습니다.",
        "",
        "직접 해결하려면:",
    ]
    if direct:
        lines += [
            f"1. 아래 주소에서 압축 파일을 받습니다.\n   {direct}",
        ]
    else:
        lines += [
            f"1. {_EDGE_DRIVER_PAGE} 에서\n"
            f"   설치된 엣지와 같은 버전({edge_label})의 Edge WebDriver (x64)를 받습니다.",
        ]
    lines += [
        "2. 압축을 풀어 나온 msedgedriver.exe 를",
        f"   {_SETTINGS_DIR} 폴더에 넣고 프로그램을 다시 실행합니다.",
        "",
        f"원본 오류: {exc}",
    ]
    return "\n".join(lines)


def _make_edge_driver(opts, log: Callable[[str], None]):
    from selenium import webdriver
    from selenium.webdriver.edge.service import Service as EdgeService

    edge_major = _installed_edge_major()
    log(f"엣지 버전 확인: {edge_major or '알 수 없음'}")

    for candidate in _edge_driver_candidates():
        driver_major = _major(_exe_version(candidate))
        if edge_major is not None and driver_major != edge_major:
            log(f"  드라이버 버전 불일치 (드라이버 {driver_major or '?'} ≠ 엣지 {edge_major}) — 건너뜀")
            continue
        try:
            return webdriver.Edge(
                service=EdgeService(executable_path=str(candidate)), options=opts
            )
        except Exception as exc:
            log(f"  드라이버 실행 실패: {exc}")

    # 맞는 드라이버가 없으면 공식 배포 서버에서 직접 받는다.
    # Selenium Manager는 폐기된 CDN을 보고 있어 더 이상 드라이버를 구하지 못한다.
    if edge_major is not None:
        try:
            downloaded = _download_edge_driver(edge_major, log)
            return webdriver.Edge(
                service=EdgeService(executable_path=str(downloaded)), options=opts
            )
        except Exception as exc:
            log(f"드라이버 직접 받기 실패: {exc}")

    # 마지막 수단
    log("Selenium Manager로 드라이버 준비 시도...")
    _ensure_selenium_manager()
    try:
        os.environ.setdefault("SE_CACHE_PATH", str(_driver_cache_dir()))
    except OSError:
        pass  # 설정 폴더에 쓸 수 없으면 기본 캐시 위치를 쓴다

    try:
        return webdriver.Edge(options=opts)
    except Exception as exc:
        raise RuntimeError(_driver_help_text(edge_major, exc)) from exc


def _make_driver(log: Callable[[str], None] | None = None):
    import platform
    import tempfile
    from selenium import webdriver

    def _log(msg: str) -> None:
        if log:
            log(msg)

    system = platform.system()

    # 공통 안정성 플래그 (메모리·렌더링 크래시 방지)
    # RendererCodeIntegrity 비활성: 보안SW가 브라우저에 코드를 주입할 때
    # GetHandleVerifier가 프로세스를 강제 종료하는 문제를 방지
    _common_args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--window-size=1280,800",
        "--disable-extensions",
        "--no-first-run",
        "--disable-default-apps",
        "--disable-sync",
        "--disable-translate",
        "--disable-background-timer-throttling",
        "--disable-features=RendererCodeIntegrity",
        f"--user-data-dir={tempfile.mkdtemp()}",
    ]

    if system == "Windows":
        from selenium.webdriver.edge.options import Options as EdgeOptions

        opts = EdgeOptions()
        for arg in _common_args:
            opts.add_argument(arg)

        for edge_path in [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]:
            if Path(edge_path).exists():
                opts.binary_location = edge_path
                break

        return _make_edge_driver(opts, _log)

    # Mac: Chrome + headless=new (Mac ARM은 --headless 크래시)
    from selenium.webdriver.chrome.options import Options
    opts = Options()
    opts.add_argument("--headless=new")
    for arg in _common_args:
        opts.add_argument(arg)

    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if Path(chrome_path).exists():
        opts.binary_location = chrome_path

    return webdriver.Chrome(options=opts)


# ── 로그인 진입 ────────────────────────────────────────────────────────────────
# 첫 화면에서 로그인 폼까지 들어가는 단계. 브로제이는 공개 API가 없어 DOM에 의존하므로
# 사이트가 마크업을 바꾸면 여기가 가장 먼저 깨진다. 셀렉터를 여러 개 두고, 그래도
# 실패하면 화면에 뭐가 있었는지 그대로 보여줘서 원격에서 원인을 잡을 수 있게 한다.

# 로그인 입력란은 id가 바뀔 수 있다. type="password"는 거의 바뀌지 않으므로
# 비밀번호 칸을 기준점으로 잡고 아이디 칸·제출 버튼을 구조로 찾는다.
# 메뉴 표기가 '락커'인지 '락카'인지 확실치 않아 둘 다 받는다.
_LOCKER_MENU_TEXTS = ("락커관리", "락카관리", "락커 관리", "락카 관리")

_PASSWORD_XPATH = "//input[@type='password']"
_ID_XPATHS = [
    "//input[@id='login_id']",
    "//input[@type='text' or @type='email' or @type='tel' or not(@type)]",
]
_SUBMIT_XPATHS = [
    "//*[@id='login-submit']",
    "//button[@type='submit']",
    "//button[contains(., '로그인')]",
    "//input[@type='submit']",
]

# text()는 직계 텍스트 노드만 본다. <button><span>로그인</span></button> 같은
# 중첩 구조도 잡으려면 . 으로 비교해야 한다.
_LOGIN_ENTRY_XPATHS = [
    "//button[contains(., '로그인')]",
    "//a[contains(., '로그인')]",
    "//*[@role='button'][contains(., '로그인')]",
    "//input[@type='button' or @type='submit'][contains(@value, '로그인')]",
]


def _to_top(driver) -> None:
    """최상위 문서로 돌아온다. iframe 안에 갇힌 채 탐색하면 아무것도 못 찾는다."""
    try:
        driver.switch_to.default_content()
    except Exception:
        pass


def _visible(elements: list) -> list:
    """화면에 보이는 것만 남긴다. 숨은 입력란을 잘못 집는 일을 막는다."""
    result = []
    for element in elements:
        try:
            if element.is_displayed():
                result.append(element)
        except Exception:
            continue
    return result


def _find_password_input(driver):
    """비밀번호 입력란을 찾는다. 모달이 iframe 안에 있으면 그 안까지 들어간다."""
    from selenium.webdriver.common.by import By

    found = _visible(driver.find_elements(By.XPATH, _PASSWORD_XPATH))
    if found:
        return found[0]

    for frame in driver.find_elements(By.TAG_NAME, "iframe"):
        try:
            driver.switch_to.frame(frame)
        except Exception:
            driver.switch_to.default_content()
            continue
        found = _visible(driver.find_elements(By.XPATH, _PASSWORD_XPATH))
        if found:
            return found[0]  # 호출자가 입력을 마친 뒤 default_content로 돌아와야 한다
        driver.switch_to.default_content()
    return None


def _open_login_form(driver, wait, log: Callable[[str], None]) -> None:
    """로그인 입력란이 보일 때까지 진입한다. 이미 보이면 아무것도 하지 않는다."""
    from selenium.webdriver.common.by import By

    if _find_password_input(driver):
        log("로그인 폼이 이미 표시됨")
        return

    for xpath in _LOGIN_ENTRY_XPATHS:
        elements = _visible(driver.find_elements(By.XPATH, xpath))
        if not elements:
            continue
        try:
            elements[0].click()
        except Exception:
            continue
        log(f"로그인 진입 클릭 ({xpath})")
        # 모달이 떠서 입력란이 그려질 때까지 기다린다
        for _ in range(20):
            if _find_password_input(driver):
                return
            time.sleep(0.5)

    if not _find_password_input(driver):
        raise RuntimeError("로그인 입력란(비밀번호 칸)을 찾지 못했습니다.")


def _submit_login(driver, username: str, password: str, log: Callable[[str], None]) -> None:
    """아이디·비밀번호를 넣고 로그인 버튼을 누른다.

    id가 바뀌어도 동작하도록 비밀번호 칸을 기준으로 폼 안에서 상대 탐색한다.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    password_input = _find_password_input(driver)
    if password_input is None:
        raise RuntimeError("비밀번호 입력란을 찾지 못했습니다.")

    id_input = None
    for xpath in _ID_XPATHS:
        candidates = [
            el for el in _visible(driver.find_elements(By.XPATH, xpath))
            if el != password_input
        ]
        if candidates:
            id_input = candidates[0]
            break
    if id_input is None:
        raise RuntimeError("아이디 입력란을 찾지 못했습니다.")

    id_input.clear()
    id_input.send_keys(username)
    password_input.clear()
    password_input.send_keys(password)
    log("아이디·비밀번호 입력 완료")

    try:
        for xpath in _SUBMIT_XPATHS:
            buttons = _visible(driver.find_elements(By.XPATH, xpath))
            if buttons:
                buttons[0].click()
                log(f"로그인 버튼 클릭 ({xpath})")
                return
        # 버튼을 못 찾으면 엔터로 제출을 시도한다
        password_input.send_keys(Keys.RETURN)
        log("로그인 버튼을 찾지 못해 엔터로 제출")
    finally:
        # 로그인 폼이 iframe 안에 있었다면 그 안에 머문 채로 끝난다.
        # 최상위로 돌아오지 않으면 이후 메뉴 탐색이 빈 화면을 보게 된다.
        _to_top(driver)


def _input_field_summary(driver, limit: int = 10) -> list[str]:
    """입력란의 id/name/type/placeholder를 모은다. 셀렉터가 깨졌을 때 단서가 된다."""
    from selenium.webdriver.common.by import By

    summary: list[str] = []
    try:
        for element in driver.find_elements(By.TAG_NAME, "input"):
            parts = [
                f"{key}={value}"
                for key, value in (
                    ("id", element.get_attribute("id")),
                    ("name", element.get_attribute("name")),
                    ("type", element.get_attribute("type")),
                    ("placeholder", element.get_attribute("placeholder")),
                )
                if value
            ]
            if parts:
                summary.append("<input " + " ".join(parts) + ">")
            if len(summary) >= limit:
                break
    except Exception:
        pass
    return summary


def _visible_button_texts(driver, limit: int = 15) -> list[str]:
    """화면에 보이는 버튼·링크 문구를 모은다. 셀렉터가 깨졌을 때 단서가 된다."""
    from selenium.webdriver.common.by import By

    texts: list[str] = []
    try:
        for element in driver.find_elements(By.XPATH, "//button | //a | //input[@type='submit']"):
            label = (element.text or element.get_attribute("value") or "").strip()
            if label and label not in texts:
                texts.append(label)
            if len(texts) >= limit:
                break
    except Exception:
        pass
    return texts


def _login_help_text(driver, exc: Exception) -> str:
    """원격에서 원인을 짚을 수 있도록 현재 화면 상태를 함께 담는다."""
    try:
        url = driver.current_url
        title = driver.title
    except Exception:
        url = title = "(확인 불가)"

    buttons = _visible_button_texts(driver)
    button_line = ", ".join(buttons) if buttons else "(없음)"
    inputs = _input_field_summary(driver)
    input_line = "\n  ".join(inputs) if inputs else "(없음)"

    return (
        "브로제이 로그인에 실패했습니다.\n\n"
        f"현재 주소: {url}\n"
        f"페이지 제목: {title}\n"
        f"화면의 버튼·링크: {button_line}\n"
        f"입력란:\n  {input_line}\n\n"
        "사이트 화면 구성이 바뀌었을 수 있습니다.\n"
        "위 내용을 그대로 제작자에게 전달해주세요.\n\n"
        f"원본 오류: {exc}"
    )


def _wait_for_text(driver, text: str, timeout: int = 30) -> bool:
    """문구가 화면에 나타날 때까지 기다린다. 중첩된 텍스트도 잡는다."""
    from selenium.webdriver.common.by import By

    deadline = time.monotonic() + timeout
    while True:
        if _visible(driver.find_elements(By.XPATH, f"//*[contains(., '{text}')]")):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.5)


def _wait_for_any_text(driver, texts, timeout: int = 30) -> str | None:
    """여러 후보 문구 중 먼저 나타나는 것을 돌려준다. 없으면 None."""
    deadline = time.monotonic() + timeout
    while True:
        for text in texts:
            if _wait_for_text(driver, text, timeout=0):
                return text
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.5)


def _click_any_text(driver, texts, log: Callable[[str], None]) -> bool:
    """후보 문구를 순서대로 눌러본다."""
    return any(_click_by_text(driver, text, log) for text in texts)


def _click_by_text(driver, text: str, log: Callable[[str], None]) -> bool:
    """문구가 들어간 클릭 가능한 요소를 찾아 누른다.

    text()는 직계 텍스트 노드만 보므로 <a><span>락커관리</span></a> 같은 구조를
    놓친다. . 으로 비교하고 요소 종류도 넓게 잡는다.
    """
    from selenium.webdriver.common.by import By

    for xpath in (
        f"//a[contains(., '{text}')]",
        f"//button[contains(., '{text}')]",
        f"//*[@role='button' or @role='menuitem'][contains(., '{text}')]",
        f"//li[contains(., '{text}')]",
        f"//span[contains(., '{text}')]",
        f"//*[contains(., '{text}')][not(.//*[contains(., '{text}')])]",
    ):
        for element in _visible(driver.find_elements(By.XPATH, xpath)):
            try:
                element.click()
            except Exception:
                continue
            log(f"'{text}' 클릭 ({xpath})")
            return True
    return False


def _scan_frames_for_buttons(driver, limit: int = 20) -> str:
    """최상위에 아무것도 없을 때 각 iframe 안의 버튼 문구를 모아본다."""
    from selenium.webdriver.common.by import By

    lines: list[str] = []
    frames = driver.find_elements(By.TAG_NAME, "iframe")
    for index, frame in enumerate(frames):
        _to_top(driver)
        try:
            driver.switch_to.frame(frame)
        except Exception:
            continue
        texts = _visible_button_texts(driver, limit=limit)
        if texts:
            lines.append(f"iframe#{index}: " + ", ".join(texts))
    _to_top(driver)
    return "\n  ".join(lines) if lines else "(없음)"


def _nav_help_text(driver, step: str, exc: Exception) -> str:
    """진행이 막힌 단계와 그때 화면에 뭐가 있었는지 함께 보여준다."""
    from selenium.webdriver.common.by import By

    _to_top(driver)  # 프레임 안에서 수집하면 빈 화면처럼 보인다
    try:
        url, title = driver.current_url, driver.title
        frames = len(driver.find_elements(By.TAG_NAME, "iframe"))
    except Exception:
        url = title = "(확인 불가)"
        frames = -1

    links = ", ".join(_visible_button_texts(driver, limit=25)) or "(없음)"
    if links == "(없음)" and frames > 0:
        links = _scan_frames_for_buttons(driver)
    return (
        f"락카 동기화가 '{step}' 단계에서 멈췄습니다.\n\n"
        f"현재 주소: {url}\n"
        f"페이지 제목: {title}\n"
        f"iframe 개수: {frames}\n"
        f"화면의 메뉴·버튼: {links}\n\n"
        "브로제이 화면 구성이 바뀐 것으로 보입니다.\n"
        "위 내용을 그대로 제작자에게 전달해주세요.\n\n"
        f"원본 오류: {exc}"
    )


def _switch_to_locker_frame(driver, log: Callable[[str], None]) -> bool:
    """락카 버튼이 들어 있는 iframe으로 전환한다.

    예전에는 iframe[0]으로 고정했는데, 프레임이 늘거나 순서가 바뀌면 깨진다.
    번호를 세는 대신 락카 번호가 보이는 프레임을 직접 찾는다.
    """
    from selenium.webdriver.common.by import By

    frames = driver.find_elements(By.TAG_NAME, "iframe")
    for index, frame in enumerate(frames):
        driver.switch_to.default_content()
        try:
            driver.switch_to.frame(frame)
        except Exception:
            continue
        buttons = driver.find_elements(By.TAG_NAME, "button")
        if any(_parse_button_text(b.text) for b in buttons[:80]):
            log(f"락카 iframe 전환 (iframe #{index})")
            return True

    # 프레임 없이 본문에 바로 그려지는 경우
    driver.switch_to.default_content()
    if any(_parse_button_text(b.text) for b in driver.find_elements(By.TAG_NAME, "button")[:80]):
        log("iframe 없이 본문에서 락카 버튼 발견")
        return True
    return False


def _parse_button_text(text: str) -> tuple[int, str, date | None, bool] | None:
    """로컬뷰 버튼 텍스트 → (전역번호, 이름, 만료일, is_holding).

    버튼 형식 예:
      "1\\n오동혁\\n~2027-02-22\\n233일후 만료\\n활성"
      "22"  ← 미배정, None 반환
    """
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if len(lines) < 2:
        return None

    try:
        num = int(lines[0])
    except ValueError:
        return None

    name = lines[1]
    expiry: date | None = None
    is_holding = False

    for line in lines[2:]:
        if line.startswith("~"):
            m = re.search(r"(\d{4}-\d{2}-\d{2})", line)
            if m:
                try:
                    expiry = date.fromisoformat(m.group(1))
                except ValueError:
                    pass
        if "홀딩" in line:
            is_holding = True

    return num, name, expiry, is_holding


def _collect_section(driver, section_name: str) -> list[LockerRecord]:
    """현재 섹션 박스뷰 버튼을 파싱해 LockerRecord 목록으로 반환한다."""
    from selenium.webdriver.common.by import By

    records: list[LockerRecord] = []
    btns = driver.find_elements(By.TAG_NAME, "button")
    for btn in btns:
        parsed = _parse_button_text(btn.text)
        if parsed is None:
            continue
        num, name, expiry, is_holding = parsed
        records.append(LockerRecord(
            member_name=name,
            locker_room=section_name,
            locker_number=num,
            has_key=True,
            expiry_date=None,
            start_date=None,
            is_holding=is_holding,
            membership_type=None,
            phone_number=None,
            locker_expiry=expiry,
            is_locker_scheduled=False,
        ))
    return records


def fetch_locker_records(
    username: str,
    password: str,
    log: Callable[[str], None] | None = None,
) -> list[LockerRecord]:
    """브로제이 CRM에 자동 로그인 후 3개 구역 락카 데이터를 직접 파싱한다.

    Excel 다운로드 없이 박스뷰 DOM에서 번호·이름·만료일을 직접 읽는다.

    Returns:
        3개 구역 전체 LockerRecord 목록

    Raises:
        RuntimeError: 로그인 실패 또는 페이지 탐색 오류
    """
    from selenium.webdriver.support.ui import WebDriverWait

    def _log(msg: str) -> None:
        if log:
            log(msg)

    driver = _make_driver(_log)
    wait = WebDriverWait(driver, 40)  # 느린 PC 대응 — 20 → 40초
    all_records: list[LockerRecord] = []

    try:
        # ── 1. 로그인 폼까지 진입 (네트워크 불안정 대비 최대 3회) ──────
        for attempt in range(1, 4):
            _log(f"브로제이 접속 중... (시도 {attempt}/3)")
            try:
                driver.get(_BROJ_BASE)
                _open_login_form(driver, wait, _log)
                break
            except Exception as exc:
                if attempt == 3:
                    raise RuntimeError(_login_help_text(driver, exc)) from exc
                _log(f"접속 실패, 5초 후 재시도... ({exc})")
                time.sleep(5)

        try:
            _submit_login(driver, username, password, _log)
        except Exception as exc:
            raise RuntimeError(_login_help_text(driver, exc)) from exc
        _log("로그인 시도 중...")

        # 로그인 성공 판정: 메뉴에 '락커관리'가 나타날 때까지 기다린다.
        # text()로 비교하면 <a><span>락커관리</span></a> 구조를 놓치므로 . 으로 본다.
        _to_top(driver)
        menu_text = _wait_for_any_text(driver, _LOCKER_MENU_TEXTS, timeout=40)
        if menu_text is None:
            raise RuntimeError(
                _nav_help_text(driver, "로그인 후 메뉴 대기",
                               RuntimeError("로그인은 됐지만 '락커관리' 메뉴가 보이지 않습니다. "
                                            "아이디·비밀번호가 틀렸거나 메뉴 구성이 바뀌었을 수 있습니다."))
            )
        time.sleep(2)  # SPA 내부 초기화 대기
        _log("로그인 완료")

        # ── 2. 락커관리 진입 ──────────────────────────────────────────
        try:
            if not _click_by_text(driver, menu_text, _log):
                raise RuntimeError(f"'{menu_text}' 메뉴를 찾지 못했습니다.")
            time.sleep(3)
        except Exception as exc:
            raise RuntimeError(_nav_help_text(driver, "락커관리 메뉴 진입", exc)) from exc
        _log("락커관리 페이지 이동 완료")

        # ── 3. 락카 버튼이 있는 프레임으로 전환 ───────────────────────
        if not _switch_to_locker_frame(driver, _log):
            raise RuntimeError(
                _nav_help_text(driver, "락카 목록 화면 찾기",
                               RuntimeError("락카 번호가 보이는 영역을 찾지 못했습니다."))
            )

        # ── 4. 3개 구역 순서대로 파싱 ───────────────────────────────
        for idx, (section_name, dropdown_keyword) in enumerate(_SECTIONS):
            _log(f"[{idx + 1}/3] {section_name} 수집 중...")

            if dropdown_keyword:
                # JS click 대신 native click — 보안 소프트웨어 간섭 최소화
                if not _click_by_text(driver, "더보기", _log):
                    raise RuntimeError(
                        _nav_help_text(driver, f"{section_name} — 더보기 버튼",
                                       RuntimeError("'더보기' 버튼을 찾지 못했습니다."))
                    )
                time.sleep(2)

                if not _click_by_text(driver, dropdown_keyword, _log):
                    raise RuntimeError(
                        _nav_help_text(driver, f"{section_name} 선택",
                                       RuntimeError(f"'{dropdown_keyword}' 항목을 찾지 못했습니다."))
                    )
                time.sleep(4)

            records = _collect_section(driver, section_name)
            all_records.extend(records)
            _log(f"  {section_name}: {len(records)}개 수집")

    except Exception as exc:
        _log(f"오류 발생: {exc}")
        raise RuntimeError(f"락카 데이터 가져오기 실패: {exc}") from exc
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return all_records
