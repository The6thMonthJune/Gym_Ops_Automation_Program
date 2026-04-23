from __future__ import annotations

import json
import urllib.error
import urllib.request

_PORT = 9094


def send_kakao(phone_ip: str, target: str, message: str) -> None:
    """
    target: "직원" | "알바"
    센터폰 메신저봇R HTTP 서버로 POST 요청을 보낸다.
    """
    url = f"http://{phone_ip}:{_PORT}"
    payload = json.dumps({"target": target, "msg": message}, ensure_ascii=True).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            res.read()
    except urllib.error.URLError as e:
        raise RuntimeError(f"센터폰 연결 실패 ({phone_ip}:{_PORT}): {e.reason}")


def is_reachable(phone_ip: str) -> bool:
    try:
        url = f"http://{phone_ip}:{_PORT}"
        req = urllib.request.Request(url, data=b"{}", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=2) as res:
            res.read()
        return True
    except Exception:
        return False
