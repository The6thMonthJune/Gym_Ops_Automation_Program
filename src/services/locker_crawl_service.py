from __future__ import annotations

import re
import time
from datetime import date
from pathlib import Path
from typing import Callable

from src.services.broj_service import LockerRecord

_BROJ_BASE = "https://crm.broj.co.kr"

# 순서대로 처리할 섹션: (내부명, 드롭다운 검색 키워드)
# 모든 섹션을 드롭다운으로 명시적 선택 — 기본값 가정 시 남자 탈의실 누락 발생
_SECTIONS = [
    ("남자 탈의실", "남자 탈의실 락카"),
    ("회원복 락카", "회원복 락카"),
    ("메인 락카",   "메인 락카"),
]


def _make_driver():
    import platform
    import tempfile
    from selenium import webdriver

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
        import sys
        from selenium.webdriver.edge.options import Options as EdgeOptions
        from selenium.webdriver.edge.service import Service as EdgeService

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

        # 빌드 시 번들된 msedgedriver.exe를 우선 사용 → 런타임 네트워크 다운로드 불필요
        driver_candidates: list[Path] = []
        if getattr(sys, "frozen", False):
            driver_candidates.append(Path(sys._MEIPASS) / "drivers" / "msedgedriver.exe")
            driver_candidates.append(Path(sys.executable).parent / "drivers" / "msedgedriver.exe")
        else:
            driver_candidates.append(Path(__file__).parent.parent.parent / "drivers" / "msedgedriver.exe")

        for candidate in driver_candidates:
            if candidate.exists():
                return webdriver.Edge(service=EdgeService(executable_path=str(candidate)), options=opts)

        # 번들 드라이버가 없으면 Selenium Manager 자동 탐색 시도
        return webdriver.Edge(options=opts)

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

    driver = _make_driver()
    wait = WebDriverWait(driver, 40)  # 느린 PC 대응 — 20 → 40초
    all_records: list[LockerRecord] = []

    try:
        # ── 1. 로그인 ────────────────────────────────────────────────
        _log("브로제이 접속 중...")
        driver.get(_BROJ_BASE)

        # 랜딩 → OAuth 로그인 화면 (sleep 없이 버튼이 클릭 가능해질 때까지 대기)
        wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//button[contains(text(),'로그인 페이지')]")
        )).click()

        # login_id 필드가 나타날 때까지 대기 (sleep 불필요)
        wait.until(EC.presence_of_element_located((By.ID, "login_id"))).send_keys(username)
        driver.find_element(By.ID, "login_password").send_keys(password)
        driver.find_element(By.ID, "login-submit").click()
        _log("로그인 시도 중...")

        # 클릭 가능 상태까지 대기 (presence만으론 SPA 렌더 완료 보장 안 됨)
        wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//a[contains(text(),'락커관리')]")
        ))
        time.sleep(2)  # 느린 PC: DOM 있어도 SPA 내부 초기화 대기
        _log("로그인 완료")

        # ── 2. 락커관리 진입 ──────────────────────────────────────────
        driver.execute_script(
            "arguments[0].click();",
            driver.find_element(By.XPATH, "//a[contains(text(),'락커관리')]"),
        )
        # iframe이 DOM에 나타날 때까지 대기
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "iframe")))
        time.sleep(3)  # iframe 내부 콘텐츠 렌더링 여유 (2→3초)
        _log("락커관리 페이지 이동 완료")

        # ── 3. iframe[0] 전환 (콘텐츠 전체가 iframe 안에 있음) ──────
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        if not iframes:
            raise RuntimeError("락커관리 iframe을 찾을 수 없습니다.")
        driver.switch_to.frame(iframes[0])
        # 첫 번째 버튼이 나타날 때까지 대기
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "button")))
        _log("iframe 전환 완료")

        # ── 4. 3개 구역 순서대로 파싱 ───────────────────────────────
        for idx, (section_name, dropdown_keyword) in enumerate(_SECTIONS):
            _log(f"[{idx + 1}/3] {section_name} 수집 중...")

            if dropdown_keyword:
                # 드롭다운 열기 (JS click — 클릭 불가 오류 방지)
                more_btn = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//button[.//span[contains(text(),'더보기')]]")
                ))
                driver.execute_script("arguments[0].click();", more_btn)
                time.sleep(1.5)

                # 해당 섹션 선택
                section_item = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, f"//*[contains(text(),'{dropdown_keyword}') and not(contains(@class,'badge'))]")
                ))
                driver.execute_script("arguments[0].click();", section_item)
                time.sleep(4)  # 느린 PC 대응 — 2 → 4초

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
