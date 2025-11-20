#!/usr/bin/env python3
# src/app/application.py
from __future__ import annotations

from PyQt5.QtWidgets import QProxyStyle, QStyle, QApplication

from .helper import Helper
from .configuration import Configuration
from .log import Log

class NoFocusRectStyle(QProxyStyle):
    def drawPrimitive(self, element, option, painter, widget=None):
        if element == QStyle.PE_FrameFocusRect:
            return  # skip drawing the focus rect completely
        super().drawPrimitive(element, option, painter, widget)

class Application(QApplication):

    def __init__(self, argv=None):

        # Initialize QApplication
        super().__init__(argv or [])

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
