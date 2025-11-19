#!/usr/bin/env python3
# src/network/openvpn.py
from __future__ import annotations

import os
import base64
import signal
import subprocess
import threading
from typing import Optional, TYPE_CHECKING, Any, Dict, Callable

from PyQt5.QtCore import QObject, pyqtSignal, QThread, Qt
from PyQt5.QtWidgets import (
    QApplication,
    QProgressDialog,
    QPushButton,
)

from app.helper import Helper
from app.configuration import Configuration
from app.ui import MsgBox
from app.log import Log

if TYPE_CHECKING:
    from app.application import Application


# ---------------------------------------------------------------------------
# Worker thread
# ---------------------------------------------------------------------------

class OpenVPNConnection(QThread):
    connected = pyqtSignal()
    failed = pyqtSignal(str, str, str)  # title, details, raw_log
    info = pyqtSignal(str)

    def __init__(
        self,
        command: list[str],
        owner: "OpenVPN",
        logger: Optional[Log],
        log_channel: str = "openvpn",
        debug_enabled: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.command = command
        self._owner = owner
        self._logger = logger
        self._log_channel = log_channel
        self._debug_enabled = debug_enabled

        self._proc: Optional[subprocess.Popen] = None
        self._stop_flag = False
        self._connected_emitted = False

    def run(self):
        collected: list[str] = []
        text = ""

        try:
            env = os.environ.copy()

            self._proc = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                text=True,
                env=env,
                bufsize=1,
                universal_newlines=True,
            )

            # Expose process to owner for is_running()/stop()
            self._owner._proc = self._proc
            self._owner.stateChanged.emit("starting")

            def pump(stream):
                for line in iter(stream.readline, ""):
                    if self._stop_flag:
                        break
                    ln = line.rstrip()
                    if ln:
                        collected.append(ln)

                        # Central logger
                        if self._logger is not None:
                            self._logger.append(ln, channel=self._log_channel)

                        # Emit live info if desired
                        if self._debug_enabled:
                            self.info.emit(ln)

                        # Detect successful init
                        if "Initialization Sequence Completed" in ln:
                            if not self._connected_emitted:
                                self._connected_emitted = True
                                self._owner.stateChanged.emit("running")
                                self.connected.emit()
                try:
                    stream.close()
                except Exception:
                    pass

            t_out = threading.Thread(target=pump, args=(self._proc.stdout,))
            t_err = threading.Thread(target=pump, args=(self._proc.stderr,))
            t_out.start()
            t_err.start()

            rc = self._proc.wait()
            t_out.join()
            t_err.join()

            text = "\n".join(collected)

            # Reset process handle on owner
            self._owner._proc = None

            # Always clean up temporary files (auth file etc.)
            try:
                self._owner._cleanup_temp_files()
            except Exception:
                pass

            if self._stop_flag:
                # User-cancelled; do not treat as error
                self._owner.stateChanged.emit("stopped")
                return

            # If we already signaled connected, silently ignore later exit
            # (the app will show state via Stop/Disconnect actions).
            if self._connected_emitted:
                self._owner.stateChanged.emit("stopped")
                return

            # Connection failed before init completed
            self._owner.stateChanged.emit("error")

            # Try to classify a couple of common cases
            details = "OpenVPN failed to connect.\n\nOpen the detailed log for more information."
            title = "VPN connection failed"

            lowered = text.lower()
            if "auth_failed" in lowered or "authentication failed" in lowered:
                details = "Authentication failed.\n\nCheck your username and password."
            elif "cannot resolve host address" in lowered or "resolv" in lowered:
                details = "Could not resolve the VPN host.\n\nVerify the configured hostname and DNS."

            self.failed.emit(title, details, text)

        except Exception as e:
            self._owner._proc = None
            self._owner.stateChanged.emit("error")
            if not text:
                try:
                    text = "\n".join(collected)
                except Exception:
                    text = ""
            self.failed.emit(
                "Unexpected error",
                f"{type(e).__name__}: {e}",
                text,
            )

    # ------------------------------------------------------------------

    def stop(self):
        self._stop_flag = True
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass

# ---------------------------------------------------------------------------
# Connection progress dialog
# ---------------------------------------------------------------------------

class OpenVPNDialog(QProgressDialog):
    canceled_by_user = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Connecting to VPN...", "Cancel", 0, 0, parent)
        self.setWindowModality(Qt.WindowModal)
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowTitleHint
            | Qt.CustomizeWindowHint | Qt.WindowCloseButtonHint
        )
        self.setObjectName("OpenVPNDialog")
        self.setMinimumDuration(0)
        self.setAutoReset(False)
        self.setFixedWidth(300)

        btn = QPushButton("Cancel", self)
        btn.clicked.connect(self._on_cancel)
        self.setCancelButton(btn)

    def _on_cancel(self):
        self.canceled_by_user.emit()
        self.reject()

