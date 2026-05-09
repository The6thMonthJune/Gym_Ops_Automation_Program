from __future__ import annotations

import json
import urllib.error
import urllib.request


def send_webhook(webhook_url: str, text: str) -> None:
    """네이트온 팀룸 인커밍 웹훅으로 텍스트 메시지를 전송한다."""
    if not webhook_url:
        raise ValueError("웹훅 URL이 설정되어 있지 않습니다.")

    body = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            if res.status not in (200, 201, 204):
                raise RuntimeError(f"웹훅 전송 실패 (HTTP {res.status})")
    except urllib.error.URLError as e:
        raise RuntimeError(f"웹훅 전송 오류: {e}") from e
