#!/usr/bin/env python3
# src/app/network/diagnostic.py

from __future__ import annotations

import re
from typing import Any

from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QWidget
)

from app.helper import Helper
from app.ui import StepIndicator
from .tools import Tools

class Diagnostic(QThread):
    log     = pyqtSignal(str)
    phase   = pyqtSignal(str, str)
    summary = pyqtSignal(bool, bool, bool)

    def __init__(self, host: str, ports: Any, parent=None):

        # Initialize QThread
        super().__init__(parent)

        # Initialize Helper and Tools
        self._helper = Helper()
        self._tools = Tools()

        # Store host and ports
        self.host = (host or "").strip()
        self.ports = ports

        # Parent for dialogs
        self._parent = None

    # -------------------------------------------------
    # Small helpers
    # -------------------------------------------------

    def _is_ip(self, value: str) -> bool:
        return bool(re.match(r"^\d+\.\d+\.\d+\.\d+$", value.strip()))

    def _resolve_host(self, host: str) -> tuple[bool, str]:
        """
        Resolve a host using Tools.nslookup when necessary.
        Returns (ok, ip_or_error).
        """
        if self._is_ip(host):
            return True, host

        ok, ip = self._tools.nslookup(host)
        if ok:
            return True, ip
        return False, ip or "Resolution failed"

    # -------------------------------------------------
    # Main run logic (4 phases: device, network, internet, service)
    # -------------------------------------------------

    def run(self):
        # ---------------- DEVICE ----------------
        self.phase.emit("device", "running")

        ips = self._tools.ip()
        if not ips:
            self.log.emit("Device: could not determine any local IPv4 address.")
            self.phase.emit("device", "fail")
            self.summary.emit(False, False, False)
            return

        # pick the first non-APIPA, non-loopback IP from Tools.ip()
        ip = None
        for cand in ips:
            if not cand.startswith("127.") and not self._tools.apipa(cand):
                ip = cand
                break

        if not ip:
            self.log.emit(f"Device: only APIPA/loopback addresses found: {ips}")
            self.phase.emit("device", "fail")
            self.summary.emit(False, False, False)
            return

        if self._tools.apipa(ip):
            self.log.emit(f"Device: APIPA address {ip} (DHCP failure).")
            self.phase.emit("device", "fail")
            self.summary.emit(False, False, False)
            return

        self.log.emit(f"Device: local IP is {ip}")
        self.phase.emit("device", "ok")

        # ---------------- NETWORK (gateway) ----------------
        self.phase.emit("network", "running")

        gw = self._tools.gateway()
        if not gw:
            self.log.emit("Network: default gateway not found.")
            self.phase.emit("network", "fail")
            self.summary.emit(False, False, False)
            return

        self.log.emit(f"Network: default gateway {gw}")
        gw_ok = self._tools.ping(gw)
        self.log.emit("Network: gateway reachable." if gw_ok else "Network: gateway not reachable.")
        self.phase.emit("network", "ok" if gw_ok else "fail")
        network_ok = gw_ok

        # ---------------- INTERNET (public ping + DNS) ----------------
        self.phase.emit("internet", "running")

        # Public IP check via ping (8.8.8.8)
        pub_ok = self._tools.ping("8.8.8.8")
        self.log.emit(
            "Internet: 8.8.8.8 reachable."
            if pub_ok else
            "Internet: cannot reach 8.8.8.8."
        )

        # DNS test via Tools.nslookup
        dns_ok, detail = self._tools.nslookup("google.com")
        if dns_ok:
            self.log.emit(f"Internet: DNS OK → {detail}")
        else:
            self.log.emit(f"Internet: DNS failed: {detail}")

        internet_ok = pub_ok and dns_ok
        self.phase.emit("internet", "ok" if internet_ok else "fail")

        # ---------------- SERVICE (resolve + ping + port(s)) ----------------
        self.phase.emit("service", "running")
        svc_ok = False

        if not self.host:
            self.log.emit("Service: no host configured.")
        else:
            res_ok, addr = self._resolve_host(self.host)
            if not res_ok:
                self.log.emit(f"Service: cannot resolve {self.host}: {addr}")
            else:
                self.log.emit(f"Service: target {self.host} -> {addr} (ports: {self.ports})")

                p_ok = self._tools.ping(addr)
                self.log.emit(
                    "Service: ping reachable."
                    if p_ok else
                    "Service: ping failed."
                )

                # Port test using Tools.nmap (with TCP fallback inside nmap())
                port_results = self._tools.nmap(addr, self.ports)
                if not port_results:
                    self.log.emit("Service: no ports tested or scan failed.")
                    t_ok = False
                else:
                    # Log each port
                    open_any = False
                    for p, is_open in port_results.items():
                        self.log.emit(
                            f"Service: port {p} {'open' if is_open else 'closed'}."
                        )
                        if is_open:
                            open_any = True
                    t_ok = open_any

                svc_ok = p_ok and t_ok

        self.phase.emit("service", "ok" if svc_ok else "fail")

        # ---------------- SUMMARY ----------------
        self.summary.emit(network_ok, internet_ok, svc_ok)

    # ------------------------------------------------------------------
    # UI dialog helper
    # ------------------------------------------------------------------

    def show(self, parent=None):
        if parent is not None and isinstance(parent, QWidget):
            self._parent = parent
        dlg = DiagnosticDialog(self.host, self.ports, parent=self._parent)
        dlg.exec_()
        dlg.raise_()
        dlg.activateWindow()
        return dlg

