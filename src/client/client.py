#!/usr/bin/env python3
# src/client/client.py

from __future__ import annotations

import re
import base64
import threading
import time
from typing import Optional, TYPE_CHECKING, Callable

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QGridLayout, QLabel, QLineEdit,
    QHBoxLayout, QFormLayout, QSpinBox, QComboBox, QCheckBox,
    QApplication,
)
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import Qt, QTimer, pyqtSignal

from core.helper import Helper
from core.ui import Form
from core.configuration import Configuration
from core.log import Log
from core.network.diagnostic import Diagnostic
from core.network.tools import Tools
from .openvpn import OpenVPN
from .freerdp import FreeRDP

if TYPE_CHECKING:
    # For type hints only, avoids circular import at runtime
    from core.application import Application

class Client(QMainWindow):
    """
    Main application window placeholder.
    """

    vpn_diag_request = pyqtSignal(dict, object, object, bool)

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

        # Tools
        self._tools: Tools = Tools(helper=self._helper)

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
        self._logger.append(
            "[Client] OpenVPN instance created and wired into Client.",
            channel="client",
            level="debug",
        )
        # Wire diagnostic VPN request signal so it always runs on the GUI thread
        self.vpn_diag_request.connect(self._handle_vpn_diag_request)
        self._logger.append(
            "[Client] vpn_diag_request signal connected to _handle_vpn_diag_request.",
            channel="client",
            level="debug",
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

    def overrides(self, clear: bool = True) -> dict:
        # Initialize overrides dictionary
        overrides = {}

        # Get values from input fields
        for widget in self._inputs:
            name = widget.objectName()
            if isinstance(widget, QLineEdit):
                overrides[name] = widget.text()
                if clear:
                    widget.clear()
            elif isinstance(widget, QSpinBox):
                overrides[name] = widget.value()
                if clear:
                    widget.setValue(0)
            elif isinstance(widget, QComboBox):
                overrides[name] = widget.currentText()
                if clear:
                    widget.setCurrentIndex(0)
            elif isinstance(widget, QCheckBox):
                overrides[name] = widget.isChecked()
                if clear:
                    widget.setChecked(False)

        # Add the form items to the form layout
        general = self._configuration.get("general", {}) or {}
        for name, value in general.items():
            if overrides.get(f"general.{name}") in (None, ""):
                overrides[f"general.{name}"] = value

        # if we have cleared, reset focus to first input
        if clear and self._inputs:
            self._inputs[0].setFocus()

        return overrides

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
    # Diagnostics
    # ------------------------------------------------------------------

    def showDiagnostic(self):
        overrides = self.overrides(clear=False)

        # Resolve host/port for diagnostics using overrides first, then configuration
        host = (
            overrides.get("general.host")
            or self._configuration.get("general.host")
            or self._configuration.get("vpn.openvpn.host")
            or ""
        )
        port = (
            overrides.get("general.port")
            or self._configuration.get("general.port")
            or self._configuration.get("vpn.openvpn.port")
            or 3389
        )

        diag = Diagnostic(host, [port])
        self._logger.append(
            "[Client] Diagnostic instance created.",
            channel="client",
            level="debug",
        )

        # Core connectivity steps
        diag.add("device", "Device", None, self._step_device)
        self._logger.append(
            "[Client] Diagnostic step 'device' registered.",
            channel="client",
            level="debug",
        )
        diag.add("network", "Network", None, self._step_network)
        self._logger.append(
            "[Client] Diagnostic step 'network' registered.",
            channel="client",
            level="debug",
        )
        diag.add("internet", "Internet", None, self._step_internet)
        self._logger.append(
            "[Client] Diagnostic step 'internet' registered.",
            channel="client",
            level="debug",
        )

        # Optional VPN configuration step (no actual tunnel establishment here)
        if self._configuration.get("vpn.openvpn.auto"):
            diag.add("vpn", "VPN", None, self._step_vpn)
            self._logger.append(
                "[Client] Diagnostic step 'vpn' (VPN connectivity) registered.",
                channel="client",
                level="debug",
            )

        # Target service step
        diag.add("service", "Service", None, self._step_service)
        self._logger.append(
            "[Client] Diagnostic step 'service' registered.",
            channel="client",
            level="debug",
        )

        self._logger.append(
            "[Client] Starting diagnostics via Diagnostic.show().",
            channel="client",
            level="debug",
        )
        diag.show(
            parent=self,
            finished=self._on_diagnostic_finished,
        )
        self._logger.append(
            "[Client] Diagnostic dialog closed.",
            channel="client",
            level="debug",
        )

    def _step_device(self, print_fn: Callable[[str], None]) -> bool:
        ips = self._tools.ip()
        if not ips:
            print_fn("Device: could not determine any local IPv4 address.")
            return False

        ip = None
        for cand in ips:
            if not cand.startswith("127.") and not self._tools.apipa(cand):
                ip = cand
                break

        if not ip:
            print_fn(f"Device: only APIPA/loopback addresses found: {ips}")
            return False

        if self._tools.apipa(ip):
            print_fn(f"Device: APIPA address {ip} (DHCP failure).")
            return False

        print_fn(f"Device: local IP is {ip}")
        return True

    def _step_network(self, print_fn: Callable[[str], None]) -> bool:
        gw = self._tools.gateway()
        if not gw:
            print_fn("Network: default gateway not found.")
            return False

        print_fn(f"Network: default gateway {gw}")
        gw_ok = self._tools.ping(gw)
        print_fn("Network: gateway reachable." if gw_ok else "Network: gateway not reachable.")
        return gw_ok

    def _step_internet(self, print_fn: Callable[[str], None]) -> bool:
        pub_ok = self._tools.ping("8.8.8.8")
        print_fn(
            "Internet: 8.8.8.8 reachable."
            if pub_ok else
            "Internet: cannot reach 8.8.8.8."
        )

        IPs = self._tools.nslookup("google.com")
        dns_ok = bool(IPs)
        if dns_ok:
            print_fn(f"Internet: DNS OK → {IPs}")
        else:
            print_fn(f"Internet: DNS failed: {IPs or 'no valid addresses found.'}")

        return pub_ok and dns_ok

    def _step_vpn(self, print_fn):
        """
        Diagnostic VPN step.

        This runs in DiagnosticThread, but we reuse OpenVPN.connect()
        on the UI thread and block here only until we get a success/fail
        signal (or hit a timeout).
        """
        self._logger.append(
            "[Client] _step_vpn called.",
            channel="client",
            level="debug",
        )

        # Retrieve overrides if available
        if hasattr(self, "overrides"):
            self._logger.append(
                "[Client] _step_vpn: using self.overrides(clear=False).",
                channel="client",
                level="debug",
            )
            overrides = self.overrides(clear=False)
            self._logger.append(
                f"[Client] _step_vpn: overrides obtained: {overrides}.",
                channel="client",
                level="debug",
            )
        else:
            self._logger.append(
                "[Client] _step_vpn: no overrides() method found, using empty overrides.",
                channel="client",
                level="debug",
            )
            overrides = {}

        # Basic configuration check
        if not self._openvpn.is_configured():
            msg = "VPN: OpenVPN is not configured (no .ovpn file set)."
            print_fn(msg)
            self._logger.append(
                f"[Client] _step_vpn: {msg}",
                channel="client",
                level="warning",
            )
            return False

        # Already running?
        if self._openvpn.is_running():
            msg = "VPN: tunnel already running."
            print_fn(msg)
            self._logger.append(
                f"[Client] _step_vpn: {msg}",
                channel="client",
                level="debug",
            )
            return True

        print_fn("VPN: scheduling OpenVPN.connect() on UI thread...")
        self._logger.append(
            "[Client] _step_vpn: emitting vpn_diag_request signal to GUI thread.",
            channel="client",
            level="debug",
        )

        # Shared result + event
        result = {"done": False, "ok": False}
        done_event = threading.Event()

        def _mark(ok: bool) -> None:
            self._logger.append(
                f"[Client] _step_vpn: _mark called with ok={ok}.",
                channel="client",
                level="debug",
            )
            result["ok"] = ok
            result["done"] = True
            done_event.set()

        def _on_vpn_success() -> None:
            self._logger.append(
                "[Client] _step_vpn: _on_vpn_success callback invoked.",
                channel="client",
                level="debug",
            )
            _mark(True)

        def _on_vpn_error() -> None:
            self._logger.append(
                "[Client] _step_vpn: _on_vpn_error callback invoked.",
                channel="client",
                level="debug",
            )
            _mark(False)

        self.vpn_diag_request.emit(
            overrides,
            _on_vpn_success,
            _on_vpn_error,
            False,
        )

        # Wait until we know the result, but don’t spin
        timeout_seconds = 60.0
        start = time.monotonic()
        self._logger.append(
            f"[Client] _step_vpn: waiting for VPN result with timeout={timeout_seconds}s.",
            channel="client",
            level="debug",
        )

        while True:
            if done_event.wait(0.1):
                self._logger.append(
                    "[Client] _step_vpn: done_event set, breaking wait loop.",
                    channel="client",
                    level="debug",
                )
                break

            elapsed = time.monotonic() - start
            if elapsed > timeout_seconds:
                msg = "VPN: timeout while waiting for tunnel establishment."
                print_fn(msg)
                self._logger.append(
                    f"[Client] _step_vpn: {msg} (elapsed={elapsed:.1f}s)",
                    channel="client",
                    level="warning",
                )
                return False

        if result["ok"]:
            msg = "VPN: tunnel established successfully."
            print_fn(msg)
            self._logger.append(
                f"[Client] _step_vpn: {msg}",
                channel="client",
                level="info",
            )
            return True

        msg = "VPN: failed to establish tunnel. See OpenVPN log for details."
        print_fn(msg)
        self._logger.append(
            f"[Client] _step_vpn: {msg}",
            channel="client",
            level="warning",
        )
        return False

    def _handle_vpn_diag_request(
        self,
        overrides: dict,
        on_success: Optional[Callable[[], None]],
        on_error: Optional[Callable[[], None]],
        show_dialog: bool,
    ) -> None:
        """
        Handle VPN connection requests coming from the diagnostic thread.

        This method is executed in the GUI thread and safely calls OpenVPN.connect().
        """
        self._logger.append(
            "[Client] _handle_vpn_diag_request() received in GUI thread → calling OpenVPN.connect().",
            channel="client",
            level="debug",
        )
        self._openvpn.connect(
            parent=self,
            overrides=overrides,
            on_success=on_success,
            on_error=on_error,
            show_dialog=False,
        )

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

    def _step_service(self, print_fn: Callable[[str], None]) -> bool:
        overrides = self.overrides(clear=False)

        host = (
            overrides.get("general.host")
            or self._configuration.get("general.host")
            or self._configuration.get("vpn.openvpn.host")
            or ""
        )
        if not host:
            print_fn("Service: no host configured.")
            return False

        port = (
            overrides.get("general.port")
            or self._configuration.get("general.port")
            or self._configuration.get("vpn.openvpn.port")
        )
        ports = [port] if port else []

        res_ok, addr = self._resolve_host(host)
        if not res_ok:
            print_fn(f"Service: cannot resolve {host}: {addr}")
            return False

        print_fn(f"Service: target {host} -> {addr} (ports: {ports})")

        p_ok = self._tools.ping(addr)
        print_fn("Service: ping reachable." if p_ok else "Service: ping failed.")

        port_results = self._tools.nmap(addr, ports)
        if not port_results:
            print_fn("Service: no ports tested or scan failed.")
            t_ok = False
        else:
            open_any = False
            for p, is_open in port_results.items():
                print_fn(f"Service: port {p} {'open' if is_open else 'closed'}.")
                if is_open:
                    open_any = True
            t_ok = open_any

        return p_ok and t_ok

    def _on_diagnostic_finished(self, success: bool) -> None:
        self._logger.append(
            f"[Client] _on_diagnostics_finished called with success={success}.",
            channel="client",
            level="debug",
        )
        if success:
            self._logger.append(
                "[Client] Diagnostics completed successfully.",
                channel="client",
            )
        else:
            self._logger.append(
                "[Client] Diagnostics detected issues.",
                channel="client",
                level="warning",
            )
            self._logger.append(
                "[Client] Diagnostics detected issues → requesting OpenVPN.stop().",
                channel="client",
                level="debug",
            )
            self._openvpn.stop()

    # ------------------------------------------------------------------
    # Diagnostics helpers
    # ------------------------------------------------------------------

    def _is_ip(self, value: str) -> bool:
        return bool(re.match(r"^\d+\.\d+\.\d+\.\d+$", value.strip()))

    def _resolve_host(self, host: str) -> tuple[bool, str]:
        if self._is_ip(host):
            return True, host

        ips = self._tools.nslookup(host)
        if ips:
            return True, ips[0]
        return False, "Resolution failed"

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

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
            logo_label.setStyleSheet("padding: 0px; margin: 0px; border: none;")
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
        overrides = self.overrides()

        # Make sure VPN is up if needed; only start RDP after VPN connects
        if self._configuration.get("vpn.openvpn.auto"):
            self._openvpn.connect(
                parent=self,
                overrides=overrides,
                on_success=lambda: self._freerdp.connect(parent=self, overrides=overrides),
            )
        else:
            self._freerdp.connect(parent=self, overrides=overrides)
