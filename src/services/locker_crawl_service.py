from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

_BROJ_BASE = "https://crm.broj.co.kr"

# 구역 순서: (내부 이름, 탭 검색 키워드)
# 첫 번째 구역은 페이지 진입 시 기본 선택되어 있음
_SECTIONS: list[tuple[str, str]] = [
    ("남자 탈의실", "남자"),
    ("회원복 락카", "회원복"),
    ("메인 락카", "메인"),
]


def _make_driver(download_dir: str):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-extensions")
    opts.add_experimental_option("prefs", {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    })

    # 시스템에 설치된 chromedriver를 우선 사용 (Selenium Manager 자동 다운로드 실패 시 대비)
    import shutil
    driver_path = shutil.which("chromedriver")
    service = Service(driver_path) if driver_path else Service()

    driver = webdriver.Chrome(service=service, options=opts)

    # headless 모드에서 파일 다운로드 활성화 (CDP 명령)
    driver.execute_cdp_cmd("Page.setDownloadBehavior", {
        "behavior": "allow",
        "downloadPath": download_dir,
    })

    return driver


def _wait_new_xlsx(download_dir: Path, before: set[str], timeout: int = 30) -> Path | None:
    """새 xlsx 파일이 다운로드 완료될 때까지 폴링한다."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        current = {
            f.name for f in download_dir.glob("*.xlsx")
            if not f.name.endswith(".crdownload")
        }
        new = current - before
        if new:
            # 파일 쓰기가 완전히 끝났는지 잠시 대기
            time.sleep(0.3)
            return download_dir / next(iter(new))
        time.sleep(0.5)
    return None


def download_locker_excels(
    username: str,
    password: str,
    download_dir: Path,
    log: Callable[[str], None] | None = None,
) -> list[tuple[str, Path]]:
    """
    브로제이 CRM에 자동 로그인 후 락커관리 리스트 뷰에서
    3개 구역 엑셀을 순서대로 다운로드한다.

    Returns:
        [(section_name, file_path), ...]  — 성공한 구역만 포함

    Raises:
        RuntimeError: 로그인 실패 또는 페이지 탐색 오류
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    def _log(msg: str) -> None:
        if log:
            log(msg)

    download_dir.mkdir(parents=True, exist_ok=True)
    driver = _make_driver(str(download_dir.resolve()))
    wait = WebDriverWait(driver, 20)
    results: list[tuple[str, Path]] = []

    try:
        # ── 1. 로그인 ────────────────────────────────────────────────────
        _log("브로제이 접속 중...")
        driver.get(_BROJ_BASE)
        time.sleep(2)

        email_el = wait.until(EC.presence_of_element_located((
            By.CSS_SELECTOR,
            "input[type='email'], input[type='text']",
        )))
        email_el.clear()
        email_el.send_keys(username)

        pw_el = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
        pw_el.clear()
        pw_el.send_keys(password)

        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        _log("로그인 시도 중...")

        # 로그인 완료 = 대시보드 또는 사이드바 메뉴 등장
        wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//*[contains(text(),'락커관리') or contains(text(),'대시보드') or contains(text(),'인사이트')]",
        )))
        _log("로그인 완료")
        time.sleep(1)

        # ── 2. 락커관리 메뉴 클릭 ────────────────────────────────────────
        locker_menu = wait.until(EC.element_to_be_clickable((
            By.XPATH,
            "//a[contains(text(),'락커관리')] | //span[contains(text(),'락커관리')]/.. | //li[contains(text(),'락커관리')]",
        )))
        locker_menu.click()
        time.sleep(2)
        _log("락커관리 페이지 이동 완료")

        # ── 3. 3개 구역 순서대로 다운로드 ───────────────────────────────
        for idx, (section_name, tab_keyword) in enumerate(_SECTIONS):
            _log(f"[{idx + 1}/3] {section_name} 처리 중...")

            # 두 번째 구역부터는 탭 선택이 필요
            if idx > 0:
                # "더보기" 버튼이 있으면 클릭해 숨겨진 탭 펼치기
                try:
                    more_btns = driver.find_elements(
                        By.XPATH, "//*[contains(text(),'더보기')]"
                    )
                    for btn in more_btns:
                        if btn.is_displayed():
                            btn.click()
                            time.sleep(0.5)
                            break
                except Exception:
                    pass

                # 구역 탭 클릭
                section_tab = wait.until(EC.element_to_be_clickable((
                    By.XPATH, f"//*[contains(text(),'{tab_keyword}') and (self::button or self::a or self::li or self::span)]",
                )))
                section_tab.click()
                time.sleep(1.5)

            # 리스트 뷰로 전환
            list_btn = wait.until(EC.element_to_be_clickable((
                By.XPATH, "//button[normalize-space(text())='리스트'] | //*[normalize-space(text())='리스트' and (@role='button' or self::button)]",
            )))
            list_btn.click()
            time.sleep(1)
            _log(f"  리스트 뷰 전환 완료")

            # 엑셀 다운로드
            before_files = {f.name for f in download_dir.glob("*.xlsx")}

            excel_btn = wait.until(EC.element_to_be_clickable((
                By.XPATH,
                "//*[contains(text(),'엑셀') or contains(text(),'Excel') or "
                "contains(@title,'엑셀') or contains(@aria-label,'엑셀') or "
                "contains(@title,'Excel') or contains(@aria-label,'Excel')]",
            )))
            excel_btn.click()
            _log(f"  다운로드 클릭 — 완료 대기 중...")

            downloaded = _wait_new_xlsx(download_dir, before_files, timeout=30)
            if downloaded:
                # 구역명으로 파일 rename
                safe_name = section_name.replace(" ", "_")
                target = download_dir / f"locker_{idx + 1}_{safe_name}.xlsx"
                if target.exists():
                    target.unlink()
                downloaded.rename(target)
                results.append((section_name, target))
                _log(f"  저장 완료: {target.name}")
            else:
                _log(f"  [경고] {section_name} 다운로드 실패 또는 시간 초과")

    except Exception as exc:
        _log(f"오류 발생: {exc}")
        raise RuntimeError(f"락카 데이터 가져오기 실패: {exc}") from exc
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return results
