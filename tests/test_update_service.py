import pytest

from src.services import update_service
from src.services.update_service import ReleaseInfo, is_newer, parse_version

_PAYLOAD = {
    "tag_name": "v3.2.0",
    "html_url": "https://github.com/owner/repo/releases/tag/v3.2.0",
    "body": "- 버그 수정",
    "assets": [
        {"name": "GymOps.exe", "browser_download_url": "https://x/GymOps.exe", "size": 100},
        {"name": "다른파일.zip", "browser_download_url": "https://x/other.zip", "size": 5},
    ],
}


class TestParseVersion:
    def test_strips_v_prefix(self):
        assert parse_version("v3.0.11") == (3, 0, 11)

    def test_plain(self):
        assert parse_version("3.1.0") == (3, 1, 0)

    def test_non_numeric_chunk_becomes_zero(self):
        assert parse_version("v3.1.0-beta") == (3, 1, 0)


class TestIsNewer:
    @pytest.mark.parametrize(
        ("latest", "current", "expected"),
        [
            ("3.1.0", "3.0.11", True),
            ("3.0.12", "3.0.11", True),
            ("3.0.11", "3.0.11", False),
            ("3.0.9", "3.0.11", False),   # 문자열 비교였다면 틀렸을 조합
            ("3.1", "3.0.11", True),      # 자릿수가 달라도 비교된다
            ("3.0", "3.0.0", False),
        ],
    )
    def test_compare(self, latest, current, expected):
        assert is_newer(latest, current) is expected


class TestFetchLatestRelease:
    def _patch_api(self, monkeypatch, payload):
        class _Response:
            def json(self):
                return payload

            def raise_for_status(self):
                return None

        monkeypatch.setattr(update_service.requests, "get", lambda *a, **k: _Response())

    def test_picks_exe_asset(self, monkeypatch):
        self._patch_api(monkeypatch, _PAYLOAD)
        release = update_service.fetch_latest_release()
        assert release == ReleaseInfo(
            version="3.2.0",
            download_url="https://x/GymOps.exe",
            size=100,
            notes="- 버그 수정",
            page_url="https://github.com/owner/repo/releases/tag/v3.2.0",
        )

    def test_none_when_exe_missing(self, monkeypatch):
        self._patch_api(monkeypatch, {**_PAYLOAD, "assets": [{"name": "x.zip"}]})
        assert update_service.fetch_latest_release() is None

    def test_check_swallows_network_error(self, monkeypatch):
        def _boom(*a, **k):
            raise OSError("네트워크 없음")

        monkeypatch.setattr(update_service.requests, "get", _boom)
        assert update_service.check_for_update() is None


class TestApplyUpdate:
    def test_swaps_exe_and_keeps_backup(self, tmp_path, monkeypatch):
        exe = tmp_path / "GymOps.exe"
        exe.write_bytes(b"old")
        new_exe = tmp_path / "GymOps.exe.download"
        new_exe.write_bytes(b"new")
        monkeypatch.setattr(update_service, "current_exe", lambda: exe)

        result = update_service.apply_update(new_exe)

        assert result == exe
        assert exe.read_bytes() == b"new"
        assert (tmp_path / "GymOps.exe.old").read_bytes() == b"old"
        assert not new_exe.exists()

    def test_rolls_back_when_replace_fails(self, tmp_path, monkeypatch):
        exe = tmp_path / "GymOps.exe"
        exe.write_bytes(b"old")
        monkeypatch.setattr(update_service, "current_exe", lambda: exe)

        with pytest.raises(Exception):
            update_service.apply_update(tmp_path / "없는파일.exe")

        assert exe.read_bytes() == b"old"  # 교체에 실패해도 기존 EXE는 살아 있다
        assert not (tmp_path / "GymOps.exe.old").exists()
