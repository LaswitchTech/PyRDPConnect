#!/usr/bin/env python3
# src/network/openvpn.py
from __future__ import annotations

import signal
import subprocess
import os
from typing import Optional, TYPE_CHECKING

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QApplication

from app.helper import Helper
from app.configuration import Configuration
from app.log import Log

if TYPE_CHECKING:
    from app.application import Application


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
            helper = helper or app.helper                    # type: ignore[attr-defined]
            configuration = configuration or app.configuration  # type: ignore[attr-defined]
            logger = logger or app.logger                    # type: ignore[attr-defined]

        # Helper
        self._helper: Helper = helper

        # Configuration
        self._configuration: Configuration = configuration
        self._configuration.label("network.openvpn", "OpenVPN")
        self._configuration.add("network.openvpn.file", None, "file", label="Config File", filter="OpenVPN Config Files (*.ovpn);;All Files (*)")
        self._configuration.add("network.openvpn.auto", False, "checkbox", label="Auto Connect")

        # Save any new defaults
        self._configuration.save()

        # Logger
        self._logger: Log = logger
        self._log_channel = "openvpn"

        self._proc: Optional[subprocess.Popen] = None
        self._last_error: str = ""
        self.stateChanged.emit("stopped")

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    def is_configured(self) -> bool:
        cfg = self._configuration.get("network.openvpn.file")
        return bool(cfg)

    def auto_connect(self) -> bool:
        return bool(self._configuration.get("network.openvpn.auto"))

    def config_file(self) -> Optional[str]:
        cfg = self._configuration.get("network.openvpn.file")
        if not cfg:
            return None
        return str(cfg)

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
    # Process management
    # ------------------------------------------------------------------

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def last_error(self) -> str:
        return self._last_error

    def start(self) -> bool:
        """
        Start OpenVPN if configured and not already running.
        """
        self._last_error = ""

        if not self.is_configured():
            self._last_error = "OpenVPN config file is not set."
            self._logger.append(self._last_error, channel=self._log_channel)
            self.stateChanged.emit("error")
            return False

        if self.is_running():
            # Already running – treat as success
            self._logger.append(
                "[OpenVPN] start() called but process is already running.",
                channel=self._log_channel,
            )
            return True

        cfg = self.config_file()
        bin_path = self._binary_path()

        if not cfg:
            self._last_error = "OpenVPN config file is empty."
            self._logger.append(self._last_error, channel=self._log_channel)
            self.stateChanged.emit("error")
            return False

        self.stateChanged.emit("starting")
        self._logger.append(
            f"[OpenVPN] Starting: {bin_path} --config {cfg}",
            channel=self._log_channel,
        )

        try:
            self._proc = subprocess.Popen(
                [bin_path, "--config", cfg],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.stateChanged.emit("running")
            self._logger.append("[OpenVPN] Process started successfully.", channel=self._log_channel)
            return True
        except Exception as e:
            self._last_error = str(e)
            self._proc = None
            self.stateChanged.emit("error")
            self._logger.append(f"[OpenVPN] Failed to start: {e}", channel=self._log_channel)
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
            self.stateChanged.emit("stopped")
            self._logger.append("[OpenVPN] Process stopped.", channel=self._log_channel)

    def ensure_connected(self) -> tuple[bool, str]:
        """
        High-level helper for Client:

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
