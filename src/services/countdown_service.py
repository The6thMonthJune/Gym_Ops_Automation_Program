from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

_SETTINGS_DIR = Path(os.environ.get("APPDATA", "~")).expanduser() / "리와인드자동화"
_COUNTDOWN_FILE = _SETTINGS_DIR / "countdown.json"


def load_countdown() -> dict:
    """
    저장된 카운트다운 상태를 반환한다.

    반환 키:
      date            - 마지막 저장 날짜 (YYYY-MM-DD)
      center_baseline - 해당 날짜 이전까지의 센터 누적 (당일 내 불변)
      pt_baseline     - 해당 날짜 이전까지의 피티 누적 (당일 내 불변)
      center_total    - 해당 날짜 포함 최종 누적 (저장 시 갱신)
      pt_total        - 해당 날짜 포함 최종 누적 (저장 시 갱신)
    """
    if not _COUNTDOWN_FILE.exists():
        return {}
    try:
        return json.loads(_COUNTDOWN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def compute_running(
    data: dict,
    today_center: int,
    today_pt: int,
) -> tuple[int, int, int, int]:
    """
    저장 데이터와 오늘 데일리 값으로 (running_center, running_pt, baseline_center, baseline_pt)를 계산한다.

    오늘 날짜가 저장 날짜와 같으면 baseline 그대로 사용해 이중 집계를 방지한다.
    새 날이면 전날 total을 baseline으로 승격한다.
    """
    today_str = date.today().isoformat()
    if data.get("date") == today_str:
        baseline_center = data.get("center_baseline", 0)
        baseline_pt = data.get("pt_baseline", 0)
    else:
        baseline_center = data.get("center_total", 0)
        baseline_pt = data.get("pt_total", 0)

    return (
        baseline_center + today_center,
        baseline_pt + today_pt,
        baseline_center,
        baseline_pt,
    )


def save_countdown(
    center_baseline: int,
    pt_baseline: int,
    center_total: int,
    pt_total: int,
) -> None:
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "date": date.today().isoformat(),
        "center_baseline": center_baseline,
        "pt_baseline": pt_baseline,
        "center_total": center_total,
        "pt_total": pt_total,
    }
    _COUNTDOWN_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
