#!/usr/bin/env python3
# src/client/freerdp.py

from __future__ import annotations

import enum
import os
import re
import subprocess
import sys
import threading
from typing import Any, Dict, Optional, Iterable

from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtWidgets import (
    QPushButton, QProgressDialog, QApplication
)

from app.helper import Helper
from app.configuration import Configuration
from app.ui import MsgBox
from app.log import Log

# ---------------------------------------------------------------------------
# Severity / events
# ---------------------------------------------------------------------------

class FreeRDPSeverity(enum.Enum):
    DEBUG = 0
    INFO = 1
    WARNING = 2
    ERROR = 3


class FreeRDPEvent:
    def __init__(self, severity: FreeRDPSeverity, code: str, message: str, hint: str = ""):
        self.severity = severity
        self.code = code
        self.message = message
        self.hint = hint

# ---------------------------------------------------------------------------
# Log interpreter
# ---------------------------------------------------------------------------

class FreeRDPInterpreter:
    """
    Interprets FreeRDP stdout/stderr text into higher-level events.
    """

    def __init__(self, show_cert_warning: bool = False):
        self.show_cert_warning = show_cert_warning

    # Patterns → (severity, code, user message, hint)
    RULES = [
        # --- Normal/expected endings ---
        (r'ERRINFO_LOGOFF_BY_USER', (FreeRDPSeverity.INFO, 'ERRINFO_LOGOFF_BY_USER',
            'You logged off the remote session.',
            'This is normal if you clicked Disconnect/Sign out on the remote Windows session.')),
        (r'ERRINFO_IDLE_TIMEOUT', (FreeRDPSeverity.INFO, 'ERRINFO_IDLE_TIMEOUT',
            'Disconnected due to inactivity.', 'Reconnect to continue.')),

        # --- Common alternate lines seen on some FreeRDP builds/platforms ---
        (r'ERRINFO_RPC_INITIATED_DISCONNECT', (FreeRDPSeverity.INFO, 'ERRINFO_LOGOFF_BY_USER',
            'You were disconnected by the server.',
            'This can be normal if you signed out or the admin ended the session.')),
        (r'freerdp_disconnect: closing connection', (FreeRDPSeverity.INFO, 'ERRINFO_LOGOFF_BY_USER',
            'The session was closed.',
            'If you clicked Disconnect/Sign out, this is expected.')),

        # --- Connect/handshake timeouts ---
        (r'ERRCONNECT_ACTIVATION_TIMEOUT', (FreeRDPSeverity.ERROR, 'ERRCONNECT_ACTIVATION_TIMEOUT',
            'The server took too long to activate the session.',
            'Try again, or increase the connection timeout in Settings.')),

        # --- Certificate warnings ---
        (r'Certificate not checked, /cert:ignore in use', (FreeRDPSeverity.WARNING, 'CERT_IGNORE',
            'Unverified server certificate (ignored).',
            'Only use /cert:ignore on trusted LAN. Otherwise, enable certificate validation.')),

        # --- Password on CLI warnings (don’t block, just hint) ---
        (r'Using /p is insecure', (FreeRDPSeverity.WARNING, 'INSECURE_PASSWORD_ARG',
            'Password was passed on the command line.',
            'Use /from-stdin or set FREERDP_ASKPASS for safer credential entry.')),

        # --- Device hotplug noise (non-fatal) ---
        (r'handle_hotplug failed with error 1', (FreeRDPSeverity.WARNING, 'RDPDR_HOTPLUG',
            'A redirected device failed to hot-plug.',
            'Usually harmless. If it persists, disable “Drives/Printers” redirection and retry.')),

        # --- Generic catch-alls we still want to prettify ---
        (r'Could not connect to RDP server', (FreeRDPSeverity.ERROR, 'CANNOT_CONNECT',
            'Could not connect to the server.', 'Verify IP/hostname and port 3389 reachability.')),
        (r'Access Denied', (FreeRDPSeverity.ERROR, 'ACCESS_DENIED',
            'Access denied by the server.', 'Check username, password, and domain.')),
        (r'LOGON_FAILURE', (FreeRDPSeverity.ERROR, 'LOGON_FAILURE',
            'Logon failed.', 'Check credentials or account lockout.')),
        (r'hostname cannot be resolved', (FreeRDPSeverity.ERROR, 'DNS_FAIL',
            'Host cannot be resolved.', 'Check DNS or use the IP address.')),
        (r'GATEWAY.*denied|HTTP/.* 403', (FreeRDPSeverity.ERROR, 'GATEWAY_DENIED',
            'Gateway denied the connection.', 'Check RD Gateway URL/credentials.')),
    ]

    def classify(self, text: str) -> list[FreeRDPEvent]:
        events: list[FreeRDPEvent] = []
        for pat, (sev, code, msg, hint) in self.RULES:
            if re.search(pat, text, re.IGNORECASE):
                if code == 'CERT_IGNORE' and not self.show_cert_warning:
                    continue
                events.append(FreeRDPEvent(sev, code, msg, hint))
        return events

    def most_relevant(self, events: list[FreeRDPEvent]) -> Optional[FreeRDPEvent]:
        if not events:
            return None
        priority = {
            FreeRDPSeverity.ERROR: 3,
            FreeRDPSeverity.WARNING: 2,
            FreeRDPSeverity.INFO: 1,
            FreeRDPSeverity.DEBUG: 0,
        }
        events.sort(key=lambda e: priority.get(e.severity, 0), reverse=True)
        return events[0]


