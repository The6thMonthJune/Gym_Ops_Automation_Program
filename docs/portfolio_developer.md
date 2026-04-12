# 포트폴리오 — 개발자 관점
# Gym Ops Automation Program

> 헬스장 현장 반복 업무를 자동화한 Python 데스크톱 앱  
> 개인 프로젝트 | 2025.12 ~ 2026.04 | Python / PySide6 / xlwings

---

## 프로젝트 개요

헬스장 직원으로 근무하면서 매일 반복되는 엑셀 작업과 카카오톡 보고 업무를 직접 분석하고, Python으로 자동화 프로그램을 설계·구현했습니다. 실제 현장에 배포해 사용 중입니다.

**GitHub:** https://github.com/The6thMonthJune/Gym_Ops_Automation_Program

---

## 해결한 문제

| 기존 업무 | 소요 시간 | 자동화 결과 |
|-----------|-----------|-------------|
| 데일리 엑셀 파일 복사·날짜 변경 | 2~3분/일 | 버튼 1번 → 1초 |
| 매출 보고 문구 수동 작성 | 3~5분/일 | 자동 생성 + 복사 |
| 결제 내역 2개 파일 이중 등록 | 5~10분/건 | 폼 입력 → 자동 기록 |
| 지출 내역 2개 파일 등록 + 카톡 보고 | 5분/건 | 폼 입력 → 자동 기록 + 문구 생성 |

---

## 기술 스택

- **Python 3.11**, **PySide6 (Qt6)** — 데스크톱 GUI
- **xlwings** — Excel COM 연동 (파일이 열려 있어도 쓰기 가능)
- **openpyxl** — 셀 읽기
- **msoffcrypto-tool** — 암호화 Excel 파일 해제
- **pytest** — 단위 테스트 15건
- **PyInstaller** — 단일 EXE 빌드 (Python 미설치 PC 배포)

---

## 아키텍처

```
ui (PySide6 다이얼로그)
    ↓
services (Excel 읽기/쓰기, 보고 문구 생성)
    ↓
core (날짜 파싱, 파일명 처리)
```

단방향 의존 구조로 각 계층을 독립적으로 테스트할 수 있도록 설계했습니다.  
UI는 서비스 레이어를 호출하되, 서비스는 UI를 참조하지 않습니다.

---

## 주요 기술 구현 포인트

### 1. Excel 열림 여부와 무관한 쓰기 (xlwings)

처음에는 openpyxl로 구현했으나, 헬스장 PC에서 Excel 파일을 열어둔 채 프로그램을 실행하면 `PermissionError`가 발생하는 문제를 현장에서 발견했습니다.

**해결:** xlwings로 전환해 Excel COM 인터페이스를 활용. 실행 중인 Excel 인스턴스에 이미 열린 파일이 있으면 그대로 연결하고, 없으면 숨김 인스턴스를 생성해 처리합니다.

```python
def _open_book(path, password=None):
    # 실행 중인 Excel에서 이미 열린 파일 탐색
    for app in xw.apps:
        for book in app.books:
            if Path(book.fullname).resolve() == resolved:
                return book, True  # was_already_open=True
    # 없으면 숨김 인스턴스 생성
    new_app = xw.App(visible=False)
    return new_app.books.open(str(resolved)), False
```

### 2. 시트명 Fuzzy 매칭

총매출 파일의 시트 이름이 담당자마다 `총 매출25년_9월`, `총 매출26년 4월`, `총 매출26년 04월`처럼 일관되지 않았습니다.

**해결:** 연도 토큰(`26년`)과 월 토큰(`4월`, `04월`) 두 가지를 독립적으로 검사하는 fuzzy 탐색 함수를 구현했습니다. 지출 시트(`총 지출26년 4월`)도 동일한 패턴으로 별도 함수로 처리했습니다.

```python
def find_monthly_sheet_name(sheet_names, year, month):
    year_token = f"{year % 100}년"
    month_tokens = {f"{month}월", f"{month:02d}월"}
    for name in sheet_names:
        if "매출" in name and year_token in name:
            if any(mt in name for mt in month_tokens):
                return name
    raise ValueError(f"{year}년 {month}월 매출 시트를 찾을 수 없습니다.")
```

### 3. 센터/레슨 컬럼 분기

동일한 시트 내에서 센터 매출은 B열(col=2), 레슨 매출은 P열(col=16)부터 동일한 12컬럼 양식으로 기록됩니다.

**해결:** `SECTION_START_COL = {"센터": 2, "레슨": 16}` 상수를 정의하고, 모든 Excel 쓰기 연산을 `col_start + offset` 방식으로 처리해 코드 중복 없이 두 섹션을 지원했습니다.

```python
sheet.range((row_num, col_start)).value = [
    entry_datetime,      # +0: 계약일
    entry.entry_date.day,# +1: 일
    entry.name,          # +2: 회원명
    ...                  # +3 ~ +11
]
```

### 4. 중복 입력 방지

같은 날짜+회원명+금액의 항목이 이미 존재하면 경고를 표시하고, 사용자가 의도적으로 확인하면 강제 입력할 수 있습니다.

### 5. PyInstaller EXE 빌드 이슈 해결

`src/main.py`를 진입점으로 PyInstaller 빌드 시 `No module named 'src'` 오류가 발생했습니다.

**원인:** PyInstaller는 진입점 파일의 위치를 루트로 인식하기 때문에 `src/` 하위에서 시작하면 `src` 패키지 자체를 찾지 못합니다.

**해결:** 프로젝트 루트에 `run.py`를 생성하고 spec 파일의 진입점을 `run.py`로 변경 + `pathex=['.']` 추가했습니다.

---

## 버전별 주요 구현

| 버전 | 구현 내용 |
|------|-----------|
| v1.0 | 파일 생성, 매출 보고, 결제 이중 등록, 드래그&드롭, 경로 자동 저장 |
| v1.1 | 센터/레슨 라디오 버튼, PT 자동 pre-select, 컬럼 분기 로직 |
| v1.2 | 지출 입력 다이얼로그, 지출 시트 월별 탐색, 카톡 지출보고 문구 생성 |

---

## 브랜치 전략

```
main
├── feature/section-selector   → v1.1 PR 머지
├── feature/expense-report     → v1.2 PR 머지
├── feature/locker-management  → v2.0 개발 중
└── feat-네이트온-팀챗-자동-전송  → v1.3 개발 예정
```

---

## 테스트

```
tests/
├── test_file_naming.py          # 날짜 파싱, 월말/연말 경계 처리 (7건)
└── test_sales_report_service.py # 통화 포맷, 보고 헤더, 전체 보고문 (8건)
```

현장 특화 로직(날짜 경계, 시트 탐색)을 중점적으로 테스트합니다.

---

## 배운 점

- **현장 피드백이 설계를 바꾼다:** openpyxl → xlwings 전환, 비밀번호 GUI 관리 방식 전환 모두 현장에서 실제 사용하다 발견한 문제에서 시작했습니다.
- **단순함 우선:** 락카 관리 기능을 Playwright 자동 스크래핑으로 구현하려다가, 동일한 결과를 Excel 내보내기 파싱으로 더 안전하게 달성할 수 있다는 것을 확인하고 pivot했습니다.
- **레이어 분리의 실질적 가치:** UI와 서비스 로직을 분리해두었기 때문에, 기능 추가 시 서비스만 새로 작성하고 UI에서 호출하는 방식으로 빠르게 확장할 수 있었습니다.
