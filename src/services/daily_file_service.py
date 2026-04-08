from __future__ import annotations

import shutil
from pathlib import Path

from src.core.file_naming import build_next_date_path

def create_next_daily_file(source_file: str | Path, overwrite: bool = False) -> Path:
    """
    원본 파일을 복사하여 다음 날짜 파일을 생성한다.
    """

    source_path = Path(source_file)

    if not source_path.exists():
        raise FileNotFoundError(f"원본 파일을 찾을 수 없습니다: {source_path}")
    
    target_path = build_next_date_path(source_path)

    if target_path.exists() and not overwrite:
        raise FileExistsError(f"이미 대상 파일이 존재합니다: {target_path}")
    
    shutil.copy2(source_path, target_path)
    return target_path