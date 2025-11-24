#!/usr/bin/env python3
# src/app/application.py
from __future__ import annotations

from typing import Optional, Iterable
from PyQt5.QtWidgets import QProxyStyle, QStyle, QApplication

from .helper import Helper
from .configuration import Configuration
from .log import Log
from .ui import MsgBox
import os
import subprocess

class NoFocusRectStyle(QProxyStyle):
    def drawPrimitive(self, element, option, painter, widget=None):
        if element == QStyle.PE_FrameFocusRect:
            return  # skip drawing the focus rect completely
        super().drawPrimitive(element, option, painter, widget)

class Application(QApplication):

    def __init__(self, name: Optional[str] = None, argv=None):

        # Initialize QApplication
        super().__init__(argv or [])

        # Application name
        if name:
            self.setApplicationName(name)

        # Set application style
        self.setStyle('Fusion')

        # Use custom style to suppress focus rectangles
        self.setStyle(NoFocusRectStyle(self.style()))

        # Main window placeholder (e.g. Client)
        self._mainWindow = None

        # Helper
        self._helper = Helper()

        # Configuration manager
        self._configuration = Configuration()
        self._configuration.configChanged.connect(self.reset)

        # Default configuration entries
        self._configuration.add("administration.update", None, "button", label="Check for Updates", action=self.update)
        self._configuration.add("administration.import", None, "button", label="Import Configuration", action=self._configuration.import_cfg)
        self._configuration.add("administration.export", None, "button", label="Export Configuration", action=self._configuration.export_cfg)

        # Save any new defaults
        self._configuration.save()

        # Logger
        self._logger = Log()

        # Initial stylesheet load
        self._loadStylesheet()

    # ------------------------------------------------------------------
    # Properties / accessors
    # ------------------------------------------------------------------

    @property
    def helper(self) -> Helper:
        return self._helper

    @property
    def logger(self) -> Log:
        return self._logger

    @property
    def configuration(self) -> Configuration:
        return self._configuration

    @property
    def mainWindow(self):
        return self._mainWindow

    @property
    def name(self) -> str:
        return self.applicationName()

    # ------------------------------------------------------------------
    # Main window management
    # ------------------------------------------------------------------

    def set_mainWindow(self, window):
        self._mainWindow = window
        self._loadStylesheet()
        self._mainWindow.show()

    # ------------------------------------------------------------------
    # Stylesheet handling
    # ------------------------------------------------------------------

    def _loadStylesheet(self):

        # Base stylesheet (e.g. styles/style.css)
        base_css = self._helper.load_stylesheet("styles/style.css")  # you can implement this in Helper

        # Retrieve icon paths
        check_svg = self._helper.get_path("icons/check.svg")
        chevron_up_svg = self._helper.get_path("icons/chevron-up.svg")
        chevron_down_svg = self._helper.get_path("icons/chevron-down.svg")
        chevron_expand_svg = self._helper.get_path("icons/chevron-expand.svg")

        # Override styles
        override = (
            "\n"
            "QCheckBox::indicator:checked { "
            f"image: {self._helper.qss_url(check_svg)};"
            " }\n"
            "QComboBox::down-arrow { "
            f"image: {self._helper.qss_url(chevron_expand_svg)};"
            " }\n"
            "QSpinBox::up-arrow { "
            f"image: {self._helper.qss_url(chevron_up_svg)};"
            " }\n"
            "QSpinBox::down-arrow { "
            f"image: {self._helper.qss_url(chevron_down_svg)};"
            " }\n"
        )

        # Start with base + global overrides
        css = (base_css or "") + override

        # If main window has its own override, append it
        if self._mainWindow and hasattr(self._mainWindow, "override"):
            css += self._mainWindow.override()

        # Apply combined stylesheet
        self.setStyleSheet(css)

    # ------------------------------------------------------------------
    # UI reset on configuration change
    # ------------------------------------------------------------------

    def reset(self):

        # Do nothing if no main window
        if not self._mainWindow:
            return

        # Call main window reset if available
        if hasattr(self._mainWindow, 'reset'):
            self._loadStylesheet()
            self._mainWindow.reset()

    # ------------------------------------------------------------------
    # System Helpers
    # ------------------------------------------------------------------

    def _run_system_command(self, args: list[str]) -> None:
        # Only attempt on Linux; ignore silently on other platforms
        try:
            os_name = self._helper.get_os()
        except Exception:
            os_name = None

        if os_name != "linux":
            if self._logger:
                self._logger.append(
                    f"[Application] Ignoring system command {args!r} on non-Linux OS: {os_name}",
                    channel="system",
                    level="warning",
                )
            return

        try:
            # Use Popen so we don't block the UI; systemd will take over.
            subprocess.Popen(args)
            if self._logger:
                self._logger.append(
                    f"[Application] Executed system command: {' '.join(args)}",
                    channel="system",
                    level="info",
                )
        except Exception as e:
            if self._logger:
                self._logger.append(
                    f"[Application] Failed to execute system command {args!r}: {e}",
                    channel="system",
                    level="error",
                )

    def shutdown(self) -> None:
        self._run_system_command(["systemctl", "poweroff"])

    def restart(self) -> None:
        self._run_system_command(["systemctl", "reboot"])

    # ------------------------------------------------------------------
    # Application Helpers
    # ------------------------------------------------------------------

    def update(self):
        # Determine repo root based on this file location
        try:
            here = os.path.abspath(os.path.dirname(__file__))
            repo_root = os.path.abspath(os.path.join(here, "..", ".."))
        except Exception as e:
            if self._logger:
                self._logger.append(
                    f"[Application] Failed to determine repository root for update: {e}",
                    channel="system",
                    level="error",
                )
            return

        # Delegate to the generic system command runner so we inherit logging and OS checks
        self._run_system_command(["sudo", "git", "-C", repo_root, "pull"])

        # Notify user to restart application
        buttons: Iterable[str] = ("Exit", "OK")
        choice = MsgBox.show(
            parent=self._mainWindow,
            title="Update Successful",
            message="The application has been updated. Please restart the application to apply the latest changes.",
            icon="info",
            buttons=buttons,
            default="OK",
            icon_lookup_fn=self._helper.get_path,
        )

        if choice == "Exit":
            self.quit()
