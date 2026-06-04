from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from base64 import b64encode

_DEFAULT_PORT = 8080


def _to_international(phone: str) -> str:
    """한국 전화번호를 국제 형식(+82...)으로 변환한다."""
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("0"):
        return "+82" + digits[1:]
    if digits.startswith("82"):
        return "+" + digits
    return "+" + digits


def send_bulk_sms(
    phone_ip: str,
    phone_numbers: list[str],
    message: str,
    port: int = _DEFAULT_PORT,
    username: str = "user",
    password: str = "password",
) -> None:
    """
    android-sms-gateway 앱 REST API로 대량 SMS를 발송한다.
    실패 시 RuntimeError를 발생시킨다.

    API: POST http://<phone_ip>:<port>/message
    """
    if not phone_numbers:
        raise ValueError("수신자 번호가 없습니다.")

    numbers_intl = [_to_international(p) for p in phone_numbers]
    url = f"http://{phone_ip}:{port}/message"
    payload = json.dumps({
        "textMessage": {"text": message},
        "phoneNumbers": numbers_intl,
    }, ensure_ascii=False).encode("utf-8")

    credentials = b64encode(f"{username}:{password}".encode()).decode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {credentials}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            res.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"SMS Gateway 오류 (HTTP {e.code}): {e.reason}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"SMS Gateway 연결 실패 ({phone_ip}:{port}): {e.reason}")


def is_reachable(
    phone_ip: str,
    port: int = _DEFAULT_PORT,
    username: str = "user",
    password: str = "password",
) -> bool:
    try:
        credentials = b64encode(f"{username}:{password}".encode()).decode()
        url = f"http://{phone_ip}:{port}/message"
        req = urllib.request.Request(
            url,
            data=b'{"textMessage":{"text":"ping"},"phoneNumbers":[]}',
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Basic {credentials}",
            },
        )
        with urllib.request.urlopen(req, timeout=2) as res:
            res.read()
        return True
    except Exception:
        return False
