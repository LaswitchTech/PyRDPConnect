#!/usr/bin/env python3
# src/client/client.py
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
from app.ui import Form
from app.configuration import Configuration
from app.log import Log
from network.diagnostic import Diagnostic
from .freerdp import FreeRDP

if TYPE_CHECKING:
    # For type hints only, avoids circular import at runtime
    from app.application import Application

class Client(QMainWindow):
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

        # --- auto-wire from QApplication if not provided ---
        if helper is None or configuration is None or logger is None:
            app = QApplication.instance()
            if app is None:
                raise RuntimeError("Client must be created after QApplication/Application.")
            # narrow the type for linters / IDEs
            # no runtime import to avoid circular imports
            helper = helper or app.helper          # type: ignore[attr-defined]
            configuration = configuration or app.configuration  # type: ignore[attr-defined]
            logger = logger or app.logger          # type: ignore[attr-defined]

        # Helper
        self._helper: Helper = helper

        # Configuration
        self._configuration: Configuration = configuration
        if(self._helper.get_os() == "linux"):
            self._configuration.label("network.wifi", "WiFi")
            self._configuration.add("network.wifi.ssid", None, "text", label="SSID")
            self._configuration.add("network.wifi.passphrase", None, "password")
        self._configuration.label("network.openvpn", "OpenVPN")
        self._configuration.add("network.openvpn.file", None, "text", label="Config File")
        self._configuration.add("network.openvpn.auto", False, "checkbox", label="Auto Connect")
        self._configuration.label("network.wireguard", "WireGuard")
        self._configuration.add("network.wireguard.file", None, "text", label="Config File")
        self._configuration.add("network.wireguard.auto", False, "checkbox", label="Auto Connect")
        self._configuration.add("customize.window.logo_file", None, "picture", label="Logo File")
        self._configuration.add("customize.window.logo_position", "top-center", "select", label="Logo Position", choices=["top-left", "top-center", "top-right", "center-left", "center-center", "center-right", "bottom-left", "bottom-center", "bottom-right"])
        self._configuration.add("customize.window.form_position", "center-center", "select", label="Form Position", choices=["top-left", "top-center", "top-right", "center-left", "center-center", "center-right", "bottom-left", "bottom-center", "bottom-right"])
        self._configuration.add("customize.window.fullscreen", False, "checkbox")
        self._configuration.add("customize.window.gradient_start", "#265162", "color", label="Gradient Start")
        self._configuration.add("customize.window.gradient_end", "#002136", "color", label="Gradient End")
        self._configuration.add("customize.controls.exit", False, "checkbox")
        self._configuration.add("customize.controls.restart", False, "checkbox")
        self._configuration.add("customize.controls.shutdown", False, "checkbox")
        self._configuration.add("customize.controls.diagnostics", False, "checkbox")
        self._configuration.add("administration.update", None, "button", label="Check for Updates", action=self.exit)
        self._configuration.add("administration.import", None, "button", label="Import Configuration", action=self.exit)
        self._configuration.add("administration.export", None, "button", label="Export Configuration", action=self.exit)

        # Save any new defaults
        self._configuration.save()

        # Logger
        self._logger: Log = logger

        # FreeRDP
        self._freerdp = FreeRDP(self._helper, self._configuration, self._logger)

    # ------------------------------------------------------------------
    # Callbacks / overrides
    # ------------------------------------------------------------------

    def override(self) -> str:
        # Get gradient colors from configuration
        start = self._configuration.get("customize.window.gradient_start")
        end   = self._configuration.get("customize.window.gradient_end")

        # Return CSS for client window background
        return (
            "\n"
            "#Client {\n"
            f"    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {start}, stop:1 {end});\n"
            "}\n"
        )

    def reset(self):
        pass

    def show(self):
        self.init()
        # self.playground()
        super().show()

    def exit(self):
        exit(0)

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def showDiagnostic(self):
        host = self._configuration.get("general.host")
        ports = [self._configuration.get("general.port")]
        dlg = Diagnostic(host, ports, parent=self)
        dlg.show()

    def init(self):

        # Set window title and icon
        self.setWindowTitle("Client")
        icon_path = self._helper.join(self._helper.get_path("icons"),"play-fill.ico")
        self.setWindowIcon(QIcon(icon_path) if self._helper.file_exists(icon_path) else QIcon())
        self.setObjectName("Client")

        # Make the window fullscreen and borderless
        if self._configuration.get("customize.window.fullscreen"):
            self.showFullScreen()
            self.setWindowFlags(Qt.FramelessWindowHint)

        # Create central widget and set layout
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        # Create a 3x3 grid layout
        grid_layout = QGridLayout(central_widget)

        # Add spacers to the grid layout to create equal-sized sections
        for i in range(3):
            grid_layout.setColumnStretch(i, 1)
            grid_layout.setRowStretch(i, 1)

        # Determine positions from the configuration
        login_pos = self._configuration.get("customize.window.form_position")
        logo_pos = self._configuration.get("customize.window.logo_position")

        # Mapping of position names to grid coordinates
        position_map = {
            "top-left": (0, 0),
            "top-center": (0, 1),
            "top-right": (0, 2),
            "center-left": (1, 0),
            "center-center": (1, 1),
            "center-right": (1, 2),
            "bottom-left": (2, 0),
            "bottom-center": (2, 1),
            "bottom-right": (2, 2)
        }

        # Calculate grid positions
        login_grid_pos = position_map.get(login_pos, (1, 1))
        logo_grid_pos = position_map.get(logo_pos, (1, 1))

        # Load and place the logo image
        logo_b64 = self._configuration.get("customize.window.logo_file")
        pixmap = QPixmap()

        if isinstance(logo_b64, str) and logo_b64.strip():
            # Stored as base64
            try:
                data = base64.b64decode(logo_b64)
                if not pixmap.loadFromData(data, "PNG"):
                    pixmap = QPixmap()  # reset on failure
            except Exception as e:
                print(f"[Client] Failed to decode logo from configuration: {e}")
                pixmap = QPixmap()

        # Fallback to bundled logo if no valid custom logo
        if pixmap.isNull():
            fallback = self._helper.join(self._helper.get_path("img"), "logo.png")
            if fallback and self._helper.file_exists(fallback):
                pixmap.load(fallback)

        if not pixmap.isNull():
            logo_label = QLabel(central_widget)
            logo_label.setMaximumSize(250, 250)
            logo_label.setPixmap(
                pixmap.scaled(250, 250, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
            logo_label.setAlignment(Qt.AlignCenter)
            grid_layout.addWidget(logo_label, *logo_grid_pos, 1, 1, Qt.AlignCenter)

        # Initialize an empty list to keep track of the tab order
        tab_order_widgets = []

         # Create form layout for login if needed
        form_widget = QWidget()  # A new QWidget to hold the form_layout
        form_layout = QFormLayout(form_widget)
        form_layout.setSpacing(0)  # Set spacing to 0 to remove space between rows

        # Initialize an empty list to keep track of input widgets
        self._inputs = []

        # Add the form items to the form layout
        general = self._configuration.get("general", {}) or {}
        for name, value in general.items():
            if value in (None, ""):
                widget = self._configuration.input(f"general.{name}")
                widget.setObjectName(f"general.{name}")
                form_layout.addRow(widget)
                self._inputs.append(widget)
                tab_order_widgets.append(widget)
                if isinstance(widget, QLineEdit):
                    widget.returnPressed.connect(self.connect)

        # Create horizontal layout for the buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)

        # Create buttons
        # Connect button
        self.connect_button = Form.button(
            label="Connect",
            action=self.connect
        )
        tab_order_widgets.append(self.connect_button)
        button_layout.addWidget(self.connect_button)

        # Configuration button
        self.config_button = Form.button(
            label="",
            icon="gear-fill",
            action=self._configuration.show
        )
        tab_order_widgets.append(self.config_button)
        buttons_layout.addWidget(self.config_button)

        if self._configuration.get("customize.controls.diagnostics"):
            self.diagnostics_button = Form.button(
                label="Diagnostics",
                icon="activity",
                action=self.showDiagnostic
            )
            tab_order_widgets.append(self.diagnostics_button)
            buttons_layout.addWidget(self.diagnostics_button)

        if self._configuration.get("customize.controls.exit"):
            self.exit_button = Form.button(
                label="Exit",
                icon="x-octagon",
                action=self.exit
            )
            tab_order_widgets.append(self.exit_button)
            buttons_layout.addWidget(self.exit_button)

        if self._configuration.get("customize.controls.restart"):
            self.restart_button = Form.button(
                label="Restart",
                icon="arrow-repeat",
                action=self.exit
            )
            tab_order_widgets.append(self.restart_button)
            buttons_layout.addWidget(self.restart_button)

        if self._configuration.get("customize.controls.shutdown"):
            self.shutdown_button = Form.button(
                label="Shutdown",
                icon="power",
                action=self.exit
            )
            tab_order_widgets.append(self.shutdown_button)
            buttons_layout.addWidget(self.shutdown_button)

        # Add buttons to view
        form_layout.addRow(button_layout)
        form_layout.addRow(buttons_layout)

        # After all widgets have been created, set the tab order based on the list
        for i in range(len(tab_order_widgets) - 1):
            self.setTabOrder(tab_order_widgets[i], tab_order_widgets[i + 1])

        # Set the tab order from the last form field to the first button
        if tab_order_widgets:
            self.setTabOrder(tab_order_widgets[-1], self.connect_button)

        # Set the tab order for the buttons
        self.setTabOrder(self.connect_button, self.config_button)
        if self._configuration.get("customize.controls.exit"):
            self.setTabOrder(self.config_button, self.exit_button)

        # Add the form layout to the grid layout
        form_widget.setLayout(form_layout)
        grid_layout.addWidget(form_widget, *login_grid_pos, 1, 1, Qt.AlignCenter)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def connect(self):

        # Initialize overrides dictionary
        overrides = {}

        # Get values from input fields
        for widget in self._inputs:
            name = widget.objectName()
            if isinstance(widget, QLineEdit):
                overrides[name] = widget.text()
                widget.clear()
            elif isinstance(widget, QSpinBox):
                overrides[name] = widget.value()
                widget.setValue(0)
            elif isinstance(widget, QComboBox):
                overrides[name] = widget.currentText()
                widget.setCurrentIndex(0)
            elif isinstance(widget, QCheckBox):
                overrides[name] = widget.isChecked()
                widget.setChecked(False)

        # Add the form items to the form layout
        general = self._configuration.get("general", {}) or {}
        for name, value in general.items():
            if overrides.get(f"general.{name}") in (None, ""):
                overrides[f"general.{name}"] = value

        self._freerdp.connect(parent=self, overrides=overrides)
