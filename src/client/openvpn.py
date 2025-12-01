#!/usr/bin/env python3
# src/client/openvpn.py
from __future__ import annotations

import os
import base64
import time
import shlex
import signal
import subprocess
import threading
from typing import Optional, TYPE_CHECKING, Any, Dict, Callable, Set

from PyQt5.QtCore import QObject, pyqtSignal, QThread, Qt
from PyQt5.QtWidgets import (
    QApplication,
    QProgressDialog,
    QPushButton,
)

from app.helper import Helper
from app.ui import MsgBox
from app.log import Log

if TYPE_CHECKING:
    # For type hints only, avoids circular import at runtime
    from app.application import Application
    from app.configuration import Configuration


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

        # macOS elevated mode tracking
        self._root_pid: Optional[int] = None
        self._log_path: Optional[str] = None
        self._pid_path: Optional[str] = None

    def run(self):
        collected: list[str] = []
        text = ""

        try:
            env = os.environ.copy()
            osname = self._owner._helper.get_os()
            is_macos = (osname == "macos")

            if is_macos:
                # ----------------------------------------------------------
                # macOS path: run OpenVPN via AppleScript with root
                # ----------------------------------------------------------
                run_dir = self._owner._runtime_dir()
                self._log_path = os.path.join(run_dir, "openvpn.log")
                self._pid_path = os.path.join(run_dir, "openvpn.pid")

                # Clean previous log/pid
                for p in (self._log_path, self._pid_path):
                    try:
                        if p and os.path.exists(p):
                            os.remove(p)
                    except Exception:
                        pass

                # Build shell command:
                #   cd runtime &&
                #   <openvpn command> >> openvpn.log 2>&1 &
                #   echo $! > openvpn.pid
                shell_cmd = " ".join(shlex.quote(arg) for arg in self.command)
                sh = (
                    f"cd {shlex.quote(run_dir)}; "
                    f"{shell_cmd} >> {shlex.quote(self._log_path)} 2>&1 & "
                    f"echo $! > {shlex.quote(self._pid_path)}"
                )

                # Escape for AppleScript string literal
                # (Escape backslashes and double quotes)
                as_cmd = sh.replace("\\", "\\\\").replace('"', '\\"')
                applescript = (
                    f'do shell script "{as_cmd}" with administrator privileges'
                )

                self._logger.append(
                    f"[OpenVPN] macOS elevated launch via AppleScript:\n{sh}",
                    channel=self._log_channel,
                    level="debug",
                )

                # This osascript call returns quickly after the background job is started.
                self._proc = subprocess.Popen(
                    ["osascript", "-e", applescript],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                    bufsize=1,
                    universal_newlines=True,
                )

                # Owner only really cares about the "real" OpenVPN, but we still expose _proc
                self._owner._proc = self._proc
                self._owner.stateChanged.emit("starting")

                # Wait for osascript to finish starting the background process
                osa_stdout, osa_stderr = self._proc.communicate()
                self._logger.append(
                    f"[OpenVPN] osascript exited, stdout={osa_stdout!r}, stderr={osa_stderr!r}",
                    channel=self._log_channel,
                    level="debug",
                )

                # Now we follow the log + pid to infer connection state
                last_line_count = 0
                start_time = time.time()

                self._owner.stateChanged.emit("starting")

                while True:
                    if self._stop_flag:
                        self._logger.append(
                            "[OpenVPN] Stop flag set while monitoring macOS OpenVPN log.",
                            channel=self._log_channel,
                            level="debug",
                        )
                        break

                    # Read PID if available
                    if self._root_pid is None and self._pid_path and os.path.exists(self._pid_path):
                        try:
                            with open(self._pid_path, "r", encoding="utf-8") as f:
                                pid_str = f.read().strip()
                            if pid_str:
                                self._root_pid = int(pid_str)
                                self._logger.append(
                                    f"[OpenVPN] macOS elevated OpenVPN PID={self._root_pid}",
                                    channel=self._log_channel,
                                    level="debug",
                                )
                        except Exception as e:
                            self._logger.append(
                                f"[OpenVPN] Failed to read OpenVPN PID file: {e}",
                                channel=self._log_channel,
                                level="warning",
                            )

                    # Read any new log lines
                    if self._log_path and os.path.exists(self._log_path):
                        try:
                            with open(self._log_path, "r", encoding="utf-8", errors="ignore") as f:
                                lines = f.readlines()
                            new_lines = lines[last_line_count:]
                            last_line_count = len(lines)

                            for raw in new_lines:
                                ln = raw.rstrip()
                                if not ln:
                                    continue
                                collected.append(ln)

                                if self._logger is not None:
                                    self._logger.append(ln, channel=self._log_channel)

                                if self._debug_enabled:
                                    self.info.emit(ln)

                                if "Initialization Sequence Completed" in ln:
                                    if not self._connected_emitted:
                                        self._logger.append(
                                            "[OpenVPN] Detected successful connection (macOS elevated).",
                                            channel=self._log_channel,
                                            level="info",
                                        )
                                        self._connected_emitted = True
                                        self._owner.stateChanged.emit("running")
                                        self.connected.emit()
                        except Exception as e:
                            self._logger.append(
                                f"[OpenVPN] Error reading macOS OpenVPN log: {e}",
                                channel=self._log_channel,
                                level="warning",
                            )

                    # Check if the root OpenVPN process is still alive (if we know PID)
                    alive = None
                    if self._root_pid is not None:
                        try:
                            ps = subprocess.run(
                                ["ps", "-p", str(self._root_pid), "-o", "pid="],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL,
                                text=True,
                            )
                            alive = bool(ps.stdout.strip())
                        except Exception as e:
                            self._logger.append(
                                f"[OpenVPN] ps check failed for PID {self._root_pid}: {e}",
                                channel=self._log_channel,
                                level="warning",
                            )

                    now = time.time()
                    elapsed = now - start_time

                    # Decide if we should break out of monitoring loop
                    if self._connected_emitted:
                        # If connected and process is no longer alive, we're done
                        if alive is False:
                            self._logger.append(
                                "[OpenVPN] macOS elevated OpenVPN process exited after successful connection.",
                                channel=self._log_channel,
                                level="info",
                            )
                            break
                    else:
                        # Not connected yet – see if process already exited or we timed out
                        if alive is False and elapsed > 3:
                            self._logger.append(
                                "[OpenVPN] macOS elevated OpenVPN process exited before connection.",
                                channel=self._log_channel,
                                level="error",
                            )
                            break
                        if elapsed > 30:
                            self._logger.append(
                                "[OpenVPN] macOS elevated OpenVPN connection timeout (no 'Initialization Sequence Completed').",
                                channel=self._log_channel,
                                level="error",
                            )
                            break

                    time.sleep(0.3)

                text = "\n".join(collected)

            else:
                # ----------------------------------------------------------
                # Non-macOS path: original behavior with direct Popen
                # ----------------------------------------------------------
                self._logger.append(
                    f"[OpenVPN] Starting OpenVPN with command: {' '.join(self.command)}",
                    channel=self._log_channel,
                    level="debug",
                )
                self._proc = subprocess.Popen(
                    self.command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    stdin=subprocess.PIPE,
                    text=True,
                    env=env,
                    bufsize=1,
                    universal_newlines=True,
                    cwd=self._owner._runtime_dir(),
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
                                    self._logger.append(
                                        "[OpenVPN] Detected successful connection.",
                                        channel=self._log_channel,
                                        level="info",
                                    )
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
                self._logger.append(
                    f"[OpenVPN] OpenVPN subprocess exited with return code: {rc}",
                    channel=self._log_channel,
                    level="debug",
                )
                t_out.join()
                t_err.join()

                text = "\n".join(collected)

            # ------------------------------------------------------
            # Common cleanup / result handling for both paths
            # ------------------------------------------------------
            # Reset process handle on owner
            self._owner._proc = None

            # Always clean up temporary files (auth file etc.)
            try:
                self._owner._cleanup_temp_files()
            except Exception as e:
                self._logger.append(
                    f"[OpenVPN] Failed to clean up temporary files: {e}",
                    channel=self._log_channel,
                    level="warning",
                )

            if self._stop_flag:
                # User-cancelled; do not treat as error
                self._logger.append(
                    "[OpenVPN] Connection cancelled by user.",
                    channel=self._log_channel,
                    level="info",
                )
                self._owner.stateChanged.emit("stopped")
                return

            # If we already signaled connected, silently ignore later exit
            if self._connected_emitted:
                self._logger.append(
                    "[OpenVPN] Process exited after successful connection.",
                    channel=self._log_channel,
                    level="info",
                )
                self._owner.stateChanged.emit("stopped")
                return

            # Connection failed before init completed
            self._logger.append(
                "[OpenVPN] Connection failed before initialization completed.",
                channel=self._log_channel,
                level="error",
            )
            self._owner.stateChanged.emit("error")

            # Try to classify a couple of common cases
            details = "OpenVPN failed to connect.\n\nOpen the detailed log for more information."
            title = "VPN connection failed"

            lowered = text.lower()
            if "auth_failed" in lowered or "authentication failed" in lowered:
                details = "Authentication failed.\n\nCheck your username and password."
            elif "cannot resolve host address" in lowered or "resolv" in lowered:
                details = "Could not resolve the VPN host.\n\nVerify the configured hostname and DNS."
            elif "cannot allocate tun/tap dev" in lowered or "opening utun" in lowered or "failed to open utun device" in lowered:
                details = (
                    "OpenVPN could not create a VPN tunnel (TUN/TAP/utun interface).\n\n"
                    "On macOS this usually means the process does not have permission to "
                    "create network tunnel devices.\n\n"
                    "PyRDPConnect now attempts to launch OpenVPN with administrator privileges "
                    "on macOS. If this error persists, please verify system security settings "
                    "and that you allowed the helper when prompted."
                )

            self.failed.emit(title, details, text)

        except Exception as e:
            self._logger.append(
                f"[OpenVPN] Exception in OpenVPNConnection.run: {e}",
                channel=self._log_channel,
                level="error",
            )
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

    def stop(self):
        self._stop_flag = True

        osname = self._owner._helper.get_os()
        is_macos = (osname == "macos")

        if is_macos and self._root_pid is not None:
            # Ask macOS to kill the root-owned OpenVPN process
            try:
                kill_cmd = f"kill {self._root_pid}"
                as_cmd = kill_cmd.replace("\\", "\\\\").replace('"', '\\"')
                applescript = f'do shell script "{as_cmd}" with administrator privileges'
                self._logger.append(
                    f"[OpenVPN] Requesting termination of elevated OpenVPN PID {self._root_pid} via AppleScript.",
                    channel=self._log_channel,
                    level="debug",
                )
                proc = subprocess.Popen(
                    ["osascript", "-e", applescript],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                # Wait a bit for the kill to complete (or fail)
                try:
                    out, err = proc.communicate(timeout=10)
                except Exception:
                    out, err = "", ""
                self._logger.append(
                    f"[OpenVPN] AppleScript kill result: returncode={proc.returncode}, "
                    f"stdout={out!r}, stderr={err!r}",
                    channel=self._log_channel,
                    level="debug",
                )

                # Double-check with ps if the process is still alive
                try:
                    ps = subprocess.run(
                        ["ps", "-p", str(self._root_pid), "-o", "pid="],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        text=True,
                    )
                    alive = bool(ps.stdout.strip())
                except Exception as e:
                    alive = None
                    self._logger.append(
                        f"[OpenVPN] ps check failed after kill attempt: {e}",
                        channel=self._log_channel,
                        level="warning",
                    )

                if alive:
                    self._logger.append(
                        f"[OpenVPN] WARNING: Elevated OpenVPN PID {self._root_pid} still appears alive after kill.",
                        channel=self._log_channel,
                        level="warning",
                    )
                else:
                    self._logger.append(
                        f"[OpenVPN] Elevated OpenVPN PID {self._root_pid} no longer appears in ps after kill.",
                        channel=self._log_channel,
                        level="info",
                    )

            except Exception as e:
                self._logger.append(
                    f"[OpenVPN] Failed to terminate elevated OpenVPN PID {self._root_pid}: {e}",
                    channel=self._log_channel,
                    level="error",
                )

            # We tried; avoid reusing a stale PID
            self._root_pid = None

        # Original behavior for directly-owned subprocess
        if self._proc:
            try:
                self._logger.append(
                    "[OpenVPN] Terminating OpenVPN subprocess from stop().",
                    channel=self._log_channel,
                    level="debug",
                )
                self._proc.terminate()
            except Exception as e:
                self._logger.append(
                    f"[OpenVPN] Exception terminating subprocess in stop(): {e}",
                    channel=self._log_channel,
                    level="error",
                )


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
        self._configuration.label("vpn.openvpn", "OpenVPN")
        self._configuration.add(
            "vpn.openvpn.file",
            None,
            "file",
            label="Config File",
            filter="OpenVPN Config Files (*.ovpn);;All Files (*)",
            on_changed=self._on_config_file_changed,
            as_base64=True,
        )
        self._configuration.add("vpn.openvpn.auto", False, "checkbox", label="Auto Connect")
        self._configuration.add("vpn.openvpn.host", "", "text", label="Host")
        self._configuration.add("vpn.openvpn.port", 1194, "number", label="Port")
        self._configuration.add(
            "vpn.openvpn.global",
            False,
            "checkbox",
            label="Use Global Credentials",
            on_changed=self._on_global_changed,
        )
        self._configuration.add("vpn.openvpn.username", "", "text", label="Username")
        self._configuration.add("vpn.openvpn.password", "", "password", label="Password")
        self._configuration.add(
            "vpn.openvpn.certificate",
            None,
            "file",
            label="Certificate File",
            filter="Certificate Files (*.crt *.pem);;All Files (*)",
            as_base64=True,
        )
        self._configuration.add(
            "vpn.openvpn.key",
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

        # Track all temporary files created in runtime (ovpn, cert, key, auth)
        self._temp_files: set[str] = set()

        # For UI connect()
        self._dialog: Optional[OpenVPNDialog] = None
        self._thread: Optional[OpenVPNConnection] = None

        self.stateChanged.emit("stopped")

        # --- DEBUG: initial config snapshot ---
        cfg_val = self._configuration.get("vpn.openvpn.file")
        self._logger.append(f"[OpenVPN] __init__: vpn.openvpn.file type={type(cfg_val)} value={repr(cfg_val)[:200]}", channel=self._log_channel, level="debug")

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    def is_configured(self) -> bool:
        cfg = self._configuration.get("vpn.openvpn.file")
        configured = bool(cfg)
        self._logger.append(f"[OpenVPN] is_configured(): configured={configured}, type={type(cfg)}, value={repr(cfg)[:200]}", channel=self._log_channel, level="debug")
        return configured

    def auto_connect(self) -> bool:
        val = bool(self._configuration.get("vpn.openvpn.auto"))
        self._logger.append(f"[OpenVPN] auto_connect(): {val}", channel=self._log_channel, level="debug")
        return val

    def config_file(self) -> Optional[str]:
        cfg = self._configuration.get("vpn.openvpn.file")
        self._logger.append(f"[OpenVPN] config_file(): raw value={repr(cfg)[:200]}", channel=self._log_channel, level="debug")
        if not cfg:
            return None
        return str(cfg)

    def _runtime_dir(self) -> str:
        root = self._helper.root_dir
        run_dir = os.path.join(root, "runtime")
        os.makedirs(run_dir, exist_ok=True)
        return run_dir

    def _register_temp(self, path: str) -> None:
        if path:
            self._temp_files.add(path)
            self._logger.append(f"[OpenVPN] Registered temp file: {path}", channel=self._log_channel, level="debug")

    def _on_config_file_changed(self, value: Any) -> None:
        self._logger.append(f"[OpenVPN] _on_config_file_changed called with type={type(value)}, value={repr(value)[:200]}", channel=self._log_channel, level="debug")
        host: Optional[str] = None
        port: Optional[int] = None
        auth_user_pass = False
        ca_rel: Optional[str] = None
        key_rel: Optional[str] = None

        text: Optional[str] = None
        cfg_path_for_rel: Optional[str] = None

        if isinstance(value, str) and "::" in value:
            try:
                _, b64 = value.split("::", 1)
                self._logger.append(f"[DEBUG OpenVPN] Decoding string-based config, b64 length={len(b64)}", channel=self._log_channel, level="debug")
                data = base64.b64decode(b64)
                text = data.decode("utf-8", errors="ignore")
            except Exception as e:
                self._logger.append(f"[DEBUG OpenVPN] Exception decoding string value in _on_config_file_changed: {e}", channel=self._log_channel, level="error")
                self._logger.append(
                    f"[OpenVPN] Failed to decode inline config (string) in _on_config_file_changed: {e}",
                    channel=self._log_channel,
                )

        elif isinstance(value, dict):
            try:
                self._logger.append(f"[DEBUG OpenVPN] Decoding dict-based config in _on_config_file_changed", channel=self._log_channel, level="debug")
                b64 = (
                    value.get("data")
                    or value.get("base64")
                    or value.get("b64")
                    or value.get("file")
                    or value.get("value")
                    or ""
                )
                if b64:
                    self._logger.append(f"[DEBUG OpenVPN] Decoding dict-based config, b64 length={len(b64)}", channel=self._log_channel, level="debug")
                    data = base64.b64decode(b64)
                    text = data.decode("utf-8", errors="ignore")
            except Exception as e:
                self._logger.append(f"[DEBUG OpenVPN] Exception decoding dict value in _on_config_file_changed: {e}", channel=self._log_channel, level="error")

        if not text:
            self._logger.append(f"[DEBUG OpenVPN] No text decoded in _on_config_file_changed, returning early.", channel=self._log_channel, level="debug")
            return

        self._logger.append(f"[DEBUG OpenVPN] _on_config_file_changed: first 200 chars of config:\n{text[:200]}", channel=self._log_channel, level="debug")

        try:
            for raw in text.splitlines():
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
                elif key in ("tls-auth", "tls-crypt") and len(parts) >= 2:
                    key_rel = parts[1]
        except Exception as e:
            self._logger.append(f"[DEBUG OpenVPN] Exception parsing config text in _on_config_file_changed: {e}", channel=self._log_channel, level="error")
            return

        self._logger.append(f"[DEBUG OpenVPN] _on_config_file_changed: Parsed values from config file.", channel=self._log_channel, level="debug")
        self._logger.append(f"[DEBUG OpenVPN] host={host}, port={port}, auth_user_pass={auth_user_pass}, ca_rel={ca_rel}, key_rel={key_rel}", channel=self._log_channel, level="debug")

        # --- Apply values into configuration + visible widgets ---

        if host:
            self._configuration.reload("vpn.openvpn.host", host)
        if port is not None:
            self._configuration.reload("vpn.openvpn.port", port)
        if auth_user_pass:
            self._configuration.reload("vpn.openvpn.global", True)
            self._on_global_changed(True)

        # (CA/TLS auto-import only when we know cfg_path_for_rel; currently None)

        self._configuration.save()

        self._logger.append(
            "[OpenVPN] Parsed config: "
            f"host={host or '-'} port={port or '-'} auth-user-pass={auth_user_pass} "
            f"ca={ca_rel or '-'} tls={key_rel or '-'}",
            channel=self._log_channel,
        )

    def _on_global_changed(self, value: Any) -> None:
        use_global = bool(value)
        self._logger.append(f"[DEBUG OpenVPN] _on_global_changed called with value={value} interpreted as use_global={use_global}", channel=self._log_channel, level="debug")
        try:
            self._configuration.visibility("vpn.openvpn.username", not use_global)
            self._configuration.visibility("vpn.openvpn.password", not use_global)
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
        self._logger.append(f"[DEBUG OpenVPN] _binary_path(): os={osname}, arch={arch}", channel=self._log_channel, level="debug")

        if osname in ("macos", "linux"):
            rel = f"bin/openvpn/{osname}/{arch}/openvpn"
            cand = self._helper.get_path(rel)
        else:
            cand = None

        if cand and os.path.exists(cand):
            if not os.access(cand, os.X_OK):
                try:
                    os.chmod(cand, 0o755)
                except Exception as e:
                    self._logger.append(f"[DEBUG OpenVPN] chmod failed on {cand}: {e}", channel=self._log_channel, level="warning")
            self._logger.append(f"[DEBUG OpenVPN] Using bundled openvpn binary at: {cand}", channel=self._log_channel, level="debug")
            return cand

        from shutil import which
        resolved = which("openvpn") or "openvpn"
        self._logger.append(f"[DEBUG OpenVPN] Using PATH openvpn binary: {resolved}", channel=self._log_channel, level="debug")
        return resolved

    # ------------------------------------------------------------------
    # Credential helpers
    # ------------------------------------------------------------------

    def _resolve_credentials(self, overrides: Optional[Dict[str, Any]] = None) -> tuple[str, str]:
        overrides = overrides or {}

        def val(key: str, default: Any = None) -> Any:
            if key in overrides and overrides[key] not in ("", None):
                return overrides[key]
            return self._configuration.get(key, default)

        use_global = bool(val("vpn.openvpn.global", False))
        self._logger.append(f"[DEBUG OpenVPN] _resolve_credentials: use_global={use_global}", channel=self._log_channel, level="debug")

        if use_global:
            username = val("general.username") or val("vpn.openvpn.username", "")
            password = val("general.password") or val("vpn.openvpn.password", "")
        else:
            username = val("vpn.openvpn.username") or val("general.username", "")
            password = val("vpn.openvpn.password") or val("general.password", "")

        self._logger.append(f"[DEBUG OpenVPN] _resolve_credentials: Retrieved username and password.", channel=self._log_channel, level="debug")
        return str(username or ""), str(password or "")

    def _write_auth_file(self, username: str, password: str) -> str:
        run_dir = self._runtime_dir()
        path = os.path.join(run_dir, "openvpn-auth.txt")
        self._logger.append(f"[DEBUG OpenVPN] _write_auth_file: Writing auth file at {path}", channel=self._log_channel, level="debug")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(username + "\n" + password + "\n")
            os.chmod(path, 0o600)
            self._auth_file = path
            self._register_temp(path)
            self._logger.append(f"[OpenVPN] Created auth file at {path}", channel=self._log_channel)
        except Exception as e:
            self._logger.append(f"[DEBUG OpenVPN] Exception in _write_auth_file: {e}", channel=self._log_channel, level="error")
            self._logger.append(f"[OpenVPN] Failed to create auth file: {e}", channel=self._log_channel)
        return path

    def _materialize_config(self) -> Optional[str]:
        stored = self._configuration.get("vpn.openvpn.file")
        self._logger.append(f"[DEBUG OpenVPN] _materialize_config: stored type={type(stored)}, value={repr(stored)[:200]}", channel=self._log_channel, level="debug")
        if not stored:
            self._logger.append(f"[DEBUG OpenVPN] _materialize_config: no stored value.", channel=self._log_channel, level="debug")
            return None

        run_dir = self._runtime_dir()

        if isinstance(stored, dict):
            name = stored.get("name") or "openvpn.ovpn"
            b64 = (
                stored.get("data")
                or stored.get("base64")
                or stored.get("b64")
                or stored.get("file")
                or stored.get("value")
                or ""
            )
            self._logger.append(f"[DEBUG OpenVPN] _materialize_config(dict): name={name}, b64_len={len(b64)}", channel=self._log_channel, level="debug")
            if not b64:
                self._logger.append(
                    "[OpenVPN] Config dict is missing base64 data.",
                    channel=self._log_channel,
                    level="error",
                )
                return None
            try:
                data = base64.b64decode(b64)
                cfg_path = os.path.join(run_dir, name)
                with open(cfg_path, "wb") as f:
                    f.write(data)
                self._register_temp(cfg_path)
                self._logger.append(f"[DEBUG OpenVPN] _materialize_config(dict): wrote {cfg_path}, size={os.path.getsize(cfg_path)}", channel=self._log_channel, level="debug")
                return cfg_path
            except Exception as e:
                self._logger.append(
                    f"[OpenVPN] Failed to materialize inline config (dict): {e}",
                    channel=self._log_channel,
                    level="error",
                )
                return None

        if isinstance(stored, str) and "::" in stored:
            name, b64 = stored.split("::", 1)
            name = name or "openvpn.ovpn"
            self._logger.append(f"[DEBUG OpenVPN] _materialize_config(str):: name={name}, b64_len={len(b64)}", channel=self._log_channel, level="debug")
            try:
                data = base64.b64decode(b64)
                cfg_path = os.path.join(run_dir, name)
                with open(cfg_path, "wb") as f:
                    f.write(data)
                self._register_temp(cfg_path)
                self._logger.append(f"[DEBUG OpenVPN] _materialize_config(str):: wrote {cfg_path}, size={os.path.getsize(cfg_path)}", channel=self._log_channel, level="debug")
                return cfg_path
            except Exception as e:
                self._logger.append(
                    f"[OpenVPN] Failed to materialize inline config from 'vpn.openvpn.file': {e}",
                    channel=self._log_channel,
                    level="error",
                )
                return None

        self._logger.append(
            "[OpenVPN] Unknown format for 'vpn.openvpn.file' (no config materialized).",
            channel=self._log_channel,
            level="error",
        )
        return None

    def _materialize_aux(self, cfg_key: str, default_name: str) -> Optional[str]:
        stored = self._configuration.get(cfg_key)
        self._logger.append(f"[DEBUG OpenVPN] _materialize_aux({cfg_key}): stored type={type(stored)}, value={repr(stored)[:200]}", channel=self._log_channel, level="debug")
        if not stored:
            return None

        try:
            if isinstance(stored, dict):
                name = stored.get("name") or default_name
                b64 = (
                    stored.get("data")
                    or stored.get("base64")
                    or stored.get("b64")
                    or stored.get("file")
                    or stored.get("value")
                    or ""
                )
                self._logger.append(f"[DEBUG OpenVPN] _materialize_aux(dict): name={name}, b64_len={len(b64)}", channel=self._log_channel, level="debug")
                if not b64:
                    self._logger.append(
                        f"[OpenVPN] {cfg_key} dict missing base64 data.",
                        channel=self._log_channel,
                    )
                    return None

            elif isinstance(stored, str) and "::" in stored:
                name, b64 = stored.split("::", 1)
                self._logger.append(f"[DEBUG OpenVPN] _materialize_aux(str):: name={name}, b64_len={len(b64)}", channel=self._log_channel, level="debug")

            elif isinstance(stored, str):
                name, b64 = default_name, stored
                self._logger.append(f"[DEBUG OpenVPN] _materialize_aux(str-simple): name={name}, b64_len={len(b64)}", channel=self._log_channel, level="debug")

            else:
                self._logger.append(
                    f"[OpenVPN] Unsupported type for {cfg_key}: {type(stored).__name__}",
                    channel=self._log_channel,
                    level="error",
                )
                return None

            data = base64.b64decode(b64)
            run_dir = self._runtime_dir()
            path = os.path.join(run_dir, name)
            with open(path, "wb") as f:
                f.write(data)
            self._register_temp(path)
            self._logger.append(f"[DEBUG OpenVPN] _materialize_aux: wrote {path}, size={os.path.getsize(path)}", channel=self._log_channel, level="debug")
            return path
        except Exception as e:
            self._logger.append(
                f"[OpenVPN] Failed to materialize {cfg_key}: {e}",
                channel=self._log_channel,
                level="error",
            )
            return None

    def _cleanup_temp_files(self) -> None:
        self._logger.append(f"[DEBUG OpenVPN] _cleanup_temp_files called.", channel=self._log_channel, level="debug")
        paths = set(self._temp_files)
        if self._auth_file:
            paths.add(self._auth_file)

        for p in paths:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                    self._logger.append(f"[OpenVPN] Deleted temp file: {p}", channel=self._log_channel, level="debug")
                except Exception as e:
                    self._logger.append(f"[OpenVPN] Failed to delete temp file {p}: {e}", channel=self._log_channel, level="warning")

        self._auth_file = None
        self._temp_files.clear()

        # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Process management
    # ------------------------------------------------------------------

    def is_running(self) -> bool:
        running = False

        # If worker thread is still alive, we consider VPN running
        if self._thread and self._thread.isRunning():
            running = True
        elif self._proc is not None and self._proc.poll() is None:
            running = True

        self._logger.append(
            f"[DEBUG OpenVPN] is_running(): {running}",
            channel=self._log_channel,
            level="debug",
        )
        return running

    def stop(self) -> None:
        self._logger.append(
            "[DEBUG OpenVPN] stop() called.",
            channel=self._log_channel,
            level="debug",
        )

        # 1) Prefer to go through the worker thread so it can:
        #    - set _stop_flag
        #    - kill the elevated PID (macOS)
        #    - cleanup temp files
        if self._thread and self._thread.isRunning():
            self._logger.append(
                "[OpenVPN] Requesting worker thread to stop.",
                channel=self._log_channel,
            )
            try:
                self._thread.stop()
                self._thread.wait()
            except Exception as e:
                self._logger.append(
                    f"[OpenVPN] Exception stopping worker thread: {e}",
                    channel=self._log_channel,
                    level="error",
                )
            finally:
                self._thread = None

        # 2) Fallback: if we still have a process we own directly, terminate it
        if self._proc and self._proc.poll() is None:
            try:
                self._logger.append(
                    "[OpenVPN] Terminating OpenVPN subprocess from OpenVPN.stop().",
                    channel=self._log_channel,
                )
                self._proc.terminate()
            except Exception as e:
                self._logger.append(
                    f"[OpenVPN] Failed to terminate OpenVPN subprocess: {e}",
                    channel=self._log_channel,
                    level="error",
                )
        else:
            self._logger.append(
                "[DEBUG OpenVPN] stop(): no active subprocess to terminate.",
                channel=self._log_channel,
                level="debug",
            )

        # 3) Emit final state
        self.stateChanged.emit("stopped")
    # ------------------------------------------------------------------
    # Command generation
    # ------------------------------------------------------------------

    def build_command(
        self,
        overrides: Optional[Dict[str, Any]] = None
    ) -> list[str]:
        self._logger.append(f"[DEBUG OpenVPN] build_command() called with overrides={overrides}", channel=self._log_channel, level="debug")
        overrides = overrides or {}

        def val(key: str, default: Any = None) -> Any:
            v = overrides.get(key)
            if v not in ("", None):
                return v
            return self._configuration.get(key, default)

        bin_path = self._binary_path()

        # Materialize config + CA + key into runtime
        cfg_path = self._materialize_config()
        if not cfg_path:
            self._logger.append(
                "[OpenVPN] No config file materialized; aborting command.",
                channel=self._log_channel,
            )
            self._logger.append(f"[DEBUG OpenVPN] build_command(): cfg_path is None → returning [].", channel=self._log_channel, level="debug")
            return []

        self._materialize_aux("vpn.openvpn.certificate", "ca.crt")
        self._materialize_aux("vpn.openvpn.key", "ta.key")

        cmd: list[str] = [bin_path, "--config", cfg_path]

        # Optional host/port override
        host = val("vpn.openvpn.host", "")
        port = val("vpn.openvpn.port", 1194)
        self._logger.append(f"[DEBUG OpenVPN] build_command(): resolved host={host}, port={port}", channel=self._log_channel, level="debug")

        if host:
            try:
                port_int = int(port) if port is not None else 1194
            except ValueError:
                port_int = 1194
            cmd += ["--remote", str(host), str(port_int)]

        # Credentials → auth-user-pass file
        username, password = self._resolve_credentials(overrides)
        if username and password:
            auth_file = self._write_auth_file(username, password)
            cmd += ["--auth-user-pass", auth_file]
        else:
            self._logger.append(f"[DEBUG OpenVPN] build_command(): no username/password supplied.", channel=self._log_channel, level="debug")

        self._logger.append(f"[DEBUG OpenVPN] build_command(): constructed command: {' '.join(cmd)}", channel=self._log_channel, level="debug")
        return cmd

    # ------------------------------------------------------------------
    # Public connect API
    # ------------------------------------------------------------------

    def connect(
        self,
        parent,
        overrides: Optional[Dict[str, Any]] = None,
        on_success: Optional[Callable[[], None]] = None,
    ) -> None:

        # Reset channel for this new attempt
        self._logger.clear(self._log_channel)

        # Log entry
        self._logger.append(f"[DEBUG OpenVPN] connect() called.", channel=self._log_channel, level="debug")

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

        cmd = self.build_command(overrides)

        if not cmd:
            MsgBox.show(
                parent=parent,
                title="OpenVPN",
                message=(
                    "OpenVPN configuration is invalid or missing.\n\n"
                    "Please re-import your .ovpn file in the Configuration window."
                ),
                icon="error",
                buttons=("OK",),
                default="OK",
                icon_lookup_fn=self._helper.get_path,
            )
            return

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
        _ = line
        return

    def _on_success(self, parent, on_success: Optional[Callable[[], None]] = None):
        if self._dialog:
            self._dialog.hide()

        if callable(on_success):
            on_success()
        else:
            MsgBox.show(
                parent=parent,
                title="VPN connected",
                message="OpenVPN connection established successfully.",
                icon="info",
                buttons=("OK",),
                default="OK",
                icon_lookup_fn=self._helper.get_path,
            )

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
        self._logger.append(
            "[DEBUG OpenVPN] _on_user_cancel() called by user.",
            channel=self._log_channel,
            level="debug",
        )
        # Just use the same logic as the public stop()
        self.stop()
        if self._dialog:
            self._dialog.hide()
