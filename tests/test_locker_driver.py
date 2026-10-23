"""엣지 드라이버 버전 매칭 — 센터 PC의 엣지가 자동 업데이트돼도 동기화가 살아 있어야 한다."""
import pytest
from selenium import webdriver

from src.services import locker_crawl_service as svc


class TestMajor:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Microsoft Edge WebDriver 142.0.3595.53 (abc123)", 142),
            ("142.0.3595.53", 142),
            ("", None),
            ("버전 없음", None),
        ],
    )
    def test_parse(self, text, expected):
        assert svc._major(text) == expected


@pytest.fixture
def edge_env(tmp_path, monkeypatch):
    """번들 드라이버 1개와, 호출 흔적을 남기는 가짜 webdriver.Edge를 깔아준다."""
    bundled = tmp_path / "msedgedriver.exe"
    bundled.write_bytes(b"stub")
    monkeypatch.setattr(svc, "_edge_driver_candidates", lambda: [bundled])
    monkeypatch.setattr(svc, "_driver_cache_dir", lambda: tmp_path / "cache")

    calls = []

    def _fake_edge(options=None, service=None):
        calls.append(service.path if service else "selenium-manager")
        return "driver"

    monkeypatch.setattr(webdriver, "Edge", _fake_edge)
    return bundled, calls


class TestMakeEdgeDriver:
    def test_uses_bundled_driver_when_version_matches(self, edge_env, monkeypatch):
        bundled, calls = edge_env
        monkeypatch.setattr(svc, "_installed_edge_major", lambda: 142)
        monkeypatch.setattr(svc, "_exe_version", lambda p: "Microsoft Edge WebDriver 142.0.1.2")

        assert svc._make_edge_driver(object(), lambda m: None) == "driver"
        assert calls == [str(bundled)]

    def test_falls_back_when_bundled_driver_too_old(self, edge_env, monkeypatch):
        _, calls = edge_env
        monkeypatch.setattr(svc, "_installed_edge_major", lambda: 142)
        monkeypatch.setattr(svc, "_exe_version", lambda p: "Microsoft Edge WebDriver 138.0.1.2")

        assert svc._make_edge_driver(object(), lambda m: None) == "driver"
        assert calls == ["selenium-manager"]  # 번들을 건너뛰고 자동 다운로드로 감

    def test_falls_back_when_bundled_driver_too_new(self, edge_env, monkeypatch):
        _, calls = edge_env
        monkeypatch.setattr(svc, "_installed_edge_major", lambda: 138)
        monkeypatch.setattr(svc, "_exe_version", lambda p: "Microsoft Edge WebDriver 142.0.1.2")

        svc._make_edge_driver(object(), lambda m: None)
        assert calls == ["selenium-manager"]

    def test_error_message_guides_manual_install(self, edge_env, monkeypatch):
        monkeypatch.setattr(svc, "_installed_edge_major", lambda: 142)
        monkeypatch.setattr(svc, "_exe_version", lambda p: "138.0.1.2")

        def _boom(options=None, service=None):
            raise RuntimeError("session not created")

        monkeypatch.setattr(webdriver, "Edge", _boom)

        with pytest.raises(RuntimeError) as err:
            svc._make_edge_driver(object(), lambda m: None)

        message = str(err.value)
        assert "설치된 엣지 버전: 142" in message
        assert "msedgedriver.exe" in message
        assert svc._EDGE_DRIVER_DOWNLOAD in message

    def test_unknown_edge_version_still_tries_bundled(self, edge_env, monkeypatch):
        bundled, calls = edge_env
        monkeypatch.setattr(svc, "_installed_edge_major", lambda: None)
        monkeypatch.setattr(svc, "_exe_version", lambda p: "")

        svc._make_edge_driver(object(), lambda m: None)
        assert calls == [str(bundled)]
