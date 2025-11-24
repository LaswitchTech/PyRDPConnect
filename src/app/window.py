#!/usr/bin/env python3
# src/app/window.py
import base64
from typing import Optional, TYPE_CHECKING

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QGridLayout, QLabel, QLineEdit,
    QHBoxLayout, QFormLayout, QSpinBox, QComboBox, QCheckBox,
    QApplication,
)
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import Qt

from app.helper import Helper
from app.configuration import Configuration
from app.log import Log


if TYPE_CHECKING:
    # For type hints only, avoids circular import at runtime
    from app.application import Application

class Window(QMainWindow):
    """
    Main application window placeholder.
    """

    def __init__(
        self,
        helper: Optional[Helper] = None,
        configuration: Optional[Configuration] = None,
        logger: Optional[Log] = None,
    ):
        # Initialize parent
        super().__init__()

        # Retrieve the application instance
        self._app: Application = QApplication.instance()

        # Ensure Client is created after Application
        if self._app is None:
            raise RuntimeError("Client must be created after QApplication/Application.")

        # --- auto-wire from QApplication if not provided ---
        if helper is None or configuration is None or logger is None:
            # narrow the type for linters / IDEs
            # no runtime import to avoid circular imports
            helper = helper or self._app.helper          # type: ignore[attr-defined]
            configuration = configuration or self._app.configuration  # type: ignore[attr-defined]
            logger = logger or self._app.logger          # type: ignore[attr-defined]

        # Helper
        self._helper: Helper = helper

        # Configuration
        self._configuration: Configuration = configuration
        # if(self._helper.get_os() == "linux"):
        #     self._configuration.label("network.wifi", "WiFi")
        #     self._configuration.add("network.wifi.ssid", None, "text", label="SSID")
        #     self._configuration.add("network.wifi.passphrase", None, "password")
        # self._configuration.label("network.wireguard", "WireGuard")
        # self._configuration.add("network.wireguard.file", None, "text", label="Config File")
        # self._configuration.add("network.wireguard.auto", False, "checkbox", label="Auto Connect")
        # self._configuration.add("customize.window.logo_file", None, "picture", label="Logo File")
        # self._configuration.add("customize.window.logo_position", "top-center", "select", label="Logo Position", choices=["top-left", "top-center", "top-right", "center-left", "center-center", "center-right", "bottom-left", "bottom-center", "bottom-right"])
        # self._configuration.add("customize.window.form_position", "center-center", "select", label="Form Position", choices=["top-left", "top-center", "top-right", "center-left", "center-center", "center-right", "bottom-left", "bottom-center", "bottom-right"])
        # self._configuration.add("customize.window.fullscreen", False, "checkbox")
        # self._configuration.add("customize.window.gradient_start", "#265162", "color", label="Gradient Start")
        # self._configuration.add("customize.window.gradient_end", "#002136", "color", label="Gradient End")
        # self._configuration.add("customize.controls.exit", False, "checkbox")
        # self._configuration.add("customize.controls.restart", False, "checkbox")
        # self._configuration.add("customize.controls.shutdown", False, "checkbox")
        # self._configuration.add("customize.controls.diagnostics", False, "checkbox")

        # Save any new defaults
        self._configuration.save()

        # Logger
        self._logger: Log = logger

    # ------------------------------------------------------------------
    # Callbacks / overrides
    # ------------------------------------------------------------------

    def reset(self):
        pass

    def show(self):
        self.init()
        super().show()
        self._configuration.show()

    def exit(self):
        self.close()
