"""PySide6 desktop shell for Prism.

Python owns the desktop window, local HTTP server, AI proxy, lifecycle and
fullscreen menu. The rendered workspace is the same local web UI, loaded in
Qt WebEngine so the visualizations remain pixel-identical.
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from python_app.server import start_server, stop_server

APP_TITLE = "Prism — code analysis workspace"
_MUTEX_HANDLE = None


def resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def acquire_single_instance() -> bool:
    global _MUTEX_HANDLE
    if os.name != "nt":
        return True
    kernel32 = ctypes.windll.kernel32
    _MUTEX_HANDLE = kernel32.CreateMutexW(None, False, "Local\\PrismPythonDesktop")
    return kernel32.GetLastError() != 183


def storage_root() -> Path:
    executable_dir = Path(sys.executable).resolve().parent
    if (executable_dir / "portable.flag").exists():
        return executable_dir / "PrismData"
    local = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Prism"
    return local / "WebEngine"


class PrismWindow(QMainWindow):
    def __init__(self, url: str, icon_path: Path):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1440, 920)
        self.setMinimumSize(960, 680)
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        profile = QWebEngineProfile.defaultProfile()
        storage = storage_root()
        storage.mkdir(parents=True, exist_ok=True)
        profile.setPersistentStoragePath(str(storage / "storage"))
        profile.setCachePath(str(storage / "cache"))
        profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)

        self.view = QWebEngineView(self)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
        settings = self.view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        self.view.setUrl(QUrl(url))
        self.setCentralWidget(self.view)

        self.fullscreen_action = QAction("Toggle full screen", self)
        self.fullscreen_action.setShortcut(QKeySequence("F11"))
        self.fullscreen_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self.fullscreen_action.triggered.connect(self.toggle_fullscreen)
        self.addAction(self.fullscreen_action)

        reload_action = QAction("Reload", self)
        reload_action.setShortcut(QKeySequence.StandardKey.Refresh)
        reload_action.triggered.connect(self.view.reload)
        self.addAction(reload_action)

        menu = self.menuBar()
        view_menu = menu.addMenu("&View")
        view_menu.addAction(self.fullscreen_action)
        view_menu.addAction(reload_action)
        window_menu = menu.addMenu("&Window")
        minimize_action = QAction("Minimize", self)
        minimize_action.triggered.connect(self.showMinimized)
        window_menu.addAction(minimize_action)
        close_action = QAction("Close", self)
        close_action.setShortcut(QKeySequence.StandardKey.Close)
        close_action.triggered.connect(self.close)
        window_menu.addAction(close_action)
        help_menu = menu.addMenu("&Help")
        about_action = QAction("About Prism", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        self._is_fullscreen = False

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            "About Prism",
            "Prism 1.0.0\n\nA local-first code analysis workspace.\n"
            "Python desktop shell, local server, and AI proxy.\n"
            "The analysis and diagram views run locally in Qt WebEngine.",
        )

    def keyPressEvent(self, event):  # keep F11 reliable with WebEngine focus
        if event.key() == Qt.Key.Key_F11:
            self.toggle_fullscreen()
            event.accept()
            return
        super().keyPressEvent(event)


def hide_console() -> None:
    """Use the console bootloader for reliability, but hide its window."""
    if getattr(sys, "frozen", False) and os.name == "nt":
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)


def configure_webengine(root: Path) -> None:
    """Point Qt WebEngine at the bundled runtime and use the portable GL path."""
    frozen = getattr(sys, "frozen", False)
    portable_runtime = root / "runtime" / "Lib" / "site-packages" / "PySide6"
    if frozen or (root / "portable.flag").exists():
        qt = root / "PySide6" if frozen else portable_runtime
        os.environ.setdefault("QTWEBENGINE_RESOURCES_PATH", str(qt / "resources"))
        os.environ.setdefault("QTWEBENGINE_LOCALES_PATH", str(qt / "translations" / "qtwebengine_locales"))
        os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
        flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        for flag in ("--single-process", "--disable-gpu", "--no-sandbox"):
            if flag not in flags:
                flags = f"{flags} {flag}".strip()
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = flags
    else:
        os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-features=Translate")


def main() -> int:
    hide_console()
    if not acquire_single_instance():
        return 0
    root = resource_root()
    configure_webengine(root)
    server, url = start_server(root)
    icon_path = root / "assets" / "icon.ico"
    app = QApplication(sys.argv)
    app.setApplicationName("Prism")
    app.setApplicationDisplayName("Prism")
    window = PrismWindow(url, icon_path)
    if "--fullscreen" in sys.argv:
        window.showFullScreen()
    else:
        window.show()
    try:
        return app.exec()
    finally:
        stop_server(server)


if __name__ == "__main__":
    raise SystemExit(main())
