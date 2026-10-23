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


class _FakeElement:
    def __init__(self, text="", value="", clickable=True):
        self.text = text
        self._value = value
        self._clickable = clickable
        self.clicked = False

    def get_attribute(self, name):
        return self._value if name == "value" else None

    def click(self):
        if not self._clickable:
            raise RuntimeError("가려져 있어 클릭할 수 없음")
        self.clicked = True


class _FakeDriver:
    """XPath/ID 조회에 미리 정한 결과를 돌려주는 최소 드라이버."""

    def __init__(self, by_id=None, by_xpath=None, url="https://crm.broj.co.kr", title="브로제이"):
        self._by_id = by_id or {}
        self._by_xpath = by_xpath or {}
        self.current_url = url
        self.title = title

    def find_elements(self, by, locator):
        table = self._by_id if by == "id" else self._by_xpath
        return table.get(locator, [])


class TestOpenLoginForm:
    """브로제이는 공개 API가 없어 DOM에 의존한다 — 마크업이 바뀌어도 버텨야 한다."""

    def test_does_nothing_when_form_already_shown(self):
        driver = _FakeDriver(by_id={"login_id": [_FakeElement()]})
        svc._open_login_form(driver, None, lambda m: None)  # 예외 없이 끝나면 통과

    def test_clicks_button_with_nested_text(self, monkeypatch):
        # <button><span>로그인 페이지</span></button> 는 text()로는 안 잡히고 . 으로만 잡힌다
        button = _FakeElement("로그인 페이지")
        driver = _FakeDriver(
            by_id={"login_id": []},
            by_xpath={"//button[contains(., '로그인 페이지')]": [button]},
        )
        import selenium.webdriver.support.ui as ui

        monkeypatch.setattr(ui, "WebDriverWait", lambda *a, **k: type("W", (), {"until": lambda s, c: True})())
        svc._open_login_form(driver, None, lambda m: None)

        assert button.clicked

    def test_falls_through_to_looser_selector(self, monkeypatch):
        button = _FakeElement("로그인")
        driver = _FakeDriver(
            by_id={"login_id": []},
            by_xpath={"//button[contains(., '로그인')]": [button]},
        )
        import selenium.webdriver.support.ui as ui

        monkeypatch.setattr(ui, "WebDriverWait", lambda *a, **k: type("W", (), {"until": lambda s, c: True})())
        svc._open_login_form(driver, None, lambda m: None)

        assert button.clicked


class TestLoginHelpText:
    def test_includes_page_state_for_remote_diagnosis(self):
        driver = _FakeDriver(
            by_xpath={"//button | //a | //input[@type='submit']": [
                _FakeElement("회원가입"), _FakeElement("", value="시작하기"),
            ]},
            url="https://crm.broj.co.kr/intro",
            title="브로제이 CRM",
        )

        message = svc._login_help_text(driver, RuntimeError("timeout"))

        assert "https://crm.broj.co.kr/intro" in message
        assert "브로제이 CRM" in message
        assert "회원가입" in message
        assert "시작하기" in message      # value 속성만 있는 버튼도 수집
        assert "timeout" in message
