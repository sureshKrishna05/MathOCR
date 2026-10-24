"""Zero-install desktop launcher for MathOCR.

Created by Bouronikos Christos <chrisbouronikos@gmail.com>.
Support MathOCR at https://paypal.me/christosbouronikos.

PyInstaller freezes this module, Python, the OCR dependencies, and frontend
assets into a platform-specific application. At launch it starts the existing
FastAPI app on a private random loopback port and opens it in a native pywebview
window (or falls back to the default browser if pywebview/WebView2 is unavailable).
The end user never needs to see Python, a terminal, or a browser tab.
"""

from __future__ import annotations

import atexit
import json
import logging
import multiprocessing
import os
import shutil
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn

from backend.app import APP_ROOT, app
from backend.model_store import default_cache_root

HOST = "127.0.0.1"
logger = logging.getLogger("mathocr.desktop")


def lock_file_path() -> Path:
    """Return the location of the single-instance lockfile."""
    return default_cache_root().parent / "mathocr.lock"


def find_available_port(host: str = HOST) -> int:
    """Ask the operating system for an unused loopback TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((host, 0))
        return int(listener.getsockname()[1])


def desktop_url(port: int) -> str:
    """Build the UI URL and tell JavaScript which private API origin to use."""
    origin = f"http://{HOST}:{port}"
    query = urllib.parse.urlencode({"desktop": "1", "api": origin})
    return f"{origin}/?{query}"


def is_service_healthy(port: int, timeout: float = 1.0) -> bool:
    """Check if a running MathOCR backend responds with HTTP 200 on /api/health."""
    health_url = f"http://{HOST}:{port}/api/health"
    try:
        req = urllib.request.Request(health_url, headers={"User-Agent": "MathOCR-Launcher"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def wait_until_ready(port: int, timeout: float = 30.0) -> None:
    """Wait for Uvicorn to accept requests before creating the native window."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_service_healthy(port, timeout=0.5):
            return
        time.sleep(0.1)
    raise RuntimeError("The local MathOCR engine did not start in time")


def show_error_dialog(title: str, message: str) -> None:
    """Display a user-friendly error dialog box for fatal desktop errors."""
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, message, title, 0x10 | 0x0)  # MB_ICONERROR | MB_OK
            return
        except Exception:
            pass
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
        return
    except Exception:
        pass
    print(f"[{title}] {message}", file=sys.stderr)


def check_single_instance() -> bool:
    """Check if another MathOCR instance is already running.

    If an active instance is running, opens the browser to it and returns False
    to signal the caller to exit. If no instance is active (or a stale lock exists),
    removes any stale lock and returns True.
    """
    lock_file = lock_file_path()
    if lock_file.is_file():
        try:
            data = json.loads(lock_file.read_text(encoding="utf-8"))
            port = int(data.get("port", 0))
            if port > 0 and is_service_healthy(port, timeout=1.0):
                # An active instance exists: navigate user to it
                webbrowser.open(desktop_url(port))
                return False
        except Exception:
            pass
        # Stale lock: clean it up
        try:
            lock_file.unlink(missing_ok=True)
        except OSError:
            pass
    return True


def acquire_instance_lock(port: int) -> None:
    """Write current process ID and port to lockfile."""
    lock_file = lock_file_path()
    try:
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        lock_file.write_text(json.dumps({"pid": os.getpid(), "port": port}), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write lockfile %s: %s", lock_file, exc)


def release_instance_lock() -> None:
    """Remove single instance lockfile."""
    try:
        lock_file_path().unlink(missing_ok=True)
    except OSError:
        pass


def run_headless() -> None:
    """Serve the API without a window (MATHOCR_HEADLESS=1).

    Used to smoke-test the frozen application: recognition can be exercised
    with plain HTTP requests, which catches packaging bugs (missing data
    files, missing sources for TorchScript) that only appear when frozen.
    """
    port = int(os.getenv("MATHOCR_PORT", "8765"))
    uvicorn.run(app, host=HOST, port=port, log_level="info")


def run_desktop() -> None:
    """Start the local service, show the window (or browser), and stop cleanly on exit."""
    if not check_single_instance():
        print("MathOCR is already running. Opened the existing application window.")
        return

    port = find_available_port()
    acquire_instance_lock(port)
    atexit.register(release_instance_lock)

    config = uvicorn.Config(
        app,
        host=HOST,
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None
    server_thread = threading.Thread(target=server.run, name="mathocr-api", daemon=True)
    server_thread.start()

    try:
        try:
            wait_until_ready(port)
        except Exception as exc:
            log_dir = default_cache_root().parent / "logs"
            show_error_dialog(
                "MathOCR Startup Error",
                f"MathOCR could not start the background service:\n\n{exc}\n\n"
                f"Detailed logs are available at:\n{log_dir / 'mathocr.log'}",
            )
            return

        window_created = False
        try:
            import webview

            webview.create_window(
                "Qryptex — Bharathidasan University Math OCR",
                desktop_url(port),
                width=1180,
                height=860,
                min_size=(760, 620),
                background_color="#f8fafc",  # matches interface slate theme
                text_select=True,
            )
            window_created = True
            webview.start(debug=os.getenv("MATHOCR_DESKTOP_DEBUG") == "1")
        except Exception as gui_err:
            logger.warning("Native webview window failed (%s); falling back to default browser.", gui_err)
            webbrowser.open(desktop_url(port))
            # In browser fallback mode, keep the server running until interrupted
            try:
                while not server.should_exit:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                pass
    finally:
        server.should_exit = True
        server_thread.join(timeout=5)
        release_instance_lock()


def main() -> None:
    """Freeze-safe console entry point used by PyInstaller."""
    multiprocessing.freeze_support()
    # Anchor working directory to application root for path stability
    try:
        os.chdir(APP_ROOT)
    except OSError:
        pass

    if os.getenv("MATHOCR_HEADLESS") == "1":
        run_headless()
    else:
        run_desktop()


if __name__ == "__main__":
    main()
