"""Desktop-launcher tests by Bouronikos Christos <chrisbouronikos@gmail.com>.

Support MathOCR at https://paypal.me/christosbouronikos. These checks do not
open a GUI or load OCR models, so they are safe in local and GitHub CI runs.
"""

import json
from urllib.parse import parse_qs, urlparse

from desktop import main as desktop_main
from desktop.main import (
    acquire_instance_lock,
    check_single_instance,
    desktop_url,
    find_available_port,
    lock_file_path,
    release_instance_lock,
    show_error_dialog,
)


def test_desktop_url_points_frontend_to_its_private_api() -> None:
    url = desktop_url(43210)
    parsed = urlparse(url)
    assert parsed.scheme == "http"
    assert parsed.netloc == "127.0.0.1:43210"
    assert parse_qs(parsed.query) == {
        "desktop": ["1"],
        "api": ["http://127.0.0.1:43210"],
    }


def test_find_available_port_returns_a_user_port(monkeypatch) -> None:
    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def bind(self, address):
            assert address == ("127.0.0.1", 0)

        def getsockname(self):
            return ("127.0.0.1", 43210)

    monkeypatch.setattr(desktop_main.socket, "socket", lambda *_args: FakeSocket())
    port = find_available_port()
    assert port == 43210


def test_single_instance_detection_when_active(monkeypatch, tmp_path) -> None:
    lock_file = tmp_path / "mathocr.lock"
    monkeypatch.setattr(desktop_main, "lock_file_path", lambda: lock_file)

    lock_file.write_text(json.dumps({"pid": 99999, "port": 45678}), encoding="utf-8")

    # Mock is_service_healthy returning True
    monkeypatch.setattr(desktop_main, "is_service_healthy", lambda port, timeout=1.0: True)

    opened = []
    monkeypatch.setattr(desktop_main.webbrowser, "open", lambda url: opened.append(url))

    allowed = check_single_instance()
    assert allowed is False
    assert len(opened) == 1
    assert "45678" in opened[0]


def test_single_instance_cleans_stale_lock(monkeypatch, tmp_path) -> None:
    lock_file = tmp_path / "mathocr.lock"
    monkeypatch.setattr(desktop_main, "lock_file_path", lambda: lock_file)

    lock_file.write_text(json.dumps({"pid": 99999, "port": 45678}), encoding="utf-8")

    # Mock is_service_healthy returning False (dead/stale process)
    monkeypatch.setattr(desktop_main, "is_service_healthy", lambda port, timeout=1.0: False)

    allowed = check_single_instance()
    assert allowed is True
    assert not lock_file.exists()


def test_acquire_and_release_lock(monkeypatch, tmp_path) -> None:
    lock_file = tmp_path / "mathocr.lock"
    monkeypatch.setattr(desktop_main, "lock_file_path", lambda: lock_file)

    acquire_instance_lock(54321)
    assert lock_file.is_file()
    data = json.loads(lock_file.read_text(encoding="utf-8"))
    assert data["port"] == 54321

    release_instance_lock()
    assert not lock_file.exists()


def test_show_error_dialog_fallback(monkeypatch, capsys) -> None:
    # Ensure show_error_dialog falls back to stderr when GUI libraries fail
    monkeypatch.setattr(desktop_main.sys, "platform", "linux")
    monkeypatch.setitem(desktop_main.sys.modules, "tkinter", None)
    show_error_dialog("Test Title", "Test Message")
    captured = capsys.readouterr()
    assert "Test Title" in captured.err or "Test Message" in captured.err
