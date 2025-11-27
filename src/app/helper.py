#!/usr/bin/env python3
# src/app/helper.py
import os
import sys
import platform
import subprocess

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

class Helper:
    """
    Small collection of cross-app helpers.
    """

    def __init__(self, root_dir: str | None = None, script_dir: str | None = None):
        if script_dir is None:
            if getattr(sys, "frozen", False):
                script_dir = os.path.dirname(sys.executable)
            else:
                script_dir = os.path.dirname(os.path.abspath(__file__))
        self.script_dir = script_dir

        if root_dir is None:
            # If we are in .../src/app, root_dir should be project root (two levels up).
            base = os.path.dirname(self.script_dir)  # e.g. .../src
            parent = os.path.dirname(base)           # e.g. project_root
            self.root_dir = parent
        else:
            self.root_dir = root_dir

    # ---------- OS / paths ----------

    def get_path(self, rel_path: str) -> str | None:
        rel = rel_path.replace("\\", "/")

        # 1) PyInstaller onefile temp dir
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            p = os.path.join(meipass, rel)
            if os.path.exists(p):
                return p

        # 2) Next to the frozen exe
        if getattr(sys, "frozen", False):
            p = os.path.join(self.script_dir, rel)
            if os.path.exists(p):
                return p

        # 3) macOS .app Resources
        res = os.path.join(self.root_dir, "Resources", rel)
        if os.path.exists(res):
            return res

        # 4) repo src/
        src = os.path.join(self.root_dir, "src", rel)
        if os.path.exists(src):
            return src

        print(f"[Helper] Could not find resource: {rel}")
        return None

    @staticmethod
    def get_os() -> str:
        name = platform.system()
        if name == "Darwin":
            return "macos"
        if name == "Linux":
            return "linux"
        if name == "Windows":
            return "windows"
        return "unknown"

    @staticmethod
    def get_arch() -> str:
        arch = platform.machine().lower()
        if arch in ("x86_64", "amd64"):
            return "x86_64"
        if arch in ("aarch64", "arm64"):
            return "arm64"
        if arch in ("i386", "i686", "x86", "i86pc"):
            return "x86"
        if arch in ("armv7l", "armv8l", "arm"):
            return "armhf"
        return "unknown"

    @staticmethod
    def get_screen_resolution() -> tuple[int, int]:
        app = QApplication.instance()
        if not app:
            return (0, 0)
        screen = app.primaryScreen()
        size = screen.size()
        return (size.width(), size.height())

    @staticmethod
    def file_exists(path: str | None) -> bool:
        return bool(path) and os.path.isfile(path)

    @staticmethod
    def dir_exists(path: str | None) -> bool:
        return bool(path) and os.path.isdir(path)

    @staticmethod
    def join(*paths: str) -> str:
        return os.path.join(*paths)

    @staticmethod
    def qss_url(p: str | None) -> str:
        """
        Return a url("...") QSS literal, or url("") for None.
        """
        if not p:
            return 'url("")'
        return f'url("{p.replace(os.sep, "/")}")'

    @staticmethod
    def run(cmd):
        try:
            p = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=6
            )
            return p.returncode, (p.stdout or "").strip()
        except Exception as e:
            return 1, f"{type(e).__name__}: {e}"

    # ---------- StyleSheet Handling ----------
    def load_stylesheet(self, rel_path: str) -> str | None:
        """
        Load a stylesheet from a relative path.
        """
        p = self.get_path(rel_path)
        if not p:
            return None
        try:
            with open(p, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"[Helper] Failed to load stylesheet {rel_path}: {e}")
            return None