# ---------------------------------------------------------------------------
# High-level OpenVPN façade
# ---------------------------------------------------------------------------

class OpenVPN(QObject):

    stateChanged = pyqtSignal(str)  # "stopped", "starting", "running", "error"

    def __init__(
        self,
        helper: Optional[Helper] = None,
        configuration: Optional[Configuration] = None,
        logger: Optional[Log] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)

        # --- auto-wire from QApplication if not provided ---
        if helper is None or configuration is None or logger is None:
            app = QApplication.instance()
            if app is None:
                raise RuntimeError("OpenVPN must be created after QApplication/Application.")
            helper = helper or app.helper                      # type: ignore[attr-defined]
            configuration = configuration or app.configuration  # type: ignore[attr-defined]
            logger = logger or app.logger                      # type: ignore[attr-defined]

        # Helper
        self._helper: Helper = helper

        # Configuration
        self._configuration: Configuration = configuration
        self._configuration.label("network.openvpn", "OpenVPN")
        self._configuration.add(
            "network.openvpn.file",
            None,
            "file",
            label="Config File",
            filter="OpenVPN Config Files (*.ovpn);;All Files (*)",
            on_changed=self._on_config_file_changed,
            as_base64=True,
        )
        self._configuration.add("network.openvpn.auto", False, "checkbox", label="Auto Connect")
        self._configuration.add("network.openvpn.host", "", "text", label="Host")
        self._configuration.add("network.openvpn.port", 1194, "number", label="Port")
        self._configuration.add(
            "network.openvpn.global",
            False,
            "checkbox",
            label="Use Global Credentials",
            on_changed=self._on_global_changed,
        )
        self._configuration.add("network.openvpn.username", "", "text", label="Username")
        self._configuration.add("network.openvpn.password", "", "password", label="Password")
        self._configuration.add(
            "network.openvpn.certificate",
            None,
            "file",
            label="Certificate File",
            filter="Certificate Files (*.crt *.pem);;All Files (*)",
            as_base64=True,
        )
        self._configuration.add(
            "network.openvpn.key",
            None,
            "file",
            label="TLS Key File",
            filter="Key Files (*.key);;All Files (*)",
            as_base64=True,
        )

        # Save any new defaults
        self._configuration.save()

        # Logger
        self._logger: Log = logger
        self._log_channel = "openvpn"

        self._proc: Optional[subprocess.Popen] = None
        self._auth_file: Optional[str] = None
        self._last_error: str = ""

        # For UI connect()
        self._dialog: Optional[OpenVPNDialog] = None
        self._thread: Optional[OpenVPNConnection] = None

        self.stateChanged.emit("stopped")

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    def is_configured(self) -> bool:
        inline = self._configuration.get("network.openvpn.config_data")
        file_cfg = self._configuration.get("network.openvpn.file")
        return bool(inline or file_cfg)

    def auto_connect(self) -> bool:
        return bool(self._configuration.get("network.openvpn.auto"))

    def config_file(self) -> Optional[str]:
        cfg = self._configuration.get("network.openvpn.file")
        if not cfg:
            return None
        return str(cfg)

    def _runtime_dir(self) -> str:
        root = self._helper.root_dir
        run_dir = os.path.join(root, "runtime")
        os.makedirs(run_dir, exist_ok=True)
        return run_dir

    def _on_config_file_changed(self, path: str) -> None:
        if not path or not os.path.isfile(path):
            return

        host: Optional[str] = None
        port: Optional[int] = None
        auth_user_pass = False
        ca_rel: Optional[str] = None
        key_rel: Optional[str] = None

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith("#") or line.startswith(";"):
                        continue
                    parts = line.split()
                    if not parts:
                        continue

                    key = parts[0].lower()

                    if key == "remote" and len(parts) >= 2:
                        host = parts[1]
                        if len(parts) >= 3:
                            try:
                                port = int(parts[2])
                            except ValueError:
                                pass
                    elif key == "auth-user-pass":
                        auth_user_pass = True
                    elif key == "ca" and len(parts) >= 2:
                        ca_rel = parts[1]

        except Exception as e:
            self._logger.append(
                f"[OpenVPN] Failed to parse config '{path}': {e}",
                channel=self._log_channel,
            )
            return

        # --- Apply values into configuration + visible widgets ---

        if host:
            self._configuration.reload("network.openvpn.host", host)
        if port is not None:
            self._configuration.reload("network.openvpn.port", port)
        if auth_user_pass:
            self._configuration.reload("network.openvpn.global", True)
            self._on_global_changed(True)

        # CA certificate → base64 into network.openvpn.certificate
        if ca_rel:
            cfg_dir = os.path.dirname(path)
            ca_path = os.path.join(cfg_dir, ca_rel)
            if os.path.isfile(ca_path):
                try:
                    with open(ca_path, "rb") as f:
                        data = f.read()
                    b64 = base64.b64encode(data).decode("ascii")

                    fname = os.path.basename(ca_path)
                    stored = f"{fname}::{b64}"

                    self._configuration.reload("network.openvpn.certificate", stored)
                    self._logger.append(
                        f"[OpenVPN] Loaded CA certificate from '{ca_path}' into configuration.",
                        channel=self._log_channel,
                    )
                except Exception as e:
                    self._logger.append(
                        f"[OpenVPN] Failed to load CA certificate '{ca_path}': {e}",
                        channel=self._log_channel,
                    )

        # TLS key file → base64 into network.openvpn.certificate
        if key_rel:
            cfg_dir = os.path.dirname(path)
            key_path = os.path.join(cfg_dir, key_rel)
            if os.path.isfile(key_path):
                try:
                    with open(key_path, "rb") as f:
                        data = f.read()
                    b64 = base64.b64encode(data).decode("ascii")

                    fname = os.path.basename(key_path)
                    stored = f"{fname}::{b64}"

                    self._configuration.reload("network.openvpn.key", stored)
                    self._logger.append(
                        f"[OpenVPN] Loaded TLS key from '{key_path}' into configuration.",
                        channel=self._log_channel,
                    )
                except Exception as e:
                    self._logger.append(
                        f"[OpenVPN] Failed to load TLS key '{key_path}': {e}",
                        channel=self._log_channel,
                    )

        self._configuration.save()

        self._logger.append(
            f"[OpenVPN] Parsed config '{os.path.basename(path)}': "
            f"host={host or '-'} port={port or '-'} auth-user-pass={auth_user_pass} ca={ca_rel or '-'}",
            channel=self._log_channel,
        )

    def _on_global_changed(self, value: Any) -> None:
        use_global = bool(value)
        try:
            self._configuration.visibility("network.openvpn.username", not use_global)
            self._configuration.visibility("network.openvpn.password", not use_global)
        except Exception as e:
            self._logger.append(
                f"[OpenVPN] _on_global_changed error: {e}",
                channel=self._log_channel,
            )

    # ------------------------------------------------------------------
    # Binary location
    # ------------------------------------------------------------------

    def _binary_path(self) -> str:
        osname = self._helper.get_os()
        arch = self._helper.get_arch()

        if osname in ("macos", "linux"):
            rel = f"bin/openvpn/{osname}/{arch}/openvpn"
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
        return which("openvpn") or "openvpn"

    # ------------------------------------------------------------------
    # Credential helpers
    # ------------------------------------------------------------------

    def _resolve_credentials(self, overrides: Optional[Dict[str, Any]] = None) -> tuple[str, str]:
        overrides = overrides or {}

        def val(key: str, default: Any = None) -> Any:
            if key in overrides and overrides[key] not in ("", None):
                return overrides[key]
            return self._configuration.get(key, default)

        use_global = bool(val("network.openvpn.global", False))

        if use_global:
            username = val("general.username") or val("network.openvpn.username", "")
            password = val("general.password") or val("network.openvpn.password", "")
        else:
            username = val("network.openvpn.username") or val("general.username", "")
            password = val("network.openvpn.password") or val("general.password", "")

        return str(username or ""), str(password or "")

    def _write_auth_file(self, username: str, password: str) -> str:
        run_dir = self._runtime_dir()
        path = os.path.join(run_dir, "openvpn-auth.txt")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(username + "\n" + password + "\n")
            os.chmod(path, 0o600)
            self._auth_file = path
            self._logger.append(f"[OpenVPN] Created auth file at {path}", channel=self._log_channel)
        except Exception as e:
            self._logger.append(f"[OpenVPN] Failed to create auth file: {e}", channel=self._log_channel)
        return path

    def _materialize_config(self) -> Optional[str]:
        """
        Create a temporary .ovpn file in runtime/ from inline base64 config,
        or fall back to the original path if inline config is missing.
        """
        stored = self._configuration.get("network.openvpn.config_data")
        if not stored:
            # Fallback: use original on-disk config if still set
            return self.config_file()

        try:
            import base64
            if "::" in stored:
                name, b64 = stored.split("::", 1)
            else:
                name, b64 = "openvpn.ovpn", stored

            data = base64.b64decode(b64)
            run_dir = self._runtime_dir()
            cfg_path = os.path.join(run_dir, name)
            with open(cfg_path, "wb") as f:
                f.write(data)
            return cfg_path
        except Exception as e:
            self._logger.append(
                f"[OpenVPN] Failed to materialize inline config: {e}",
                channel=self._log_channel,
            )
            return None

    def _materialize_aux(self, cfg_key: str, default_name: str) -> Optional[str]:
        """
        Create a file in runtime/ from a 'name::base64' value stored in configuration.
        If only base64 is stored (legacy), use default_name.
        """
        stored = self._configuration.get(cfg_key)
        if not stored:
            return None

        try:
            import base64
            if "::" in stored:
                name, b64 = stored.split("::", 1)
            else:
                name, b64 = default_name, stored

            data = base64.b64decode(b64)
            run_dir = self._runtime_dir()
            path = os.path.join(run_dir, name)
            with open(path, "wb") as f:
                f.write(data)
            return path
        except Exception as e:
            self._logger.append(
                f"[OpenVPN] Failed to materialize {cfg_key}: {e}",
                channel=self._log_channel,
            )
            return None

    def _cleanup_temp_files(self) -> None:
        if self._auth_file and os.path.exists(self._auth_file):
            try:
                os.remove(self._auth_file)
            except Exception:
                pass
        self._auth_file = None

    # ------------------------------------------------------------------
    # Command generation
    # ------------------------------------------------------------------

    def build_command(
        self,
        overrides: Optional[Dict[str, Any]] = None
    ) -> list[str]:
        overrides = overrides or {}

        def val(key: str, default: Any = None) -> Any:
            if key in overrides and overrides[key] not in ("", None):
                return overrides[key]
            return self._configuration.get(key, default)

        bin_path = self._binary_path()

        # Materialize config + CA + key into runtime
        cfg_path = self._materialize_config()
        if not cfg_path:
            # Last fallback: original on-disk config
            cfg_path = self.config_file()

        # Even if we don't pass these on CLI, ensure the files exist
        self._materialize_aux("network.openvpn.certificate", "ca.crt")
        self._materialize_aux("network.openvpn.key", "ta.key")

        cmd: list[str] = [bin_path]
        if cfg_path:
            cmd += ["--config", cfg_path]

        # Optional host/port override
        host = val("network.openvpn.host", "")
        port = val("network.openvpn.port", 1194)
        if host:
            try:
                port_int = int(port) if port is not None else 1194
            except ValueError:
                port_int = 1194
            cmd += ["--remote", str(host), str(port_int)]

        # Credentials → auth-user-pass file (see §3)
        username, password = self._resolve_credentials(overrides)
        if username and password:
            auth_file = self._write_auth_file(username, password)
            cmd += ["--auth-user-pass", auth_file]

        return cmd

    # ------------------------------------------------------------------
    # Old synchronous process management (still used by ensure_connected)
    # ------------------------------------------------------------------

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def last_error(self) -> str:
        return self._last_error

    def start(self) -> bool:
        """
        Start OpenVPN if configured and not already running.
        (Legacy synchronous variant; does not show UI.)
        """
        self._last_error = ""

        if not self.is_configured():
            self._last_error = "OpenVPN config file is not set."
            self._logger.append(self._last_error, channel=self._log_channel)
            self.stateChanged.emit("error")
            return False

        if self.is_running():
            self._logger.append(
                "[OpenVPN] start() called but process is already running.",
                channel=self._log_channel,
            )
            return True

        cmd = self.build_command()

        if not cmd:
            self._last_error = "OpenVPN command is empty."
            self._logger.append(self._last_error, channel=self._log_channel)
            self.stateChanged.emit("error")
            return False

        self.stateChanged.emit("starting")
        self._logger.append(f"[OpenVPN] Starting (legacy): {' '.join(cmd)}", channel=self._log_channel)

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.stateChanged.emit("running")
            self._logger.append("[OpenVPN] Process started successfully (legacy).", channel=self._log_channel)
            return True
        except Exception as e:
            self._last_error = str(e)
            self._proc = None
            self.stateChanged.emit("error")
            self._logger.append(f"[OpenVPN] Failed to start (legacy): {e}", channel=self._log_channel)
            return False

    def stop(self) -> None:
        """
        Stop OpenVPN if running.
        """
        if not self.is_running():
            self._logger.append(
                "[OpenVPN] stop() called but process is not running.",
                channel=self._log_channel,
            )
            self._proc = None
            self._cleanup_temp_files()
            self.stateChanged.emit("stopped")
            return

        self._logger.append("[OpenVPN] Stopping OpenVPN process...", channel=self._log_channel)

        try:
            if self._helper.get_os() == "windows":
                self._proc.terminate()
            else:
                self._proc.send_signal(signal.SIGTERM)
        except Exception as e:
            self._logger.append(
                f"[OpenVPN] Error while stopping: {e}",
                channel=self._log_channel,
            )
        finally:
            self._proc = None
            self._cleanup_temp_files()
            self.stateChanged.emit("stopped")
            self._logger.append("[OpenVPN] Process stopped.", channel=self._log_channel)

    def ensure_connected(self) -> tuple[bool, str]:
        """
        Legacy high-level helper (no UI).

        - If not configured or auto-connect disabled: (True, "")
        - If already running: (True, "")
        - Else: try start() and return (ok, error_message)
        """
        if not self.is_configured() or not self.auto_connect():
            return True, ""

        if self.is_running():
            return True, ""

        ok = self.start()
        if not ok:
            return False, self._last_error

        return True, ""

    # ------------------------------------------------------------------
    # New UI-based connect() (like FreeRDP.connect)
    # ------------------------------------------------------------------

    def connect(
        self,
        parent,
        overrides: Optional[Dict[str, Any]] = None,
        on_success: Optional[Callable[[], None]] = None,
    ) -> None:

        # If not configured, show error dialog
        if not self.is_configured():
            MsgBox.show(
                parent=parent,
                title="OpenVPN",
                message="OpenVPN config file is not set.",
                icon="error",
                buttons=("OK",),
                default="OK",
                icon_lookup_fn=self._helper.get_path,
            )
            return

        # If already running, just invoke the callback (if any) and exit
        if self.is_running():
            if callable(on_success):
                on_success()
            return

        cmd = self.build_command(overrides)

        # Reset channel for this new attempt
        self._logger.clear(self._log_channel)

        debug_enabled = bool(self._configuration.get("log.enabled", False))
        if debug_enabled:
            self._logger.append(f"[OpenVPN] Generated command:", channel=self._log_channel)
            self._logger.append(" ".join(cmd), channel=self._log_channel)

        # Progress dialog
        self._dialog = OpenVPNDialog(parent)
        self._dialog.canceled_by_user.connect(self._on_user_cancel)

        # Worker thread
        self._thread = OpenVPNConnection(
            cmd,
            owner=self,
            logger=self._logger,
            log_channel=self._log_channel,
            debug_enabled=debug_enabled,
            parent=parent,
        )
        self._thread.connected.connect(lambda: self._on_success(parent, on_success))
        self._thread.failed.connect(
            lambda title, details, raw: self._on_failed(parent, title, details, raw)
        )
        self._thread.info.connect(self._on_info)

        self._thread.start()
        self._dialog.show()

    # ------------------------------------------------------------------
    # Internal handlers for UI connect()
    # ------------------------------------------------------------------

    def _on_info(self, line: str):
        # Hook if you ever want to update the dialog with live status
        _ = line
        return

    def _on_success(self, parent, on_success: Optional[Callable[[], None]] = None):
        if self._dialog:
            self._dialog.hide()
        MsgBox.show(
            parent=parent,
            title="VPN connected",
            message="OpenVPN connection established successfully.",
            icon="info",
            buttons=("OK",),
            default="OK",
            icon_lookup_fn=self._helper.get_path,
        )

        if callable(on_success):
            on_success()

    def _on_failed(self, parent, title: str, details: str, raw_log: str):
        _ = raw_log  # canonical log is already in self._logger
        if self._dialog:
            self._dialog.hide()

        debug_enabled = bool(self._configuration.get("log.enabled", False))

        if debug_enabled and self._logger.has_data(self._log_channel):
            buttons = ("Open log", "OK")
        else:
            buttons = ("OK",)

        choice = MsgBox.show(
            parent=parent,
            title=title,
            message=details,
            icon="error",
            buttons=buttons,
            default="OK",
            icon_lookup_fn=self._helper.get_path,
        )

        if choice == "Open log":
            self._logger.show(parent=parent, channel=self._log_channel)

    def _on_user_cancel(self):
        if self._thread and self._thread.isRunning():
            self._thread.stop()
            self._thread.wait()
        if self._dialog:
            self._dialog.hide()
        self.stop()