# ---------------------------------------------------------------------------
# Connection thread
# ---------------------------------------------------------------------------

class FreeRDPConnection(QThread):
    """
    Runs xfreerdp in a background thread, collects logs, and classifies the result.
    """
    connection_success = pyqtSignal()
    connection_failed = pyqtSignal(str, str, str)  # title, details, raw_log
    connection_info = pyqtSignal(str)             # optional live status/lines

    def __init__(
        self,
        command: list[str],
        parent=None,
        show_cert_warning: bool = False,
        stdin_password: Optional[str] = None,
        debug_enabled: bool = False,
        logger: Optional[Log] = None,
        log_channel: str = "freerdp",
    ):
        super().__init__(parent)
        self.command = command
        self.freerdp_process: Optional[subprocess.Popen] = None
        self._interpreter = FreeRDPInterpreter(show_cert_warning=show_cert_warning)
        self._stdin_password = stdin_password
        self._debug_enabled = debug_enabled
        self._stop_flag = False

        self._logger = logger
        self._log_channel = log_channel

    def run(self):
        collected: list[str] = []
        text = ""

        try:
            env = os.environ.copy()
            freerdp_bin = self.command[0]
            base_dir = os.path.dirname(freerdp_bin)

            # Bundled runtime dirs
            lib_dir = os.path.join(base_dir, "lib")
            plugins_dir = os.path.join(base_dir, "plugins")

            # Library search paths
            if sys.platform == "darwin":
                if os.path.isdir(lib_dir):
                    env["DYLD_LIBRARY_PATH"] = lib_dir + (
                        ":" + env.get("DYLD_LIBRARY_PATH", "")
                        if env.get("DYLD_LIBRARY_PATH") else ""
                    )
            elif sys.platform.startswith("linux"):
                if os.path.isdir(lib_dir):
                    env["LD_LIBRARY_PATH"] = lib_dir + (
                        ":" + env.get("LD_LIBRARY_PATH", "")
                        if env.get("LD_LIBRARY_PATH") else ""
                    )

            if os.path.isdir(plugins_dir):
                env["FREERDP_PLUGIN_PATH"] = plugins_dir

            self.freerdp_process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                text=True,
                env=env,
                bufsize=1,
                universal_newlines=True,
            )

            # Password via stdin (/from-stdin)
            try:
                if any(arg.startswith("/from-stdin") for arg in self.command) and self._stdin_password is not None:
                    self.freerdp_process.stdin.write(self._stdin_password + "\n")
                    self.freerdp_process.stdin.flush()
            except Exception:
                pass

            def pump(stream):
                for line in iter(stream.readline, ""):
                    if self._stop_flag:
                        break
                    ln = line.rstrip()
                    if ln:
                        collected.append(ln)
                        # Append to central logger
                        if self._logger is not None:
                            self._logger.append(ln, channel=self._log_channel)
                        # Optionally emit live info
                        if self._debug_enabled:
                            self.connection_info.emit(ln)
                try:
                    stream.close()
                except Exception:
                    pass

            t_out = threading.Thread(target=pump, args=(self.freerdp_process.stdout,))
            t_err = threading.Thread(target=pump, args=(self.freerdp_process.stderr,))
            t_out.start()
            t_err.start()

            rc = self.freerdp_process.wait()
            t_out.join()
            t_err.join()

            text = "\n".join(collected)

            if self._stop_flag:
                # treat as user cancel
                return

            if rc == 0:
                self.connection_success.emit()
                return

            events = self._interpreter.classify(text)
            top = self._interpreter.most_relevant(events)

            # Logoff / user disconnect
            if top and top.code == "ERRINFO_LOGOFF_BY_USER":
                details = top.message + (f"\n\nHint: {top.hint}" if top.hint else "")
                self.connection_failed.emit("Disconnected", details, text)
                return

            if top:
                title = "Connection problem" if top.severity != FreeRDPSeverity.INFO else "Information"
                details = top.message + (f"\n\nHint: {top.hint}" if top.hint else "")
            else:
                title = "Connection failed"
                details = (
                    "The connection ended unexpectedly.\n\n"
                    "Open the detailed log for more information."
                )

            self.connection_failed.emit(title, details, text)

        except Exception as e:
            if not text:
                try:
                    text = "\n".join(collected)
                except Exception:
                    text = ""
            self.connection_failed.emit(
                "Unexpected error",
                f"{type(e).__name__}: {e}",
                text,
            )

    # ------------------------------------------------------------------

    def stop(self):
        self._stop_flag = True
        if self.freerdp_process:
            try:
                self.freerdp_process.terminate()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Connection progress dialog
