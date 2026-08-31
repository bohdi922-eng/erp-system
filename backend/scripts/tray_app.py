"""Runs ERP System as a standalone app: no visible terminal window, just
an icon in the system tray (bottom-right, near the clock) with "Open" and
"Close" options.

Launched via pythonw.exe (not python.exe) by setup.bat, which is what
actually removes the terminal window — pythonw.exe never opens a console
in the first place. This script is otherwise just a normal Python script.

Since pythonw.exe has no console to print to, all output is redirected to
server.log next to this file — check that if the app doesn't seem to
start (icon never appears, browser never opens).
"""
from __future__ import annotations

import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
LOG_PATH = BACKEND_DIR / "server.log"

# pythonw.exe has no stdout/stderr to write to — redirect to a file so
# errors are visible SOMEWHERE instead of vanishing silently.
_log_file = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
sys.stdout = _log_file
sys.stderr = _log_file

import pystray  # noqa: E402
import uvicorn  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

APP_URL = "http://127.0.0.1:8000"
HOST, PORT = "127.0.0.1", 8000


def _is_already_running() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((HOST, PORT)) == 0


def _make_icon_image() -> Image.Image:
    # A small generated icon — no external asset file needed. Brand blue
    # circle with a white "E" (for "ERP"), matching the app's primary color.
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((2, 2, 62, 62), fill=(0, 87, 168, 255))
    draw.text((22, 16), "E", fill=(255, 255, 255, 255))
    return img


def _open_browser(icon=None, item=None) -> None:
    webbrowser.open(APP_URL)


def _quit_app(icon, item) -> None:
    print("Shutting down (tray menu -> close).")
    icon.stop()
    # uvicorn is running in the main thread and there's no clean async
    # handle to cancel it from here — a hard exit is fine for a local
    # SQLite-backed app with no external processes to clean up.
    import os
    os._exit(0)


def run() -> None:
    print(f"--- starting at {time.strftime('%Y-%m-%d %H:%M:%S')} ---")

    if _is_already_running():
        print("Already running — just opening the browser.")
        _open_browser()
        return

    menu = pystray.Menu(
        pystray.MenuItem("فتح البرنامج", _open_browser, default=True),
        pystray.MenuItem("إغلاق البرنامج", _quit_app),
    )
    icon = pystray.Icon("erp_system", _make_icon_image(), "ERP System", menu)
    icon.run_detached()  # tray icon lives on its own thread

    threading.Timer(1.5, _open_browser).start()

    try:
        uvicorn.run("app.main:app", host=HOST, port=PORT, log_level="warning")
    except Exception:
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    run()
