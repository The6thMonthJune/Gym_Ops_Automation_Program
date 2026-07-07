from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

_SETTINGS_DIR = Path(os.environ.get("APPDATA", "~")).expanduser() / "리와인드자동화"
_COUNTDOWN_FILE = _SETTINGS_DIR / "countdown.json"


def load_period_settings() -> dict:
    """저장된 카운트다운 기간 설정을 반환한다.

    반환 키:
      center_target  - 센터 목표금액
      pt_target      - 피티 목표금액
      start_date     - 기간 시작일 (date)
      end_date       - 기간 종료일 (date)
    """
    if not _COUNTDOWN_FILE.exists():
        return {}
    try:
        data = json.loads(_COUNTDOWN_FILE.read_text(encoding="utf-8"))
        if isinstance(data.get("start_date"), str):
            data["start_date"] = date.fromisoformat(data["start_date"])
        if isinstance(data.get("end_date"), str):
            data["end_date"] = date.fromisoformat(data["end_date"])
        return data
    except Exception:
        return {}


def save_period_settings(
    center_target: int,
    pt_target: int,
    start_date: date,
    end_date: date,
) -> None:
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    _COUNTDOWN_FILE.write_text(
        json.dumps(
            {
                "center_target": center_target,
                "pt_target": pt_target,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