# ---------------------------------------------------------------------------

class FreeRDPDialog(QProgressDialog):
    canceled_by_user = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Connecting to server...", "Cancel", 0, 0, parent)
        self.setWindowModality(Qt.WindowModal)
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowTitleHint
            | Qt.CustomizeWindowHint | Qt.WindowCloseButtonHint
        )
        self.setObjectName("FreeRDPDialog")
        self.setMinimumDuration(0)
        self.setAutoReset(False)
        self.setFixedWidth(300)

        # Replace default Cancel button with our own so we can style it if needed
        btn = QPushButton("Cancel", self)
        btn.clicked.connect(self._on_cancel)
        self.setCancelButton(btn)

    def _on_cancel(self):
        self.canceled_by_user.emit()
        self.reject()


# ---------------------------------------------------------------------------
# High-level FreeRDP façade
# ---------------------------------------------------------------------------

class FreeRDP:

    def __init__(
        self,
        helper: Optional[Helper] = None,
        configuration: Optional[Configuration] = None,
        logger: Optional[Log] = None,
    ):

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
        self._configuration.add("general.host", None, "text", placeholder="Server Address")
        self._configuration.add("general.port", 3389, "number", min=1, max=65535)
        self._configuration.add("general.username", None, "text", placeholder="Username")
        self._configuration.add("general.password", None, "password", placeholder="Password")
        self._configuration.add("general.domain", None, "text", placeholder="Domain")
        self._configuration.label("freerdp", "FreeRDP")
        self._configuration.add("freerdp.display.resolution", None, "select", choices=["800x600", "1024x768", "1280x720", "1366x768", "1920x1080", "3840x2160"])
        self._configuration.add("freerdp.display.fullscreen", False, "checkbox", label="Fullscreen")
        self._configuration.add("freerdp.display.fit", False, "checkbox", label="Fit to window")
        self._configuration.add("freerdp.display.all", False, "checkbox", label="All monitors")
        self._configuration.add("freerdp.devices.output", "On this computer", "select", label="Play Sound", choices=["Never", "On this computer", "On the remote computer"])
        self._configuration.add("freerdp.devices.input", "On this computer", "select", label="Record Sound", choices=["Never", "On this computer", "On the remote computer"])
        self._configuration.add("freerdp.devices.printers", False, "checkbox")
        self._configuration.add("freerdp.devices.smart_cards", False, "checkbox", label="Smart Cards")
        self._configuration.add("freerdp.devices.ports", False, "checkbox")
        self._configuration.add("freerdp.devices.drives", False, "checkbox")
        self._configuration.add("freerdp.folders.redirect", False, "checkbox")
        self._configuration.add("freerdp.experience.clipboard", False, "checkbox")
        self._configuration.add("freerdp.experience.remotefx", False, "checkbox", label="RemoteFX")
        self._configuration.add("freerdp.experience.smooth_fonts", False, "checkbox", label="Smooth Fonts")
        self._configuration.add("freerdp.experience.desktop_composition", False, "checkbox", label="Desktop Composition")
        self._configuration.add("freerdp.experience.full_window_drag", False, "checkbox", label="Full Window Drag")
        self._configuration.add("freerdp.experience.menu_animations", False, "checkbox", label="Menu Animations")
        self._configuration.add("freerdp.experience.disable_themes", False, "checkbox", label="Disable Themes")
        self._configuration.add("freerdp.experience.disable_wallpaper", False, "checkbox", label="Disable Wallpaper")
        self._configuration.add("freerdp.experience.show_certificate_warning", False, "checkbox", label="Show Certificate Warning")

        # Save any new defaults
        self._configuration.save()

        # Logger
        self._logger: Log = logger
        self._log_channel = "freerdp"

        # Internal state
        self._dialog: Optional[FreeRDPDialog] = None
        self._thread: Optional[FreeRDPConnection] = None

    # ------------------------------------------------------------------
    # Binary / version helpers
    # ------------------------------------------------------------------

    def _binary_path(self) -> str:
        osname = self._helper.get_os()
        arch = self._helper.get_arch()

        if osname in ("macos", "linux"):
            rel = f"bin/freerdp/{osname}/{arch}/xfreerdp"
            cand = self._helper.get_path(rel)
        else:
            cand = None

        if cand and os.path.exists(cand):
            if not os.access(cand, os.X_OK):
                try:
                    os.chmod(cand, 0o755)
                except Exception:
                    pass
            return cand

        # Fallback to PATH
        from shutil import which
        return which("xfreerdp") or "xfreerdp"

    def _get_freerdp_version(self, freerdp_path: str) -> Optional[str]:
        try:
            res = subprocess.run(
                [freerdp_path, "+version"],
                capture_output=True,
                text=True,
            )
            if res.returncode != 0:
                return None
            lines = [ln.strip() for ln in res.stdout.splitlines() if ln.strip()]
            if not lines:
                return None
            parts = lines[0].split()
            for token in parts:
                if re.match(r"^\d+\.\d+(\.\d+)?$", token):
                    return token
            return None
        except Exception as e:
            print(f"[FreeRDP] Error retrieving version: {e}")
            return None

    # ------------------------------------------------------------------
    # Command generation
    # ------------------------------------------------------------------

    def build_command(
        self,
        overrides: Optional[Dict[str, Any]] = None
    ) -> tuple[list[str], Optional[str], bool, bool]:
        overrides = overrides or {}

        def val(key: str, default: Any = None) -> Any:
            if key in overrides and overrides[key] not in ("", None):
                return overrides[key]
            return self._configuration.get(key, default)

        freerdp_path = self._binary_path()
        freerdp_version = self._get_freerdp_version(freerdp_path)
        major_version = int(freerdp_version.split(".")[0]) if freerdp_version else None

        cmd: list[str] = [freerdp_path]

        # Safe defaults
        cmd += [
            "/cert:ignore",     # TODO: later this could be toggled by config
            "/sec:nla",
            "-multitransport",
            "/timeout:30000",   # 30s
        ]

        debug_enabled = bool(val("log.enabled", False))
        if debug_enabled:
            cmd.append("/log-level:DEBUG")

        # ---- Core connection values ----
        server = val("general.host", "")
        port = val("general.port", 3389)
        username = val("general.username", "")
        password = val("general.password", "")
        domain = val("general.domain", "")

        # Display
        resolution = val("freerdp.display.resolution", "")
        use_all_mon = bool(val("freerdp.display.all", False))
        fullscreen = bool(val("freerdp.display.fullscreen", False))
        fit_window = bool(val("freerdp.display.fit", False))

        # Devices / audio
        play_sound = val("freerdp.devices.output", "Never")
        record_sound = val("freerdp.devices.input", "Never")
        printers = bool(val("freerdp.devices.printers", False))
        smart_cards = bool(val("freerdp.devices.smart_cards", False))
        ports_redirect = bool(val("freerdp.devices.ports", False))
        drives = bool(val("freerdp.devices.drives", False))

        # Experience
        clipboard = bool(val("freerdp.experience.clipboard", False))
        remotefx = bool(val("freerdp.experience.remotefx", False))
        smooth_fonts = bool(val("freerdp.experience.smooth_fonts", False))
        desktop_comp = bool(val("freerdp.experience.desktop_composition", False))
        full_window_drag = bool(val("freerdp.experience.full_window_drag", False))
        menu_anims = bool(val("freerdp.experience.menu_animations", False))
        disable_themes = bool(val("freerdp.experience.disable_themes", False))
        disable_wallpaper = bool(val("freerdp.experience.disable_wallpaper", False))
        show_cert_warning = bool(val("freerdp.experience.show_certificate_warning", False))

        # ---- Server / user ----
        if server:
            if port:
                cmd.append(f"/v:{server}:{int(port)}")
            else:
                cmd.append(f"/v:{server}")

        if username:
            cmd.append(f"/u:{username}")
        if domain:
            cmd.append(f"/d:{domain}")

        stdin_password: Optional[str] = None
        if password:
            if major_version and major_version >= 3:
                cmd.append("/from-stdin:force")
            else:
                cmd.append("/from-stdin")
            stdin_password = str(password)

        # ---- Display options ----
        if resolution:
            cmd.append(f"/size:{resolution}")
        if use_all_mon:
            cmd.append("/multimon")
        if fullscreen:
            cmd.append("/f")
        if fit_window:
            cmd.append("/smart-sizing")

        # ---- Audio ----
        if major_version and major_version < 3:
            if play_sound == "Never":
                cmd.append("/sound:off")
            elif play_sound == "On this computer":
                cmd.append("/sound:sys:alsa")
            elif play_sound == "On the remote computer":
                cmd.append("/sound:sys:rdpsnd")
        else:
            # 3.x audio-mode
            if play_sound == "Never":
                cmd.append("/audio-mode:2")
            elif play_sound == "On this computer":
                cmd.append("/audio-mode:0")
            elif play_sound == "On the remote computer":
                cmd.append("/audio-mode:1")

        # record_sound currently not handled in detail; can be extended later

        # ---- Devices ----
        if printers:
            cmd.append("/printer")
        if drives:
            cmd.append("/drives")
        if ports_redirect:
            cmd.append("/usb:auto")
        if smart_cards:
            # Simple: enable smartcard redirection; can tune later for v2/v3
            cmd.append("/smartcard")

        # ---- Experience ----
        if clipboard:
            cmd.append("+clipboard")
        if remotefx:
            cmd.append("/rfx /gfx /gfx-h264 /gdi:hw")
        if smooth_fonts:
            cmd.append("+fonts")
        if desktop_comp:
            cmd.append("+aero")
        if full_window_drag:
            cmd.append("+window-drag")
        if menu_anims:
            cmd.append("+menu-anims")
        if disable_themes:
            cmd.append("-themes")
        if disable_wallpaper:
            cmd.append("-wallpaper")

        # Debug safe-print
        if debug_enabled:
            self._logger.append(f"[FreeRDP] Generated command (xfreerdp {freerdp_version}):", channel=self._log_channel)
            safe = []
            for tok in cmd:
                if tok.startswith("/p:"):
                    safe.append("/p:********")
                else:
                    safe.append(tok)
            self._logger.append(" ".join(safe), channel=self._log_channel)

        return cmd, stdin_password, show_cert_warning, debug_enabled

    # ------------------------------------------------------------------
    # Public connect API
    # ------------------------------------------------------------------

    def connect(
        self,
        parent,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        High-level "connect now" entry point.

        Creates a progress dialog, spawns FreeRDPConnection, and handles
        success/failure/log windows with MsgBox + central Log.
        """
        cmd, stdin_password, show_cert_warning, debug_enabled = self.build_command(overrides)

        # Reset channel for this new attempt
        self._logger.clear(self._log_channel)

        # Progress dialog
        self._dialog = FreeRDPDialog(parent)
        self._dialog.canceled_by_user.connect(self._on_user_cancel)

        # Worker thread
        self._thread = FreeRDPConnection(
            cmd,
            parent=parent,
            show_cert_warning=show_cert_warning,
            stdin_password=stdin_password,
            debug_enabled=debug_enabled,
            logger=self._logger,
            log_channel=self._log_channel,
        )
        self._thread.connection_success.connect(lambda: self._on_success(parent))
        self._thread.connection_failed.connect(
            lambda title, details, raw: self._on_failed(parent, title, details, raw)
        )
        self._thread.connection_info.connect(self._on_info)

        self._thread.start()
        self._dialog.show()

    # ------------------------------------------------------------------
    # Internal handlers
    # ------------------------------------------------------------------

    def _on_info(self, line: str):
        _ = line
        return

    def _on_success(self, parent):
        if self._dialog:
            self._dialog.hide()
        MsgBox.show(
            parent=parent,
            title="Connected",
            message="Connection to the server was successful.",
            icon="info",
            buttons=("OK",),
            default="OK",
            icon_lookup_fn=self._helper.get_path,
        )

    def _on_failed(self, parent, title: str, details: str, raw_log: str):
        # raw_log is still there if you ever want special handling,
        # but the canonical log lives in self._logger / self._log_channel
        if self._dialog:
            self._dialog.hide()

        debug_enabled = bool(self._configuration.get("log.enabled", False))
        icon = "info" if title.lower().startswith("disconnected") else "error"

        if debug_enabled and self._logger.has_data(self._log_channel):
            buttons: Iterable[str] = ("Open log", "OK")
        else:
            buttons = ("OK")

        choice = MsgBox.show(
            parent=parent,
            title=title,
            message=details,
            icon=icon,
            buttons=buttons,
            default="OK",
            icon_lookup_fn=self._helper.get_path,
        )

        if choice == "Open log":
            self.show_log(parent)

    def _on_user_cancel(self):
        if self._thread and self._thread.isRunning():
            self._thread.stop()
            self._thread.wait()
        if self._dialog:
            self._dialog.hide()

    # ------------------------------------------------------------------
    # Log helpers
    # ------------------------------------------------------------------

    def show_log(self, parent):
        """
        Show the FreeRDP log via the central Log utility.
        """
        # focus becomes initial filter inside LogDialog
        self._logger.show(parent=parent, channel=self._log_channel)
