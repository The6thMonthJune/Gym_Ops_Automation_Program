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
    """is_displayed/clear/send_keys/click만 흉내내는 최소 엘리먼트."""

    def __init__(self, text="", attrs=None, displayed=True, clickable=True):
        self.text = text
        self._attrs = attrs or {}
        self._displayed = displayed
        self._clickable = clickable
        self.clicked = False
        self.typed = ""

    def is_displayed(self):
        return self._displayed

    def get_attribute(self, name):
        return self._attrs.get(name)

    def clear(self):
        self.typed = ""

    def send_keys(self, value):
        self.typed += str(value)

    def click(self):
        if not self._clickable:
            raise RuntimeError("가려져 있어 클릭할 수 없음")
        self.clicked = True


class _FakeDriver:
    """XPath/태그 조회에 미리 정한 결과를 돌려주는 최소 드라이버.

    on_click이 주어지면 그 클릭 이후부터 조회 결과가 after 테이블로 바뀐다.
    (로그인 버튼을 눌러야 모달 입력란이 생기는 상황을 흉내낸다)
    """

    def __init__(self, before, after=None, url="https://crm.broj.co.kr/", title="BROJ CRM"):
        self._tables = [before] if after is None else [before, after]
        self.current_url = url
        self.title = title
        self.switch_to = self

    @property
    def _table(self):
        return self._tables[0]

    def advance(self):
        if len(self._tables) > 1:
            self._tables.pop(0)

    def find_elements(self, by, locator):
        return self._table.get(locator, [])

    # switch_to 인터페이스
    def frame(self, _frame):
        raise RuntimeError("iframe 없음")

    def default_content(self):
        pass


_PW = svc._PASSWORD_XPATH


class TestOpenLoginForm:
    """브로제이는 공개 API가 없어 DOM에 의존한다 — id가 바뀌어도 버텨야 한다."""

    def test_does_nothing_when_form_already_shown(self):
        driver = _FakeDriver({_PW: [_FakeElement(attrs={"type": "password"})]})
        svc._open_login_form(driver, None, lambda m: None)  # 예외 없이 끝나면 통과

    def test_clicks_login_button_then_waits_for_modal(self):
        button = _FakeElement("로그인")
        password = _FakeElement(attrs={"type": "password"})
        before = {"//button[contains(., '로그인')]": [button], _PW: [], "iframe": []}
        driver = _FakeDriver(before, after={_PW: [password]})
        button.click = lambda: (driver.advance(), setattr(button, "clicked", True))[1]

        svc._open_login_form(driver, None, lambda m: None)

        assert button.clicked

    def test_raises_when_no_password_field_appears(self):
        driver = _FakeDriver({_PW: [], "iframe": []})
        with pytest.raises(RuntimeError, match="비밀번호 칸"):
            svc._open_login_form(driver, None, lambda m: None)


class TestSubmitLogin:
    def _driver(self, submit_xpath="//button[@type='submit']"):
        self.id_input = _FakeElement(attrs={"type": "text", "id": "userId"})
        self.password = _FakeElement(attrs={"type": "password"})
        self.submit = _FakeElement("로그인")
        return _FakeDriver({
            _PW: [self.password],
            "//input[@type='text' or @type='email' or @type='tel' or not(@type)]": [self.id_input],
            submit_xpath: [self.submit],
            "iframe": [],
        })

    def test_fills_fields_found_by_structure_not_id(self):
        driver = self._driver()

        svc._submit_login(driver, "myid", "mypw", lambda m: None)

        assert self.id_input.typed == "myid"      # id가 login_id가 아니어도 찾는다
        assert self.password.typed == "mypw"
        assert self.submit.clicked

    def test_falls_back_to_enter_when_no_submit_button(self):
        driver = self._driver(submit_xpath="//없는태그")

        svc._submit_login(driver, "myid", "mypw", lambda m: None)

        assert self.password.typed.startswith("mypw")
        assert len(self.password.typed) > len("mypw")  # 엔터 키가 덧붙음

    def test_raises_when_id_field_missing(self):
        driver = _FakeDriver({_PW: [_FakeElement(attrs={"type": "password"})], "iframe": []})
        with pytest.raises(RuntimeError, match="아이디 입력란"):
            svc._submit_login(driver, "myid", "mypw", lambda m: None)


class TestLoginHelpText:
    def test_includes_page_state_for_remote_diagnosis(self):
        driver = _FakeDriver({
            "//button | //a | //input[@type='submit']": [
                _FakeElement("로그인"), _FakeElement("", attrs={"value": "이용가이드"}),
            ],
            "input": [_FakeElement(attrs={"id": "userId", "type": "text", "placeholder": "아이디"})],
        }, url="https://crm.broj.co.kr/", title="BROJ CRM")

        message = svc._login_help_text(driver, RuntimeError("timeout"))

        assert "https://crm.broj.co.kr/" in message
        assert "BROJ CRM" in message
        assert "로그인" in message
        assert "이용가이드" in message        # value 속성만 있는 버튼도 수집
        assert "id=userId" in message         # 입력란 정보로 다음 수정 지점을 알 수 있다
        assert "timeout" in message
