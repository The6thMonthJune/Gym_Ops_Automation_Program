from __future__ import annotations

import base64
import subprocess
import threading
import time

_ADB_IME = "com.android.adbkeyboard/.AdbIME"
_LOCK = threading.Lock()


def _shell(*args: str, timeout: int = 10) -> str:
    try:
        result = subprocess.run(
            ["adb", "shell", *args],
            capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout.strip()
    except FileNotFoundError:
        raise RuntimeError("ADB를 찾을 수 없습니다. PATH에 adb가 등록돼 있는지 확인하세요.")
    except subprocess.TimeoutExpired:
        raise RuntimeError("ADB 명령 시간 초과.")


def is_connected() -> bool:
    try:
        result = subprocess.run(
            ["adb", "devices"],
            capture_output=True, text=True, timeout=5,
        )
        return any(
            line.endswith("\tdevice")
            for line in result.stdout.splitlines()
        )
    except Exception:
        return False


def send_kakao(target: str, message: str) -> None:
    """
    target: "직원" | "알바"
    센터폰 카카오톡이 트리거방에 열려 있어야 하며, ADBKeyboard 앱이 설치돼 있어야 함.
    """
    trigger_msg = f"[{target}]{message}"
    encoded = base64.b64encode(trigger_msg.encode("utf-8")).decode("ascii")

    with _LOCK:
        original_ime = _shell("settings", "get", "secure", "default_input_method")
        try:
            _shell("ime", "set", _ADB_IME)
            subprocess.run(
                ["adb", "shell", "am", "broadcast",
                 "-a", "ADB_INPUT_B64", "--es", "msg", encoded],
                capture_output=True, timeout=10,
            )
            time.sleep(0.5)  # 입력 완료 대기
            _shell("input", "keyevent", "66")  # Enter → 전송
        finally:
            if original_ime:
                _shell("ime", "set", original_ime)
