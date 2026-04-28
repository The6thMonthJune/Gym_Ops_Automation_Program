from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import os

_DATA_DIR = Path(os.environ.get("APPDATA", "~")).expanduser() / "리와인드자동화"
_DB_PATH = _DATA_DIR / "member_leads.db"

CHANNELS = ["SNS", "인터넷", "전단지", "소개", "기타"]


@dataclass
class MemberLead:
    member_name: str
    contract_date: date
    channel: str                   # SNS | 인터넷 | 전단지 | 소개 | 기타
    channel_detail: str | None     # 기타일 때 세부 내용
    residence_district: str | None # 동 단위 거주지 (예: 중산동)
    registration_type: str = "신규"
    source: str = "manual"         # manual | ocr
    raw_ocr_text: str | None = None
    id: int | None = None
    created_at: datetime | None = None


def _connect() -> sqlite3.Connection:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS member_leads (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            member_name         TEXT    NOT NULL,
            contract_date       TEXT    NOT NULL,
            channel             TEXT    NOT NULL,
            channel_detail      TEXT,
            residence_district  TEXT,
            registration_type   TEXT    DEFAULT '신규',
            source              TEXT    DEFAULT 'manual',
            raw_ocr_text        TEXT,
            created_at          TEXT    NOT NULL
        )
    """)
    conn.commit()


def save_lead(lead: MemberLead) -> int:
    """DB에 저장하고 생성된 id를 반환한다."""
    with _connect() as conn:
        _ensure_table(conn)
        cur = conn.execute(
            """
            INSERT INTO member_leads
                (member_name, contract_date, channel, channel_detail,
                 residence_district, registration_type, source, raw_ocr_text, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lead.member_name,
                lead.contract_date.isoformat(),
                lead.channel,
                lead.channel_detail,
                lead.residence_district,
                lead.registration_type,
                lead.source,
                lead.raw_ocr_text,
                datetime.now().isoformat(),
            ),
        )
        return cur.lastrowid


def load_leads(
    year: int | None = None,
    month: int | None = None,
) -> list[MemberLead]:
    """전체 또는 특정 연/월 필터로 리드 목록을 반환한다."""
    with _connect() as conn:
        _ensure_table(conn)
        if year and month:
            prefix = f"{year:04d}-{month:02d}"
            rows = conn.execute(
                "SELECT * FROM member_leads WHERE contract_date LIKE ? ORDER BY contract_date DESC",
                (f"{prefix}%",),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM member_leads ORDER BY contract_date DESC"
            ).fetchall()

    return [_row_to_lead(r) for r in rows]


def count_by_channel(
    year: int | None = None,
    month: int | None = None,
) -> dict[str, int]:
    """채널별 신규 회원 수를 반환한다."""
    leads = load_leads(year, month)
    counts: dict[str, int] = {ch: 0 for ch in CHANNELS}
    for lead in leads:
        key = lead.channel if lead.channel in counts else "기타"
        counts[key] += 1
    return counts


def count_by_district(
    year: int | None = None,
    month: int | None = None,
) -> dict[str, int]:
    """거주지역(동)별 신규 회원 수를 반환한다."""
    leads = load_leads(year, month)
    counts: dict[str, int] = {}
    for lead in leads:
        district = lead.residence_district or "미입력"
        counts[district] = counts.get(district, 0) + 1
    return counts


def _row_to_lead(row: sqlite3.Row) -> MemberLead:
    return MemberLead(
        id=row["id"],
        member_name=row["member_name"],
        contract_date=date.fromisoformat(row["contract_date"]),
        channel=row["channel"],
        channel_detail=row["channel_detail"],
        residence_district=row["residence_district"],
        registration_type=row["registration_type"],
        source=row["source"],
        raw_ocr_text=row["raw_ocr_text"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )
