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

_EDGE_DRIVER_DOWNLOAD = "https://developer.microsoft.com/microsoft-edge/tools/webdriver/"

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
    return (
        "락카 동기화에 쓸 엣지 드라이버를 준비하지 못했습니다.\n\n"
        f"설치된 엣지 버전: {edge_label}\n"
        "인터넷이 막혀 있거나 백신이 드라이버 다운로드를 차단했을 수 있습니다.\n\n"
        "직접 해결하려면:\n"
        f"1. {_EDGE_DRIVER_DOWNLOAD} 에서\n"
        f"   설치된 엣지와 같은 버전({edge_label})의 Edge WebDriver (x64)를 받습니다.\n"
        "2. 압축을 풀어 나온 msedgedriver.exe 를\n"
        f"   {_SETTINGS_DIR} 폴더에 넣고 프로그램을 다시 실행합니다.\n\n"
        f"원본 오류: {exc}"
    )


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

    # 맞는 드라이버가 없으면 Selenium Manager가 엣지에 맞춰 내려받는다 (한 번 받으면 캐시됨)
    log("엣지에 맞는 드라이버를 준비하는 중...")
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

_LOGIN_FIELD_ID = "login_id"

# text()는 직계 텍스트 노드만 본다. <button><span>로그인</span></button> 같은
# 중첩 구조도 잡으려면 . 으로 비교해야 한다.
_LOGIN_ENTRY_XPATHS = [
    "//button[contains(., '로그인 페이지')]",
    "//a[contains(., '로그인 페이지')]",
    "//*[@role='button'][contains(., '로그인 페이지')]",
    "//button[contains(., '로그인')]",
    "//a[contains(., '로그인')]",
    "//input[@type='button' or @type='submit'][contains(@value, '로그인')]",
]


def _open_login_form(driver, wait, log: Callable[[str], None]) -> None:
    """로그인 입력란이 보일 때까지 진입한다. 이미 보이면 아무것도 하지 않는다."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    if driver.find_elements(By.ID, _LOGIN_FIELD_ID):
        log("로그인 폼이 이미 표시됨")
        return

    for xpath in _LOGIN_ENTRY_XPATHS:
        elements = driver.find_elements(By.XPATH, xpath)
        if not elements:
            continue
        try:
            elements[0].click()
        except Exception:
            continue
        log(f"로그인 페이지 진입 ({xpath})")
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, _LOGIN_FIELD_ID))
        )
        return

    # 버튼 없이 바로 폼이 뜨는 경우를 대비해 한 번 더 기다려본다
    wait.until(EC.presence_of_element_located((By.ID, _LOGIN_FIELD_ID)))


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

    return (
        "브로제이 로그인 화면으로 들어가지 못했습니다.\n\n"
        f"현재 주소: {url}\n"
        f"페이지 제목: {title}\n"
        f"화면의 버튼·링크: {button_line}\n\n"
        "사이트 화면 구성이 바뀌었을 수 있습니다.\n"
        "위 내용을 그대로 제작자에게 전달해주세요.\n\n"
        f"원본 오류: {exc}"
    )


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
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
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

        wait.until(EC.presence_of_element_located((By.ID, "login_id"))).send_keys(username)
        driver.find_element(By.ID, "login_password").send_keys(password)
        driver.find_element(By.ID, "login-submit").click()
        _log("로그인 시도 중...")

        wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//a[contains(text(),'락커관리')]")
        ))
        time.sleep(2)  # SPA 내부 초기화 대기
        _log("로그인 완료")

        # ── 2. 락커관리 진입 ──────────────────────────────────────────
        driver.find_element(By.XPATH, "//a[contains(text(),'락커관리')]").click()
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "iframe")))
        time.sleep(3)
        _log("락커관리 페이지 이동 완료")

        # ── 3. iframe[0] 전환 ──────────────────────────────────────────
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        if not iframes:
            raise RuntimeError("락커관리 iframe을 찾을 수 없습니다.")
        driver.switch_to.frame(iframes[0])
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "button")))
        _log("iframe 전환 완료")

        # ── 4. 3개 구역 순서대로 파싱 ───────────────────────────────
        for idx, (section_name, dropdown_keyword) in enumerate(_SECTIONS):
            _log(f"[{idx + 1}/3] {section_name} 수집 중...")

            if dropdown_keyword:
                # JS click 대신 native click — 보안 소프트웨어 간섭 최소화
                more_btn = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//button[.//span[contains(text(),'더보기')]]")
                ))
                more_btn.click()
                time.sleep(2)

                section_item = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, f"//*[contains(text(),'{dropdown_keyword}') and not(contains(@class,'badge'))]")
                ))
                section_item.click()
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
