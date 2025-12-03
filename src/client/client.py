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

from core.helper import Helper
from core.ui import Form
from core.configuration import Configuration
from core.log import Log
from core.network.diagnostic import Diagnostic
from .openvpn import OpenVPN
from .freerdp import FreeRDP

if TYPE_CHECKING:
    # For type hints only, avoids circular import at runtime
    from core.application import Application

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
        self._configuration.label("vpn", "VPN")
        self._configuration.label("vpn.wireguard", "WireGuard")
        self._configuration.add("vpn.wireguard.file", None, "text", label="Config File")
        self._configuration.add("vpn.wireguard.auto", False, "checkbox", label="Auto Connect")
        self._configuration.add("customize.window.logo_file", None, "picture", label="Logo File")
        self._configuration.add("customize.window.logo_position", "top-center", "select", label="Logo Position", choices=["top-left", "top-center", "top-right", "center-left", "center-center", "center-right", "bottom-left", "bottom-center", "bottom-right"])
        self._configuration.add("customize.window.form_position", "center-center", "select", label="Form Position", choices=["top-left", "top-center", "top-right", "center-left", "center-center", "center-right", "bottom-left", "bottom-center", "bottom-right"])
        self._configuration.add("customize.window.fullscreen", False, "checkbox")
        self._configuration.add("customize.window.gradient_start", "#76797c", "color", label="Gradient Start")
        self._configuration.add("customize.window.gradient_end", "#242829", "color", label="Gradient End")
        self._configuration.add("customize.controls.exit", True, "checkbox")
        self._configuration.add("customize.controls.restart", False, "checkbox")
        self._configuration.add("customize.controls.shutdown", False, "checkbox")
        self._configuration.add("customize.controls.diagnostics", True, "checkbox")

        # Save any new defaults
        self._configuration.save()

        # Logger
        self._logger: Log = logger

        # FreeRDP
        self._freerdp = FreeRDP()

        # OpenVPN
        self._openvpn = OpenVPN(parent=self)

        # When RDP disconnects, stop VPN if it was auto-started
        try:
            self._freerdp.disconnected.connect(self._on_rdp_disconnected)
        except AttributeError:
            # If disconnected signal doesn't exist yet, you'll add it in FreeRDP
            self._logger.append(
                "[Client] FreeRDP.disconnected signal not available. "
                "Add it to FreeRDP to auto-stop VPN on session end.",
                channel="client",
                level="warning",
            )

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
        super().show()

    def exit(self):
        self.close()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        """
        Ensure VPN is stopped when the window closes.
        """
        try:
            if hasattr(self, "_openvpn") and self._openvpn is not None:
                if self._openvpn.is_running():
                    self._logger.append(
                        "[Client] Window closing → stopping OpenVPN.",
                        channel="client",
                    )
                    self._openvpn.stop()
        except Exception as e:
            if hasattr(self, "_logger") and self._logger is not None:
                self._logger.append(
                    f"[Client] Exception during closeEvent OpenVPN cleanup: {e}",
                    channel="client",
                    level="error",
                )

        super().closeEvent(event)

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
        self.setWindowTitle(self._app.name)
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
            fallback = self._helper.join(self._helper.get_path("icons"), "icon.png")
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

        if self._configuration.get("customize.controls.restart"):
            self.restart_button = Form.button(
                label="Restart",
                icon="arrow-repeat",
                action=self._app.restart
            )
            tab_order_widgets.append(self.restart_button)
            buttons_layout.addWidget(self.restart_button)

        if self._configuration.get("customize.controls.shutdown"):
            self.shutdown_button = Form.button(
                label="Shutdown",
                icon="power",
                action=self._app.shutdown
            )
            tab_order_widgets.append(self.shutdown_button)
            buttons_layout.addWidget(self.shutdown_button)

        if self._configuration.get("customize.controls.exit"):
            self.exit_button = Form.button(
                label="Exit",
                icon="x-octagon",
                action=self.exit
            )
            tab_order_widgets.append(self.exit_button)
            buttons_layout.addWidget(self.exit_button)

        # Add buttons to view
        form_layout.addRow(button_layout)
        form_layout.addRow(buttons_layout)

        # Build explicit tab order chain: fields → connect → config → diagnostics → restart → shutdown → exit
        tab_chain = []

        # First, all input widgets (username, password, etc.) in the order they were added
        tab_chain.extend(tab_order_widgets)

        # Then the buttons, in the desired order
        tab_chain.append(self.connect_button)
        tab_chain.append(self.config_button)

        if hasattr(self, "diagnostics_button"):
            tab_chain.append(self.diagnostics_button)
        if hasattr(self, "restart_button"):
            tab_chain.append(self.restart_button)
        if hasattr(self, "shutdown_button"):
            tab_chain.append(self.shutdown_button)
        if hasattr(self, "exit_button"):
            tab_chain.append(self.exit_button)

        # Apply the tab order sequence
        for i in range(len(tab_chain) - 1):
            self.setTabOrder(tab_chain[i], tab_chain[i + 1])

        # Add the form layout to the grid layout
        form_widget.setLayout(form_layout)
        grid_layout.addWidget(form_widget, *login_grid_pos, 1, 1, Qt.AlignCenter)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_rdp_disconnected(self, rc: int):
        self._logger.append(
            f"[Client] FreeRDP session ended with code {rc}.",
            channel="client",
        )

        if self._configuration.get("vpn.openvpn.auto"):
            self._logger.append(
                "[Client] Auto-VPN enabled → stopping OpenVPN.",
                channel="client",
            )
            self._openvpn.stop()

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

        # Make sure VPN is up if needed; only start RDP after VPN connects
        if self._configuration.get("vpn.openvpn.auto"):
            self._openvpn.connect(
                parent=self,
                overrides=overrides,
                on_success=lambda: self._freerdp.connect(parent=self, overrides=overrides),
            )
        else:
            self._freerdp.connect(parent=self, overrides=overrides)