class DiagnosticDialog(QDialog):

    def __init__(self, host: str, ports: Any, parent=None):
        super().__init__(parent)

        self._host = host or ""
        self._ports = ports
        self._helper = Helper()
        self._tools = Tools()

        self.setWindowTitle("Diagnostic")
        self.setObjectName("DiagnosticDialog")
        self.setWindowFlags(
            Qt.Dialog
            | Qt.WindowTitleHint
            | Qt.CustomizeWindowHint
            | Qt.WindowCloseButtonHint
        )
        self.setMinimumSize(700, 420)

        # --- top: horizontal stepper
        self.dev_ind = StepIndicator("Device")
        self.net_ind = StepIndicator("Network")
        self.int_ind = StepIndicator("Internet")
        self.svc_ind = StepIndicator("Service")

        stepper = QHBoxLayout()
        stepper.setSpacing(24)
        stepper.setContentsMargins(16, 16, 16, 8)
        for w in (self.dev_ind, self.net_ind, self.int_ind, self.svc_ind):
            stepper.addWidget(w, 1)

        # --- right: “Your network status”
        self.status_panel = QLabel()
        self.status_panel.setTextFormat(Qt.PlainText)
        self.status_panel.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.status_panel.setMinimumWidth(260)
        self.status_panel.setStyleSheet(
            "QLabel { "
            "background: rgba(255,255,255,.06); "
            "padding:12px; "
            "border:1px solid rgba(0,0,0,.15); "
            "border-radius:8px; "
            "}"
        )

        # --- left: log
        self.log = QTextEdit()
        self.log.setReadOnly(True)

        mid = QHBoxLayout()
        mid.setContentsMargins(16, 0, 16, 0)
        mid.setSpacing(16)
        mid.addWidget(self.log, 2)
        mid.addWidget(self.status_panel, 1)

        # --- bottom: buttons
        self.run_btn = QPushButton("Run Diagnostics")
        self.close_btn = QPushButton("Close")
        self.run_btn.clicked.connect(self.start_diagnostic)
        self.close_btn.clicked.connect(self.close)

        btns = QHBoxLayout()
        btns.setContentsMargins(16, 8, 16, 16)
        btns.addStretch(1)
        btns.addWidget(self.run_btn)
        btns.addWidget(self.close_btn)

        # --- root layout
        root = QVBoxLayout(self)
        root.addLayout(stepper)
        root.addLayout(mid)
        root.addLayout(btns)

        self._update_status_panel("Unknown", "Unknown", "Unknown")

        # thread handle
        self._thr: Diagnostic | None = None

    # -------------------------------------------------
    # UI helpers
    # -------------------------------------------------

    def _update_status_panel(self, network: str, internet: str, service: str):
        lines = [
            "Your network status:",
            f"Network:  {network}",
            f"Internet: {internet}",
            f"Service:  {service}",
        ]
        self.status_panel.setText("\n".join(lines))

    def _set_all(self, state: str = "idle"):
        self.dev_ind.set_state(state)
        self.net_ind.set_state(state)
        self.int_ind.set_state(state)
        self.svc_ind.set_state(state)

    # -------------------------------------------------
    # Start diagnostics
    # -------------------------------------------------

    def start_diagnostic(self):
        self.log.clear()
        self._set_all("idle")
        self.run_btn.setEnabled(False)

        # If host not provided, try to guess from tools (e.g. gateway or first IP)
        host = self._host
        ports = self._ports

        self._thr = Diagnostic(host=host, ports=ports, parent=self)
        self._thr.log.connect(self._on_log)
        self._thr.phase.connect(self._on_phase)       # phase, state
        self._thr.summary.connect(self._on_summary)   # network, internet, service
        self._thr.finished.connect(lambda: self.run_btn.setEnabled(True))
        self._thr.start()

    # -------------------------------------------------
    # Slots for worker signals
    # -------------------------------------------------

    def _on_log(self, s: str):
        self.log.append(s)

    def _on_phase(self, phase: str, state: str):
        mapping = {
            "device": self.dev_ind,
            "network": self.net_ind,
            "internet": self.int_ind,
            "service": self.svc_ind,
        }
        if phase in mapping:
            mapping[phase].set_state(state)

    def _on_summary(self, network: bool, internet: bool, service: bool):
        def t(b: bool) -> str:
            return "Connected" if b else "Not connected"

        self._update_status_panel(t(network), t(internet), t(service))
