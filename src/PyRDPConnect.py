#!/usr/bin/env python3
from PyQt5.QtWidgets import (
    QApplication, QProgressDialog, QMessageBox, QDialog, QMainWindow,
    QDesktopWidget, QWidget, QTabWidget, QCheckBox, QFrame, QSizePolicy,
    QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QLineEdit, QFormLayout,
    QGroupBox, QGridLayout, QComboBox, QSpinBox, QFileDialog, QColorDialog,
    QTextEdit, QListWidget, QListWidgetItem
)
from PyQt5.QtGui import (
    QIcon, QPixmap, QPainter, QPalette, QColor, QValidator, QTextCharFormat
)
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QRegExp, QSize
import subprocess
import platform
import shutil
import base64
import json
import sys
import os
import re
import enum
import threading
import queue
import time

class Severity(enum.Enum):
    INFO = 1
    WARNING = 2
    ERROR = 3

class StepIndicator(QWidget):
    """
    A compact status lamp + label. States: 'idle', 'running', 'ok', 'fail'
    Uses stylesheet-only colors so it renders on thin clients without emoji/fonts.
    """
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._state = 'idle'
        self.dot = QLabel()
        self.dot.setObjectName("statusDot")
        self.dot.setFixedSize(16, 16)
        self.label = QLabel(text)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(6)
        dot_wrap = QWidget()
        dot_wrap.setFixedHeight(20)
        dot_lay = QHBoxLayout(dot_wrap)
        dot_lay.setContentsMargins(0,0,0,0)
        dot_lay.addStretch(1)
        dot_lay.addWidget(self.dot, 0, Qt.AlignCenter)
        dot_lay.addStretch(1)

        lay.addWidget(dot_wrap)
        self.label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.label)
        self._apply_style()

    def set_state(self, state: str):
        self._state = state
        self._apply_style()

    def _apply_style(self):
        colors = {
            'idle':    '#A0A4A8',   # grey
            'running': '#F5C542',   # amber
            'ok':      '#2FB344',   # green
            'fail':    '#E03131',   # red
        }
        c = colors.get(self._state, '#A0A4A8')
        self.dot.setStyleSheet(f"background:{c}; border-radius:7px; border:1px solid rgba(0,0,0,.25);")

class DiagnosticsWindow(QDialog):
    def __init__(self, parent: "Client"):
        super().__init__(parent)
        self.client = parent
        self.setWindowTitle("Diagnostics")
        self.setObjectName("diagnosticsWindow")
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.CustomizeWindowHint | Qt.WindowCloseButtonHint)
        self.setMinimumSize(700, 420)

        # --- top: horizontal stepper
        self.dev_ind   = StepIndicator("Device")
        self.net_ind   = StepIndicator("Network")
        self.int_ind   = StepIndicator("Internet")
        self.svc_ind   = StepIndicator("Service")

        stepper = QHBoxLayout()
        stepper.setSpacing(24); stepper.setContentsMargins(16, 16, 16, 8)
        for w in (self.dev_ind, self.net_ind, self.int_ind, self.svc_ind):
            stepper.addWidget(w, 1)

        # --- right: “Your network status”
        self.status_panel = QLabel()
        self.status_panel.setTextFormat(Qt.PlainText)
        self.status_panel.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.status_panel.setMinimumWidth(260)
        self.status_panel.setStyleSheet("QLabel { background: rgba(255,255,255,.06); padding:12px; border:1px solid rgba(0,0,0,.15); border-radius:8px; }")

        # --- left: log
        self.log = QTextEdit(); self.log.setReadOnly(True)

        mid = QHBoxLayout()
        mid.setContentsMargins(16, 0, 16, 0)
        mid.setSpacing(16)
        mid.addWidget(self.log, 2)
        mid.addWidget(self.status_panel, 1)

        # --- bottom: buttons
        self.run_btn   = QPushButton("Run Diagnostics")
        self.close_btn = QPushButton("Close")
        self.run_btn.clicked.connect(self.start)
        self.close_btn.clicked.connect(self.close)

        btns = QHBoxLayout()
        btns.setContentsMargins(16, 8, 16, 16)
        btns.addStretch(1); btns.addWidget(self.run_btn); btns.addWidget(self.close_btn)

        # --- root
        root = QVBoxLayout(self)
        root.addLayout(stepper)
        root.addLayout(mid)
        root.addLayout(btns)

        self._update_status_panel("Unknown", "Unknown", "Unknown")

        # thread handle
        self._thr = None

    def _update_status_panel(self, network, internet, service):
        lines = [
            "Your network status:",
            f"Network:  {network}",
            f"Internet: {internet}",
            f"Service:  {service}",
        ]
        self.status_panel.setText("\n".join(lines))

    def _set_all(self, state='idle'):
        self.dev_ind.set_state(state)
        self.net_ind.set_state(state)
        self.int_ind.set_state(state)
        self.svc_ind.set_state(state)

    def start(self):
        self.log.clear()
        self._set_all('idle')
        self.run_btn.setEnabled(False)

        # assemble target/port from current config
        cfg = self.client.config
        host = (cfg.get("General", {}).get("Server Address") or "").strip()
        port = int(cfg.get("General", {}).get("Port") or 3389)

        self._thr = DiagnosticsThread(host=host, port=port, parent=self)
        self._thr.log.connect(self._on_log)
        self._thr.phase.connect(self._on_phase)   # phase, state
        self._thr.summary.connect(self._on_summary)  # network, internet, service
        self._thr.finished.connect(lambda: self.run_btn.setEnabled(True))
        self._thr.start()

    def _on_log(self, s: str):
        self.log.append(s)

    def _on_phase(self, phase: str, state: str):
        mapping = {
            'device': self.dev_ind,
            'network': self.net_ind,
            'internet': self.int_ind,
            'service': self.svc_ind,
        }
        if phase in mapping:
            mapping[phase].set_state(state)

    def _on_summary(self, network: bool, internet: bool, service: bool):
        def t(b): return "Connected" if b else "Not connected"
        self._update_status_panel(t(network), t(internet), t(service))

class DiagnosticsThread(QThread):
    log     = pyqtSignal(str)
    phase   = pyqtSignal(str, str)          # ('device'|'network'|'internet'|'service', 'idle'|'running'|'ok'|'fail')
    summary = pyqtSignal(bool, bool, bool)  # network_ok, internet_ok, service_ok

    def __init__(self, host: str, port: int, parent=None):
        super().__init__(parent)
        self.host = host
        self.port = port

    # ---------- helpers ----------
    def _run(self, cmd):
        try:
            p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, timeout=6)
            return p.returncode, (p.stdout or "").strip()
        except Exception as e:
            return 1, f"{type(e).__name__}: {e}"

    def _ping(self, host, osname):
        args = ["ping", "-c", "1"] + (["-t", "1"] if osname == "Darwin" else ["-W", "1"])
        # try PATH ping if absolute not found
        return self._run(args + [host])[0] == 0

    def _default_gateway(self, osname):
        # macOS
        rc, out = self._run(["/sbin/route", "-n", "get", "default"]) if osname == "Darwin" else (1, "")
        if rc == 0:
            m = re.search(r"gateway:\s+([0-9.]+)", out);
            if m: return m.group(1)
        # Linux fallbacks: /sbin/ip, ip, route -n
        for cmd in (["/sbin/ip","route"], ["ip","route"], ["route","-n"]):
            rc, out = self._run(cmd)
            if rc == 0:
                for line in out.splitlines():
                    if line.startswith("default via "):
                        parts = line.split()
                        if len(parts) >= 3: return parts[2]
                    if line.startswith("0.0.0.0") and len(line.split()) >= 3:  # busybox route -n
                        return line.split()[1]
        return None

    def _egress_ip(self):
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(2)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]; s.close()
            return ip
        except Exception:
            return None

    def _is_apipa(self, ip): return isinstance(ip, str) and ip.startswith("169.254.")

    def _dns_lookup(self, host):
        import socket
        try:
            return True, socket.gethostbyname(host)
        except Exception as e:
            return False, str(e)

    def _tcp_connect(self, host, port, timeout=3.0):
        import socket
        try:
            ai = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
            for fam, st, proto, canon, sa in ai:
                s = socket.socket(fam, st, proto)
                s.settimeout(timeout)
                try:
                    s.connect(sa)
                    s.close()
                    return True
                except Exception:
                    s.close()
            return False
        except Exception:
            return False

    # ---------- main ----------
    def run(self):
        osname = platform.system()

        # DEVICE
        self.phase.emit('device', 'running')
        ip = self._egress_ip()
        if not ip:
            self.log.emit("Device: could not determine local egress IP.")
            self.phase.emit('device', 'fail'); self.summary.emit(False, False, False); return
        if self._is_apipa(ip):
            self.log.emit(f"Device: APIPA address {ip} (DHCP failure).")
            self.phase.emit('device', 'fail'); self.summary.emit(False, False, False); return
        self.log.emit(f"Device: local IP is {ip}")
        self.phase.emit('device', 'ok')

        # NETWORK (gateway)
        self.phase.emit('network', 'running')
        gw = self._default_gateway(osname)
        if not gw:
            self.log.emit("Network: default gateway not found.")
            self.phase.emit('network', 'fail'); self.summary.emit(False, False, False); return
        self.log.emit(f"Network: default gateway {gw}")
        gw_ok = self._ping(gw, osname)
        self.log.emit("Network: gateway reachable." if gw_ok else "Network: gateway not reachable.")
        self.phase.emit('network', 'ok' if gw_ok else 'fail')
        network_ok = gw_ok

        # INTERNET (public ping + DNS)
        self.phase.emit('internet', 'running')
        pub_ok = self._ping("8.8.8.8", osname)
        self.log.emit("Internet: 8.8.8.8 reachable." if pub_ok else "Internet: cannot reach 8.8.8.8.")
        dns_ok, detail = self._dns_lookup("google.com")
        self.log.emit(f"Internet: DNS {'OK → '+detail if dns_ok else 'failed: '+detail}")
        internet_ok = pub_ok and dns_ok
        self.phase.emit('internet', 'ok' if internet_ok else 'fail')

        # SERVICE (resolve + ping + TCP port)
        self.phase.emit('service', 'running')
        svc_ok = False
        if not self.host:
            self.log.emit("Service: no host configured.")
        else:
            res_ok, addr = self._dns_lookup(self.host) if not re.match(r'^\d+\.\d+\.\d+\.\d+$', self.host) else (True, self.host)
            if not res_ok:
                self.log.emit(f"Service: cannot resolve {self.host}: {addr}")
            else:
                self.log.emit(f"Service: target {self.host} -> {addr}:{self.port}")
                p_ok = self._ping(addr, osname)
                self.log.emit("Service: ping reachable." if p_ok else "Service: ping failed.")
                t_ok = self._tcp_connect(addr, self.port, timeout=3.0)
                self.log.emit("Service: TCP port open." if t_ok else "Service: TCP connect failed.")
                svc_ok = p_ok and t_ok

        self.phase.emit('service', 'ok' if svc_ok else 'fail')

        # Summary back to window
        self.summary.emit(network_ok, internet_ok, svc_ok)

class FreerdpEvent:
    def __init__(self, severity: Severity, code: str, message: str, hint: str = ""):
        self.severity = severity
        self.code = code             # e.g. ERRCONNECT_ACTIVATION_TIMEOUT
        self.message = message       # user-facing short message
        self.hint = hint             # optional suggestion/fix

class FreerdpLogInterpreter:
    def __init__(self, show_cert_warning: bool = False):
        self.show_cert_warning = show_cert_warning

    # Patterns → (severity, code, user message, hint)
    RULES = [
        # --- Normal/expected endings ---
        (r'ERRINFO_LOGOFF_BY_USER', (Severity.INFO, 'ERRINFO_LOGOFF_BY_USER',
            'You logged off the remote session.',
            'This is normal if you clicked Disconnect/Sign out on the remote Windows session.')),
        (r'ERRINFO_IDLE_TIMEOUT', (Severity.INFO, 'ERRINFO_IDLE_TIMEOUT',
            'Disconnected due to inactivity.', 'Reconnect to continue.')),

        # --- Common alternate lines seen on some FreeRDP builds/platforms ---
        (r'ERRINFO_RPC_INITIATED_DISCONNECT', (Severity.INFO, 'ERRINFO_LOGOFF_BY_USER',
            'You were disconnected by the server.',
            'This can be normal if you signed out or the admin ended the session.')),
        (r'freerdp_disconnect: closing connection', (Severity.INFO, 'ERRINFO_LOGOFF_BY_USER',
            'The session was closed.',
            'If you clicked Disconnect/Sign out, this is expected.')),

        # --- Idle timeout ---
        (r'ERRINFO_IDLE_TIMEOUT', (Severity.INFO, 'ERRINFO_IDLE_TIMEOUT',
            'Disconnected due to inactivity.', 'Reconnect to continue.')),

        # --- Connect/handshake timeouts ---
        (r'ERRCONNECT_ACTIVATION_TIMEOUT', (Severity.ERROR, 'ERRCONNECT_ACTIVATION_TIMEOUT',
            'The server took too long to activate the session.',
            'Try again, or increase the connection timeout in Settings.')),

        # --- Certificate warnings ---
        (r'Certificate not checked, /cert:ignore in use', (Severity.WARNING, 'CERT_IGNORE',
            'Unverified server certificate (ignored).',
            'Only use /cert:ignore on trusted LAN. Otherwise, enable certificate validation.')),

        # --- Password on CLI warnings (don’t block, just hint) ---
        (r'Using /p is insecure', (Severity.WARNING, 'INSECURE_PASSWORD_ARG',
            'Password was passed on the command line.',
            'Use /from-stdin or set FREERDP_ASKPASS for safer credential entry.')),

        # --- Device hotplug noise (non-fatal) ---
        (r'handle_hotplug failed with error 1', (Severity.WARNING, 'RDPDR_HOTPLUG',
            'A redirected device failed to hot-plug.',
            'Usually harmless. If it persists, disable “Drives/Printers” redirection and retry.')),

        # --- Generic catch-alls we still want to prettify ---
        (r'Could not connect to RDP server', (Severity.ERROR, 'CANNOT_CONNECT',
            'Could not connect to the server.', 'Verify IP/hostname and port 3389 reachability.')),
        (r'Access Denied', (Severity.ERROR, 'ACCESS_DENIED',
            'Access denied by the server.', 'Check username, password, and domain.')),
        (r'LOGON_FAILURE', (Severity.ERROR, 'LOGON_FAILURE',
            'Logon failed.', 'Check credentials or account lockout.')),
        (r'hostname cannot be resolved', (Severity.ERROR, 'DNS_FAIL',
            'Host cannot be resolved.', 'Check DNS or use the IP address.')),
        (r'GATEWAY.*denied|HTTP/.* 403', (Severity.ERROR, 'GATEWAY_DENIED',
            'Gateway denied the connection.', 'Check RD Gateway URL/credentials.')),
    ]

    def classify(self, text: str) -> list:
        events = []
        for pat, (sev, code, msg, hint) in self.RULES:
            if re.search(pat, text, re.IGNORECASE):
                if code == 'CERT_IGNORE' and not self.show_cert_warning:
                    continue
                events.append(FreerdpEvent(sev, code, msg, hint))
        return events

    def most_relevant(self, events: list) -> FreerdpEvent | None:
        if not events:
            return None
        # Prefer ERROR > WARNING > INFO
        priority = {Severity.ERROR: 3, Severity.WARNING: 2, Severity.INFO: 1}
        events.sort(key=lambda e: priority[e.severity], reverse=True)
        return events[0]

class LogWindow(QDialog):
    def __init__(self, parent=None, text: str = "", filter_text: str = None):
        super().__init__(parent)
        self.setWindowTitle("Connection Log")
        self.setObjectName("logWindow")
        self.setMinimumSize(720, 420)

        # keep the full log intact; we render a filtered view into the QTextEdit
        self._full_text = text or ""

        self.text = QTextEdit(self)
        self.text.setReadOnly(True)
        self.text.setPlainText(self._full_text)

        self.find_box = QLineEdit(self)
        self.find_box.setPlaceholderText("Filter...")
        # live filtering as the user types
        self.find_box.textChanged.connect(self.apply_filter)

        self.copy_btn = QPushButton("Copy all")
        self.copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.text.toPlainText()))
        self.save_btn = QPushButton("Save as...")
        self.save_btn.clicked.connect(self.save_as)

        top = QHBoxLayout()
        top.addWidget(self.find_box)
        top.addWidget(self.copy_btn)
        top.addWidget(self.save_btn)

        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(self.text)

        # if the window is opened with a filter, apply it immediately
        if filter_text:
            self.find_box.setText(filter_text)
        else:
            self.apply_filter()  # renders full text (no highlight) on open

    def set_text(self, text: str):
        self._full_text = text or ""
        self.apply_filter()

    def save_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save log", "connection.log",
            "Log Files (*.log);;Text Files (*.txt);;All Files (*)"
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.text.toPlainText())

    # ---- filtering + highlighting ----
    def apply_filter(self):
        needle = self.find_box.text().strip()
        if not needle:
            # show everything, no highlights
            self._set_view_text(self._full_text)
            return

        # keep only lines containing the needle (case-insensitive)
        filtered_lines = [ln for ln in self._full_text.splitlines()
                          if needle.lower() in ln.lower()]
        self._set_view_text("\n".join(filtered_lines))

        # highlight all occurrences of the needle in yellow
        self._highlight_all(needle)

    def _set_view_text(self, s: str):
        # avoid recursive textChanged signals while replacing the whole buffer
        self.text.blockSignals(True)
        self.text.setPlainText(s)
        self.text.blockSignals(False)

    def _highlight_all(self, needle: str):
        if not needle:
            return
        doc = self.text.document()
        cursor = self.text.textCursor()
        cursor.beginEditBlock()

        # clear previous formats
        clear = QTextCharFormat()
        rng = self.text.textCursor()
        rng.movePosition(rng.Start)
        rng.movePosition(rng.End, rng.KeepAnchor)
        rng.setCharFormat(clear)

        # yellow background for matches
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("yellow"))
        fmt.setForeground(QColor("black"))

        # case-insensitive search with QRegExp
        rx = QRegExp(needle)
        rx.setCaseSensitivity(Qt.CaseInsensitive)

        pos = 0
        while True:
            pos = rx.indexIn(doc.toPlainText(), pos)
            if pos < 0:
                break
            # select the match and apply format
            match_cursor = self.text.textCursor()
            match_cursor.setPosition(pos)
            match_cursor.setPosition(pos + rx.matchedLength(), match_cursor.KeepAnchor)
            match_cursor.mergeCharFormat(fmt)
            pos += max(1, rx.matchedLength())

        cursor.endEditBlock()

    # keep these around for compatibility (optional)
    def find_next(self):
        # not needed anymore (live filter), but kept if you call it elsewhere
        self.apply_filter()

class ConnectionThread(QThread):
    connection_success = pyqtSignal()
    connection_failed = pyqtSignal(str, str, str)   # (title, details)
    connection_info   = pyqtSignal(str)        # live status text (optional)
    stop_thread = False

    def __init__(self, command, parent = None, show_cert_warning: bool = False, stdin_password: str | None = None, debug_enabled: bool = False):
        super().__init__(parent)
        self.command = command
        self.freerdp_process = None
        self._interpreter = FreerdpLogInterpreter(show_cert_warning=show_cert_warning)
        self._stdin_password = stdin_password
        self._debug_enabled = debug_enabled

    def run(self):
        try:
            env = os.environ.copy()
            freerdp_bin = self.command[0]
            base_dir = os.path.dirname(freerdp_bin)

            # Look for adjacent 'lib' and 'plugins' folders in the bundle
            lib_dir = os.path.join(base_dir, 'lib')
            plugins_dir = os.path.join(base_dir, 'plugins')

            # Per-OS runtime search paths
            if sys.platform == 'darwin':
                if os.path.isdir(lib_dir):
                    env['DYLD_LIBRARY_PATH'] = lib_dir + (':' + env.get('DYLD_LIBRARY_PATH','') if env.get('DYLD_LIBRARY_PATH') else '')
            elif sys.platform.startswith('linux'):
                if os.path.isdir(lib_dir):
                    env['LD_LIBRARY_PATH'] = lib_dir + (':' + env.get('LD_LIBRARY_PATH','') if env.get('LD_LIBRARY_PATH') else '')

            # Channel plugins (cliprdr, drdynvc, rdpsnd, etc.)
            if os.path.isdir(plugins_dir):
                env['FREERDP_PLUGIN_PATH'] = plugins_dir

            # (Optional) make certificates resolvable in restricted environments
            # env.setdefault('SSL_CERT_DIR', '/etc/ssl/certs')

            self.freerdp_process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                text=True,
                env=env,
                bufsize=1,
                universal_newlines=True
            )

            # Send password via stdin (compatible with v2 and v3)
            try:
                if any(arg.startswith("/from-stdin") for arg in self.command) and self._stdin_password is not None:
                    self.freerdp_process.stdin.write(self._stdin_password + "\n")
                    self.freerdp_process.stdin.flush()
                    # keep stdin open; some builds may read again
            except Exception:
                pass

            collected = []

            def pump(stream):
                for line in iter(stream.readline, ''):
                    if self.stop_thread:
                        break
                    ln = line.rstrip()
                    collected.append(ln)
                stream.close()

            # Read both streams
            t_out = threading.Thread(target=pump, args=(self.freerdp_process.stdout,))
            t_err = threading.Thread(target=pump, args=(self.freerdp_process.stderr,))
            t_out.start(); t_err.start()

            # Wait for freerdp to exit
            rc = self.freerdp_process.wait()
            t_out.join(); t_err.join()

            text = "\n".join(collected)

            if self.stop_thread:
                # Treat as a user-cancel—don’t show an error dialog
                return

            # If return code is 0, success
            if rc == 0:
                self.connection_success.emit()
                return

            # Classify errors
            events = self._interpreter.classify(text)
            top = self._interpreter.most_relevant(events)

            # Special case: treat user logoff as INFO, not an error
            if top and top.code == 'ERRINFO_LOGOFF_BY_USER':
                # self.connection_failed.emit("Disconnected", top.message + (f"\n\nHint: {top.hint}" if top.hint else ""))
                # return
                details = top.message + (f"\n\nHint: {top.hint}" if top.hint else "")
                self.connection_failed.emit("Disconnected", details, text)
                return

            # Build a friendly message
            if top:
                title = "Connection problem" if top.severity != Severity.INFO else "Information"
                details = top.message + (f"\n\nHint: {top.hint}" if top.hint else "")
            else:
                title = "Connection failed"
                details = "The connection ended unexpectedly.\n\nOpen the detailed log for more information."

            self.connection_failed.emit(title, details, text)

        except Exception as e:
            # make sure we still forward whatever we collected
            if not text:
                try:
                    text = "\n".join(collected)
                except Exception:
                    text = ""
            self.connection_failed.emit("Unexpected error", f"{type(e).__name__}: {e}", text)

    def stop(self):
        self.stop_thread = True
        if self.freerdp_process:
            try:
                self.freerdp_process.terminate()
            except Exception:
                pass

class ColorButton(QPushButton):
    """
    A small button that shows a color swatch; clicking opens a color dialog.
    Use .color() to get QColor; .hex() for '#RRGGBB'.
    """
    colorChanged = pyqtSignal(QColor)

    def __init__(self, initial="#265162", parent=None):
        super().__init__(parent)
        self._color = QColor(initial)
        self.setFixedSize(48, 24)
        self._update_style()
        self.clicked.connect(self._pick)

    def _pick(self):
        chosen = QColorDialog.getColor(self._color, self, "Choose Color")
        if chosen.isValid():
            self._color = chosen
            self._update_style()
            self.colorChanged.emit(self._color)

    def _update_style(self):
        self.setStyleSheet(
            f"border: 1px solid #76797C; border-radius: 4px; "
            f"background: {self._color.name()};"
        )

    def color(self) -> QColor:
        return self._color

    def hex(self) -> str:
        return self._color.name()

class Client(QMainWindow):

    def __init__(self):
        super().__init__()

        # Initialize the last log text
        self.last_log_text = ""

        # Initialize properties
        self.init_properties()

        # Load config from file
        self.load_config()

        # Load widgets
        self.load_widgets()

        # Initialize window
        self.init_window()

        # Initialize UI
        self.init_ui()

    def get_path(self,path):
        """
        Return an absolute path to a data file bundled either:
        - in a PyInstaller onefile (sys._MEIPASS),
        - in a macOS .app (Contents/Resources),
        - in the repo (src/),
        and gracefully return None if not found.
        """
        # Normalize input (accept "icons/foo.svg" or os.path.join(...))
        rel = path.replace("\\", "/")

        # 1) PyInstaller onefile temp dir
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            p = os.path.join(meipass, rel)
            if os.path.exists(p):
                return p

        # 2) Next to the frozen executable (one-folder or manual copies)
        if getattr(sys, 'frozen', False):
            p = os.path.join(self.script_dir, rel)
            if os.path.exists(p):
                return p

        # 3) macOS .app Resources (…/Contents/Resources/<rel>)
        res = os.path.join(self.root_dir, 'Resources', rel)
        if os.path.exists(res):
            return res

        # 4) Repo layout (…/<root>/src/<rel>)
        src = os.path.join(self.root_dir, 'src', rel)
        if os.path.exists(src):
            return src

        # Debug
        print(f"Could not find: [{self.root_dir}] {rel}")
        return None

    def get_os(self):
        os_name = platform.system()
        if os_name == "Darwin":
            return "macos"
        elif os_name == "Linux":
            return "linux"
        elif os_name == "Windows":
            return "windows"
        else:
            return "unknown"

    def load_config(self):

        # Initialize config dictionary with default values
        self.config = {
            "General": {
                "Server Address": "",
                "Port": 3389,
                "Username": "",
                "Password": "",
                "Domain": ""
            },
            "FreeRDP": {
                "Display": {
                    "Resolution": "",
                    "Use all monitors": False,
                    "Start session in fullscreen": False,
                    "Fit session to window": False
                },
                "Devices": {
                    "Play sound": "",
                    "Record sound": "",
                    "Printers": False,
                    "Smart Cards": False,
                    "Ports": False,
                    "Drives": False
                },
                "Folders": {
                    "Redirect": False,
                    "Folders": []
                },
                "Experience": {
                    "Clipboard": False,
                    "RemoteFX": False,
                    "Smooth Fonts": False,
                    "Desktop Composition": False,
                    "Full Window Drag": False,
                    "Menu Animations": False,
                    "Disable Themes": False,
                    "Disable Wallpaper": False,
                    "Show certificate warning": False
                }
            },
            "Networking": {
                "WiFi": {
                    "Interface": "",
                    "SSID": "",
                    "Password": "",
                    "Auto connect": False
                },
                "OpenVPN": {
                    "Config File": "",
                    "Auto connect": False
                },
                "WireGuard": {
                    "Config File": "",
                    "Auto connect": False
                }
            },
            "Appearance": {
                "Logo File": "",
                "Logo Position": "top-center",
                "Login Position": "center-center",
                "Hide Exit": False,
                "Hide Diagnostics": False,
                "Hide Restart": False,
                "Hide Shutdown": False,
                "Fullscreen": False,
                "Gradient Start": "#265162",
                "Gradient End":   "#002136"
            },
            "Administration": {
                "Password": "",
                "Debug logging": False
            },
        }

        # Load config from file
        config_dir = os.path.join(self.root_dir, 'config')

        # --- load new-style cfgs if present ---
        def _merge_into(dst, src):
            for k, v in src.items():
                if isinstance(v, dict) and isinstance(dst.get(k), dict):
                    _merge_into(dst[k], v)
                else:
                    # keep lists non-None
                    if isinstance(dst.get(k), list) and v is None:
                        dst[k] = []
                    else:
                        dst[k] = v

        for fname, topkey in [("general.cfg","General"),
                            ("freerdp.cfg","FreeRDP"),
                            ("networking.cfg","Networking"),
                            ("appearance.cfg","Appearance"),
                            ("administration.cfg","Administration")]:
            p = os.path.join(config_dir, fname)
            if os.path.exists(p):
                try:
                    with open(p, "r") as f:
                        data = json.load(f)
                    if topkey in self.config and isinstance(self.config[topkey], dict) and isinstance(data, dict):
                        _merge_into(self.config[topkey], data)
                    elif topkey in self.config:
                        self.config[topkey] = data
                except Exception as e:
                    print(f"Failed loading {fname}: {e}")

        # --- LEGACY migration (display.cfg / devices.cfg / folders.cfg / experience.cfg) ---
        legacy_map = {
            "display.cfg": ("FreeRDP", "Display"),
            "devices.cfg": ("FreeRDP", "Devices"),
            "folders.cfg": ("FreeRDP", "Folders"),
            "experience.cfg": ("FreeRDP", "Experience"),
        }
        for legacy_fname, (top, sub) in legacy_map.items():
            p = os.path.join(config_dir, legacy_fname)
            if os.path.exists(p):
                try:
                    with open(p, "r") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        _merge_into(self.config[top][sub], data)
                except Exception as e:
                    print(f"Failed migrating {legacy_fname}: {e}")

        # Logo path resolution (same behavior)
        logo_path = os.path.join(self.root_dir, 'config', 'logo.png')
        if os.path.exists(logo_path):
            self.config["Appearance"]["Logo File"] = logo_path
        else:
            self.config["Appearance"]["Logo File"] = self.get_path(os.path.join('img', 'logo.png')) or ""

    def load_widgets(self):
        """
        Build self.widgets as a nested map that mirrors self.config for categories
        with sub-tabs (FreeRDP, Networking).
        """

        # password edits
        passwordLineEdit = QLineEdit(); passwordLineEdit.setEchoMode(QLineEdit.Password)
        lockLineEdit = QLineEdit();     lockLineEdit.setEchoMode(QLineEdit.Password)

        # Port
        portSpinBox = QSpinBox(); portSpinBox.setRange(1, 65535)
        portSpinBox.setValue(self.config["General"]["Port"])

        # Resolution (detect)
        screenResolution = QApplication.desktop().screenGeometry()
        currentResolution = f"{screenResolution.width()}x{screenResolution.height()}"
        self.config["FreeRDP"]["Display"]["Resolution"] = currentResolution

        resolutionComboBox = QComboBox()
        commonRes = ["800x600","1024x768","1280x720","1366x768","1920x1080","3840x2160"]
        if currentResolution not in commonRes:
            commonRes.insert(0, currentResolution)
        resolutionComboBox.addItems(commonRes)
        resolutionComboBox.setCurrentText(self.config["FreeRDP"]["Display"]["Resolution"])

        # Sound combos
        playSoundCombo = QComboBox(); playSoundCombo.addItems(["Never","On this computer","On the remote computer"])
        playSoundCombo.setCurrentText(self.config["FreeRDP"]["Devices"]["Play sound"])
        recordSoundCombo = QComboBox(); recordSoundCombo.addItems(["Never","On this computer","On the remote computer"])
        recordSoundCombo.setCurrentText(self.config["FreeRDP"]["Devices"]["Record sound"])

        # Positions
        positionsOptions = ["top-left","top-center","top-right","center-left","center-center","center-right","bottom-left","bottom-center","bottom-right"]
        loginPosCombo = QComboBox(); loginPosCombo.addItems(positionsOptions)
        loginPosCombo.setCurrentText(self.config["Appearance"]["Login Position"])
        logoPosCombo  = QComboBox(); logoPosCombo.addItems(positionsOptions)
        logoPosCombo.setCurrentText(self.config["Appearance"]["Logo Position"])

        # Logo
        logo_file = self.config["Appearance"]["Logo File"] or self.get_path(os.path.join('img', 'logo.png'))
        self.gen_logo_button(logo_file)

        # Gradient
        gradient_start_btn = ColorButton(self.config["Appearance"]["Gradient Start"] or "#265162")
        gradient_end_btn   = ColorButton(self.config["Appearance"]["Gradient End"] or "#002136")
        gradient_start_btn.colorChanged.connect(lambda _: self.on_configuration_changed())
        gradient_end_btn.colorChanged.connect(lambda _: self.on_configuration_changed())

        # Folder redirection controls
        self.folder_add_button = QPushButton("Add Folder")
        self.folder_add_button.clicked.connect(self.select_folder)
        self.folder_list_layout = QVBoxLayout()

        # Admin buttons
        self.open_log_button = QPushButton("Open log")
        self.open_log_button.clicked.connect(self.open_last_log)
        self.update_button = QPushButton("Update")
        self.update_button.clicked.connect(self.update_application)
        self.import_button = QPushButton("Import")
        self.import_button.clicked.connect(self.import_settings)
        self.export_button = QPushButton("Export")
        self.export_button.clicked.connect(self.export_settings)

        # --- Build widgets map mirroring new config structure ---
        self.widgets = {
            "General": {
                "Server Address": QLineEdit(),
                "Port": portSpinBox,
                "Username": QLineEdit(),
                "Password": passwordLineEdit,
                "Domain": QLineEdit(),
            },
            "FreeRDP": {
                "Display": {
                    "Resolution": resolutionComboBox,
                    "Use all monitors": QCheckBox(),
                    "Start session in fullscreen": QCheckBox(),
                    "Fit session to window": QCheckBox(),
                },
                "Devices": {
                    "Play sound":   playSoundCombo,
                    "Record sound": recordSoundCombo,
                    "Printers":     QCheckBox(),
                    "Smart Cards":  QCheckBox(),
                    "Ports":        QCheckBox(),
                    "Drives":       QCheckBox(),
                },
                "Folders": {
                    "Redirect": QCheckBox(),
                    "Folders":  [],  # list UI handled separately
                },
                "Experience": {
                    "Clipboard":             QCheckBox(),
                    "RemoteFX":              QCheckBox(),
                    "Smooth Fonts":          QCheckBox(),
                    "Desktop Composition":   QCheckBox(),
                    "Full Window Drag":      QCheckBox(),
                    "Menu Animations":       QCheckBox(),
                    "Disable Themes":        QCheckBox(),
                    "Disable Wallpaper":     QCheckBox(),
                    "Show certificate warning": QCheckBox(),
                },
            },
            "Networking": {
                # WiFi tab only shown on Linux in launch_configurations, but we still keep widgets here
                "WiFi": {
                    "Interface":    QLineEdit(),
                    "SSID":         QLineEdit(),
                    "Password":     QLineEdit(),
                    "Auto connect": QCheckBox(),
                },
                "OpenVPN": {
                    "Config File":  QLineEdit(),
                    "Auto connect": QCheckBox(),
                },
                "WireGuard": {
                    "Config File":  QLineEdit(),
                    "Auto connect": QCheckBox(),
                }
            },
            "Appearance": {
                "Logo File":      self.logo_file_button,
                "Logo Position":  logoPosCombo,
                "Login Position": loginPosCombo,
                "Hide Exit":      QCheckBox(),
                "Hide Diagnostics": QCheckBox(),
                "Hide Restart":   QCheckBox(),
                "Hide Shutdown":  QCheckBox(),
                "Fullscreen":     QCheckBox(),
                "Gradient Start": gradient_start_btn,
                "Gradient End":   gradient_end_btn,
            },
            "Administration": {
                "Password":       lockLineEdit,
                "Debug logging":  QCheckBox(),
                "Open log":       self.open_log_button,
                "Update":         self.update_button,
                "Import":         self.import_button,
                "Export":         self.export_button,
            },
        }

        # --- Apply current config values into widgets (supports nested dicts) ---
        def _apply_values(widget_map, cfg):
            for key, w in widget_map.items():
                if isinstance(w, dict) and isinstance(cfg.get(key, None), dict):
                    _apply_values(w, cfg[key])
                elif isinstance(w, list):
                    # folders list handled in launch_configurations (we only keep data here)
                    pass
                else:
                    if w is not None and key in cfg:
                        self.set_widget_value(w, cfg[key])

        _apply_values(self.widgets, self.config)

    def init_properties(self):

        # Set class properties
        # Get the directory of the script
        if getattr(sys, 'frozen', False):
            # we are running in a bundle
            self.script_dir = os.path.dirname(sys.executable)
        else:
            # we are running in a normal Python environment
            self.script_dir = os.path.dirname(os.path.abspath(__file__))

        # Get the root directory of the script
        self.root_dir = os.path.dirname(self.script_dir)

        # Get the icon directory for the window
        self.icon_path = self.get_path(os.path.join('icons', "play-fill.ico"))

    def init_window(self):

        # Set window title and icon
        self.setWindowTitle("Client")
        self.setWindowIcon(QIcon(self.icon_path) if self.file_exists(self.icon_path) else QIcon())

        # Apply gradient background based on configuration
        start = self.config["Appearance"].get("Gradient Start", "#265162")
        end   = self.config["Appearance"].get("Gradient End", "#002136")

        # Retrieve the path of the icons directory
        icons_dir = self.get_path('icons')
        check_svg = os.path.join(icons_dir, 'check.svg') if icons_dir else None
        chevron_down_svg = os.path.join(icons_dir, 'chevron-down.svg') if icons_dir else None

        # Create stylesheet overrides
        override = (
            "\n"
            "#clientWindow {\n"
            f"    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {start}, stop:1 {end});\n"
            "}\n"
            "QCheckBox::indicator:checked { "
            f"image: {self.qss_url(check_svg)};"
            " }\n"
            "QComboBox::down-arrow { "
            f"image: {self.qss_url(chevron_down_svg)};"
            " }\n"
        )

        # Load Style Sheets
        style_path = self.get_path(os.path.join('styles', 'style.css'))
        base_css = ""
        if style_path and os.path.isfile(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                base_css = f.read()

        self.setStyleSheet(base_css + override)

        # Set the object name for the stylesheet
        self.setObjectName("clientWindow")  # Set the object name for the stylesheet

        # Make the window fullscreen and borderless
        if self.config['Appearance']['Fullscreen']:
            self.showFullScreen()
            self.setWindowFlags(Qt.FramelessWindowHint)

    def init_ui(self):

        # Create central widget and set layout
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        central_widget.setObjectName("clientWidget")

        # Create a 3x3 grid layout
        grid_layout = QGridLayout(central_widget)

        # Add spacers to the grid layout to create equal-sized sections
        for i in range(3):
            grid_layout.setColumnStretch(i, 1)
            grid_layout.setRowStretch(i, 1)

        # Determine positions from the configuration
        login_pos = self.config['Appearance']['Login Position']
        logo_pos = self.config['Appearance']['Logo Position']

        # Calculate grid positions
        login_grid_pos = self.calculate_position(login_pos)
        logo_grid_pos = self.calculate_position(logo_pos)

        # Load and place the logo image
        logo_file = self.config['Appearance'].get('Logo File') or self.get_path(os.path.join('img', 'logo.png'))
        if logo_file and os.path.isfile(logo_file):
            logo_label = QLabel(central_widget)
            pixmap = QPixmap(logo_file)
            # Set a maximum size for the logo
            logo_label.setMaximumSize(250, 250)
            logo_label.setPixmap(pixmap.scaled(250, 250, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            logo_label.setAlignment(Qt.AlignCenter)
            # Place the logo in the specified position
            grid_layout.addWidget(logo_label, *logo_grid_pos, 1, 1, Qt.AlignCenter)

        # Initialize an empty list to keep track of the tab order
        tab_order_widgets = []

         # Create form layout for login if needed
        form_widget = QWidget()  # A new QWidget to hold the form_layout
        form_layout = QFormLayout(form_widget)
        form_layout.setSpacing(0)  # Set spacing to 0 to remove space between rows

        # Initialize an empty list to keep track of input widgets
        input_widgets = []

        # Add the form items to the form layout
        for category in self.config.keys():
            for name, value in self.config[category].items():
                if category == "General":
                    if name == "Username" and value == "":
                        self.username_edit = QLineEdit(central_widget)
                        self.username_edit.setPlaceholderText("Username")
                        form_layout.addRow(self.username_edit)
                        self.username_edit.returnPressed.connect(self.connect_to_server)

                        # Add the newly created QLineEdit to the list
                        input_widgets.append(self.username_edit)

                        # Set object name for tab order later
                        tab_order_widgets.append(self.username_edit)
                    elif name == "Password" and value == "":
                        self.password_edit = QLineEdit(central_widget)
                        self.password_edit.setEchoMode(QLineEdit.Password)
                        self.password_edit.setPlaceholderText("Password")
                        form_layout.addRow(self.password_edit)
                        self.password_edit.returnPressed.connect(self.connect_to_server)

                        # Add the newly created QLineEdit to the list
                        input_widgets.append(self.password_edit)

                        # Set object name for tab order later
                        tab_order_widgets.append(self.password_edit)
                    elif name == "Domain" and value == "":
                        self.domain_edit = QLineEdit(central_widget)
                        self.domain_edit.setPlaceholderText("Domain")
                        form_layout.addRow(self.domain_edit)
                        self.domain_edit.returnPressed.connect(self.connect_to_server)

                        # Add the newly created QLineEdit to the list
                        input_widgets.append(self.domain_edit)

                        # Set object name for tab order later
                        tab_order_widgets.append(self.domain_edit)
                    elif name == "Server Address" and value == "":
                        self.server_edit = QLineEdit(central_widget)
                        self.server_edit.setPlaceholderText("Server Address")
                        self.server_edit.returnPressed.connect(self.connect_to_server)
                        form_layout.addRow(self.server_edit)

                        # Add the newly created QLineEdit to the list
                        input_widgets.append(self.server_edit)

                        # Set object name for tab order later
                        tab_order_widgets.append(self.server_edit)
                    elif name == "Port" and value == "":
                        self.port_edit = QLineEdit(central_widget)
                        self.port_edit.setPlaceholderText("Port")
                        form_layout.addRow(self.port_edit)
                        self.port_edit.returnPressed.connect(self.connect_to_server)

                        # Add the newly created QLineEdit to the list
                        input_widgets.append(self.port_edit)

                        # Set object name for tab order later
                        tab_order_widgets.append(self.port_edit)

        # Check if we have any input widgets created
        if input_widgets:
            # Set object name for the first and last QLineEdit widgets
            input_widgets[0].setObjectName("firstLineEdit")  # First input
            input_widgets[-1].setObjectName("lastLineEdit")  # Last input

        # Create horizontal layout for the buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)

        # Create buttons
        self.connect_button = QPushButton(" Connect", central_widget)
        self.connect_button.setObjectName("ConnectBTN")
        self.set_svg_icon(self.connect_button, self.get_path(os.path.join("icons/box-arrow-in-right.svg")))
        self.connect_button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.connect_button.clicked.connect(self.connect_to_server)
        button_layout.addWidget(self.connect_button)

        self.config_button = QPushButton("", central_widget)
        self.config_button.setObjectName("ConfigurationsBTN")
        self.set_svg_icon(self.config_button, self.get_path(os.path.join("icons/gear-fill.svg")))
        self.config_button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.config_button.clicked.connect(self.launch_prompt)
        buttons_layout.addWidget(self.config_button)

        if not self.config['Appearance']['Hide Diagnostics']:
            self.diagnostics_button = QPushButton("", self)
            self.diagnostics_button.setObjectName("DiagnosticsBTN")
            self.set_svg_icon(self.diagnostics_button, self.get_path(os.path.join("icons/activity.svg")))
            self.diagnostics_button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
            self.diagnostics_button.clicked.connect(self.launch_diagnostics)
            buttons_layout.addWidget(self.diagnostics_button)

        if not self.config['Appearance']['Hide Exit']:
            self.exit_button = QPushButton("", central_widget)
            self.exit_button.setObjectName("ExitBTN")
            self.set_svg_icon(self.exit_button, self.get_path(os.path.join("icons/x-octagon.svg")))
            self.exit_button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
            self.exit_button.clicked.connect(self.close)
            buttons_layout.addWidget(self.exit_button)

        if not self.config['Appearance']['Hide Restart']:
            self.restart_button = QPushButton("", central_widget)
            self.restart_button.setObjectName("RestartBTN")
            self.set_svg_icon(self.restart_button, self.get_path(os.path.join("icons/arrow-repeat.svg")))
            self.restart_button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
            self.restart_button.clicked.connect(self.restart_system)
            buttons_layout.addWidget(self.restart_button)

        if not self.config['Appearance']['Hide Shutdown']:
            self.shutdown_button = QPushButton("", central_widget)
            self.shutdown_button.setObjectName("ShutdownBTN")
            self.set_svg_icon(self.shutdown_button, self.get_path(os.path.join("icons/power.svg")))
            self.shutdown_button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
            self.shutdown_button.clicked.connect(self.shutdown_system)
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
        if not self.config['Appearance']['Hide Exit']:
            self.setTabOrder(self.config_button, self.exit_button)

        # Add the form layout to the grid layout
        form_widget.setLayout(form_layout)
        grid_layout.addWidget(form_widget, *login_grid_pos, 1, 1, Qt.AlignCenter)

    def get_widget_value(self, widget):
        # Determine the type of widget and return its value accordingly
        if isinstance(widget, QLineEdit):
            return widget.text()
        elif isinstance(widget, QComboBox):
            return widget.currentText()
        elif isinstance(widget, QCheckBox):
            return widget.isChecked()
        elif isinstance(widget, QSpinBox):
            return widget.value()
        elif isinstance(widget, ColorButton):
            return widget.hex()
        else:
            return None  # Or some default value, or raise an exception

    def get_widget_from_config(self, category, name):
        # Retrieve widget from self.widgets
        category_dict = self.widgets.get(category, {})
        if isinstance(category_dict, dict):
            return category_dict.get(name)
        return None

    def set_widget_value(self, widget, value):
        # Set value to the widget based on its type
        if isinstance(widget, QLineEdit):
            widget.setText(value)
        elif isinstance(widget, QComboBox):
            index = widget.findText(value)
            if index >= 0:
                widget.setCurrentIndex(index)
        elif isinstance(widget, QCheckBox):
            widget.setChecked(value)
        elif isinstance(widget, QSpinBox):
            widget.setValue(value)
        elif isinstance(widget, ColorButton):
            widget._color = QColor(value if value else "#000000")
            widget._update_style()

    def set_svg_icon(self, button, svg_path, size=(18, 18)):

        # Check if the SVG file exists
        if not self.file_exists(svg_path):
            button.setIcon(QIcon())  # no icon, still functional
            return

        # Load SVG file
        renderer = QSvgRenderer(svg_path)

        # Create an empty QPixmap with the desired size
        pixmap = QPixmap(size[0], size[1])
        pixmap.fill(Qt.transparent)  # Fill the pixmap with transparent color

        # Paint the SVG onto the QPixmap
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()

        # Convert QPixmap to QIcon and set it to the button
        icon = QIcon(pixmap)
        button.setIcon(icon)
        button.setIconSize(pixmap.size())

    def calculate_position(self, position_string):
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
        return position_map.get(position_string, (1, 1))  # Default to center-center if not found

    def reset_ui(self):
        """
        Reset the UI by reloading configurations and resetting the widgets.
        """
        # Reload configuration settings
        self.load_config()
        # Reload widgets
        self.load_widgets()
        # Clear existing UI components
        self.clear_ui()
        # Reinitialize the UI with updated configurations
        self.init_ui()

    def clear_ui(self):
        """
        Clear existing UI components.
        """
        central_widget = self.centralWidget()
        if central_widget is not None:
            # Delete the central widget and its children
            central_widget.deleteLater()

    def restart_system(self):
        choice = self._msgbox("System Restart", "Are you sure you want to restart the system?", icon_key="question", buttons=("Yes","No"), default="No")
        if choice == "Yes":
            try:
                if sys.platform == "win32":
                    subprocess.run(["shutdown", "/r", "/t", "0"], check=True)
                else:
                    subprocess.run(["sudo", "shutdown", "-r", "now"], check=True)
            except subprocess.CalledProcessError as e:
                self._msgbox("Error", f"Failed to restart the system: {e}", icon_key="error")

    def shutdown_system(self):
        choice = self._msgbox("System Shutdown", "Are you sure you want to shutdown the system?", icon_key="question", buttons=("Yes","No"), default="No")
        if choice == "Yes":
            try:
                if sys.platform == "win32":
                    subprocess.run(["shutdown", "/s", "/t", "0"], check=True)
                else:
                    subprocess.run(["sudo", "shutdown", "-h", "now"], check=True)
            except subprocess.CalledProcessError as e:
                self._msgbox("Error", f"Failed to shutdown the system: {e}", icon_key="error")

    def launch_prompt(self):

        # Check if the password is set
        if self.config["Administration"]["Password"] == "":

            # Launch the configurations window
            self.launch_configurations()
        else:

            # Create a password prompt
            self.prompt_dialog = QDialog(self)
            self.prompt_dialog.setWindowModality(Qt.WindowModal)
            self.prompt_dialog.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.CustomizeWindowHint | Qt.WindowCloseButtonHint)
            self.prompt_dialog.setObjectName("promptWindow")

            # Create form layout for login if needed
            form_layout = QFormLayout(self.prompt_dialog)
            form_layout.setSpacing(0)  # Set spacing to 0 to remove space between rows

            # Initialize QLineEdit for password with echo mode set to Password
            self.adminPasswordLineEdit = QLineEdit()
            self.adminPasswordLineEdit.setEchoMode(QLineEdit.Password)
            self.adminPasswordLineEdit.setPlaceholderText("Password")
            self.adminPasswordLineEdit.returnPressed.connect(self.validate_password)

            # Add password to the layout
            form_layout.addRow(self.adminPasswordLineEdit)

            # Add the form layout to the grid layout
            self.prompt_dialog.setLayout(form_layout)

            # show the dialog
            self.prompt_dialog.show()

    def validate_password(self):

        # Check if the password is correct
        if self.adminPasswordLineEdit.text() == self.config["Administration"]["Password"]:

            # Launch the configurations window
            self.launch_configurations()

        # Clear the password line edit
        self.adminPasswordLineEdit.clear()

        # Hide the modal dialog
        self.prompt_dialog.hide()

    def select_folder(self):
        folder_dialog = QFileDialog(self)
        folder_dialog.setFileMode(QFileDialog.Directory)
        if folder_dialog.exec_():
            selected_folder = folder_dialog.selectedFiles()[0]
            folder_data = {"path": selected_folder, "enabled": True}
            self.config["FreeRDP"]["Folders"]["Folders"].append(folder_data)
            self.add_folder_to_list(folder_data)
            self.on_configuration_changed()

    def add_folder_to_list(self, folder_data):
        folder_widget = QWidget()
        folder_layout = QHBoxLayout(folder_widget)

        folder_label = QLabel(folder_data["path"])
        folder_layout.addWidget(folder_label)

        folder_checkbox = QCheckBox("Enabled")
        folder_checkbox.setChecked(folder_data["enabled"])
        folder_layout.addWidget(folder_checkbox)
        folder_checkbox.stateChanged.connect(lambda state, fd=folder_data: self.update_folder_enabled(fd, state))

        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(lambda: self.remove_folder(folder_widget, folder_data))
        folder_layout.addWidget(delete_button)

        self.folder_list_layout.addWidget(folder_widget)
        self.on_configuration_changed()

    def update_folder_enabled(self, folder_data, state):
        folder_data["enabled"] = bool(state)
        self.on_configuration_changed()

    def remove_folder(self, folder_widget, folder_data):
        self.folder_list_layout.removeWidget(folder_widget)
        folder_widget.deleteLater()
        self.config["FreeRDP"]["Folders"]["Folders"].remove(folder_data)
        self.on_configuration_changed()

    def find_widget_index(self, layout, widget):
        for row in range(layout.rowCount()):
            if layout.itemAt(row, QFormLayout.FieldRole).widget() == widget:
                return row
        return None

    def qss_url(self, p: str | None) -> str:
        """
        Return a quoted url("...") suitable for Qt stylesheets, or empty string.
        """
        if not p:
            return 'url("")'
        # Qt accepts forward slashes
        return f'url("{p.replace(os.sep, "/")}")'

    def file_exists(self, p: str | None) -> bool:
        return isinstance(p, str) and os.path.isfile(p)

    def gen_logo_button(self, logo_file):

        """
        Recreate the logo file button with the current logo path and a small 72px preview.
        """

        # Remove the current widget from the layout, without deleting the layout
        if hasattr(self, 'logo_file_button'):
             # Retrieve the current index before removing the row
            if hasattr(self, 'logo_layout'):
                # Get the index of the current row
                current_row_index = self.logo_layout.getWidgetPosition(self.logo_file_button)[0]
            # Remove the existing button
            self.logo_file_button.deleteLater()

        self.logo_file_button = QPushButton("Select Logo File")
        self.config["Appearance"]["Logo File"] = logo_file
        self.update_logo_button(logo_file)  # Update with the new logo
        self.logo_file_button.clicked.connect(self.select_logo_file)

        # Apply custom styling to the button
        self.logo_file_button.setFixedSize(88, 96)  # Set button size (72px image + 4px padding on each side)
        self.logo_file_button.setStyleSheet("padding: 4px;")  # Apply 4px padding to the button

        # Check if logo_layout and logo_row exist and reset the row
        if hasattr(self, 'logo_layout') and hasattr(self, 'logo_row'):

            # Reset the existing row by adding the updated widget
            self.logo_layout.removeRow(current_row_index)  # Remove the previous row

            # Re-insert the updated widget at the same index
            self.logo_row = self.logo_layout.insertRow(current_row_index, QLabel("Logo File"), self.logo_file_button)

        return self.logo_file_button

    def update_logo_button(self, logo_file):
        """
        Update the logo button with a 72px preview, falling back to bundled img/logo.png.
        """
        # Resolve fallback if needed
        candidate = logo_file if isinstance(logo_file, str) else None
        if not (candidate and os.path.isfile(candidate)):
            candidate = self.get_path(os.path.join('img', 'logo.png'))

        if candidate and os.path.isfile(candidate):
            pixmap = QPixmap(candidate)
            if not pixmap.isNull():
                scaled = pixmap.scaled(72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.logo_file_button.setIcon(QIcon(scaled))
                self.logo_file_button.setIconSize(scaled.size())
                self.logo_file_button.setText("")
            else:
                print(f"Failed to load logo: {candidate}")
                self.logo_file_button.setIcon(QIcon())
                self.logo_file_button.setText("Invalid Logo File")
        else:
            print(f"File not found: {candidate}")
            self.logo_file_button.setIcon(QIcon())
            self.logo_file_button.setText("Select Logo File")

        self.logo_file_button.update()
        self.logo_file_button.repaint()

    def select_logo_file(self):
        """
        File selection dialog for choosing a PNG logo file. Updates the button but does not copy the file yet.
        """
        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.ExistingFile)
        file_dialog.setNameFilters(["PNG Files (*.png)"])  # Only allow PNG files

        if file_dialog.exec_():
            selected_file = file_dialog.selectedFiles()[0]
            if os.path.isfile(selected_file):
                # Store the selected logo file path but don't save it yet
                self.selected_logo_file = os.path.join(selected_file)
                # Update the button to reflect the new logo preview
                self.gen_logo_button(self.selected_logo_file)
                self.on_configuration_changed()  # Mark as configuration changed

    def update_application(self):
        try:
            subprocess.run(['git', 'pull'], check=True, cwd=self.root_dir)
            self._msgbox("Update", "Application updated successfully. Restarting...", icon_key="success")
            QApplication.quit()
            subprocess.run([sys.executable] + sys.argv)
        except subprocess.CalledProcessError as e:
            self._msgbox("Error", f"Failed to update the application: {e}", icon_key="error")

    def launch_configurations(self):
        self.configurations_dialog = QDialog(self)
        self.configurations_dialog.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.CustomizeWindowHint | Qt.WindowCloseButtonHint)
        self.configurations_dialog.setObjectName("configurationsWindow")

        self.configurations_layout = QVBoxLayout(self.configurations_dialog)
        self.configurations_layout.setSpacing(0)

        self.configurations_tab_widget = QTabWidget()
        self.configurations_layout.addWidget(self.configurations_tab_widget)

        def bind_change_signals(w):
            if isinstance(w, QLineEdit):
                w.textChanged.connect(self.on_configuration_changed)
            elif isinstance(w, QCheckBox):
                w.stateChanged.connect(self.on_configuration_changed)
            elif isinstance(w, QComboBox):
                w.currentTextChanged.connect(self.on_configuration_changed)
            elif isinstance(w, QSpinBox):
                w.valueChanged.connect(self.on_configuration_changed)

        def add_simple_form_tab(title, mapping):
            tab = QWidget()
            layout = QFormLayout(); tab.setLayout(layout)
            for name, widget in mapping.items():
                if isinstance(widget, dict):
                    # shouldn't happen in simple tab
                    continue
                if isinstance(widget, list):
                    # Folders list special case
                    if title == "Folders" and name == "Folders":
                        layout.addRow(QLabel(name), self.folder_add_button)
                        for folder in self.config["FreeRDP"]["Folders"]["Folders"]:
                            self.add_folder_to_list(folder)
                        layout.addRow(self.folder_list_layout)
                    continue
                layout.addRow(QLabel(name), widget)
                bind_change_signals(widget)
            return tab

        def add_subtabbed_category(title, submaps, show_filter=None):
            """
            Creates a top-level tab that contains a QTabWidget with sub-tabs.
            show_filter: optional callable(subname:str) -> bool to conditionally include a sub-tab.
            """
            top = QWidget()
            v = QVBoxLayout(top)
            sub = QTabWidget()
            v.addWidget(sub)

            for subname, submap in submaps.items():
                if callable(show_filter) and not show_filter(subname):
                    continue
                subtab = add_simple_form_tab(subname, submap)
                sub.addTab(subtab, subname)
            return top

        # ---- Top-level tabs ----
        # General (simple form)
        general_tab = add_simple_form_tab("General", self.widgets["General"])
        self.configurations_tab_widget.addTab(general_tab, "General")

        # FreeRDP (subtabs: Display, Devices, Folders, Experience)
        freerdp_tab = add_subtabbed_category("FreeRDP", self.widgets["FreeRDP"])
        self.configurations_tab_widget.addTab(freerdp_tab, "FreeRDP")

        # Networking (subtabs: WiFi (only Linux), OpenVPN, WireGuard)
        def _net_filter(name: str) -> bool:
            if name == "WiFi":
                return self.get_os() == "linux"
            return True
        networking_tab = add_subtabbed_category("Networking", self.widgets["Networking"], show_filter=_net_filter)
        self.configurations_tab_widget.addTab(networking_tab, "Networking")

        # Appearance (simple form)
        appearance_tab = add_simple_form_tab("Appearance", self.widgets["Appearance"])
        self.configurations_tab_widget.addTab(appearance_tab, "Appearance")

        # Administration (simple form)
        admin_tab = add_simple_form_tab("Administration", self.widgets["Administration"])
        self.configurations_tab_widget.addTab(admin_tab, "Administration")

        # Save button
        self.save_button = QPushButton("Save")
        self.save_button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.configurations_layout.addWidget(self.save_button)
        self.save_button.clicked.connect(self.save_config)

        # palettes for Save
        self.originalPalette = self.save_button.palette()
        self.highlightedPalette = QPalette(self.originalPalette)
        self.highlightedPalette.setColor(QPalette.Button, QColor("#198754"))

        self.configurations_dialog.show()

    def launch_diagnostics(self):
        self.diag_window = DiagnosticsWindow(self)
        self.diag_window.show()
        # optionally auto-run:
        self.diag_window.start()

    def on_configuration_changed(self):

        # Change background color of the save button to highlight
        self.save_button.setObjectName("unsavedChanges")  # Change object name to apply new style
        self.save_button.style().unpolish(self.save_button)  # Unpolish to clear the existing styling
        self.save_button.style().polish(self.save_button)  # Re-apply the stylesheet
        self.save_button.update()  # Update the button's appearance

        # Live preview: reapply stylesheet override using the current widget values
        try:
            with open(self.get_path(os.path.join('styles/style.css')), 'r') as f:
                base_css = f.read()
            # Pull values from current widgets if they exist
            start_widget = self.get_widget_from_config("Appearance", "Gradient Start")
            end_widget = self.get_widget_from_config("Appearance", "Gradient End")
            if start_widget and end_widget:
                self.config["Appearance"]["Gradient Start"] = self.get_widget_value(start_widget)
                self.config["Appearance"]["Gradient End"]   = self.get_widget_value(end_widget)
            self.apply_dynamic_client_stylesheet(base_css)
        except Exception:
            pass

    def save_config(self):
        """
        Persist all settings to config/*.cfg (supports nested categories).
        """
        config_dir = os.path.join(self.root_dir, 'config')
        os.makedirs(config_dir, exist_ok=True)

        def _gather_values(mapping, cfg_ref):
            out = {}
            for name, w in mapping.items():
                if isinstance(w, dict):
                    out[name] = _gather_values(w, cfg_ref.get(name, {}))
                elif isinstance(w, list):
                    # only used for Folders list
                    if "Folders" in cfg_ref:
                        out[name] = cfg_ref["Folders"]
                    else:
                        out[name] = []
                else:
                    out[name] = self.get_widget_value(w)
            return out

        # Collect per top-category
        to_write = {}
        for topcat, mapping in self.widgets.items():
            if topcat in ("FreeRDP","Networking"):
                to_write[topcat] = _gather_values(mapping, self.config.get(topcat, {}))
            else:
                to_write[topcat] = _gather_values(mapping, self.config.get(topcat, {}))

        # Handle logo copy (same behavior as before)
        if "Appearance" in to_write and "Logo File" in to_write["Appearance"]:
            if hasattr(self, 'selected_logo_file') and os.path.isfile(self.selected_logo_file):
                shutil.copyfile(self.selected_logo_file, os.path.join(config_dir, 'logo.png'))
                to_write["Appearance"]["Logo File"] = os.path.join(config_dir, 'logo.png')

        # Write new style files
        file_map = {
            "General": "general.cfg",
            "FreeRDP": "freerdp.cfg",
            "Networking": "networking.cfg",
            "Appearance": "appearance.cfg",
            "Administration": "administration.cfg",
        }
        for top, fname in file_map.items():
            p = os.path.join(config_dir, fname)
            with open(p, "w") as f:
                json.dump(to_write[top], f, indent=2)

        # Update in-memory config
        self.config = to_write

        # Reset Save button styling + refresh UI
        self.save_button.setObjectName("saveButton")
        self.save_button.style().unpolish(self.save_button)
        self.save_button.style().polish(self.save_button)
        self.save_button.update()

        self.reset_ui()
        self.configurations_dialog.hide()

    def import_settings(self):
        try:
            config_dir = os.path.join(self.root_dir, 'config')
            os.makedirs(config_dir, exist_ok=True)

            dlg = QFileDialog(self)
            dlg.setAcceptMode(QFileDialog.AcceptOpen)
            dlg.setNameFilter("JSON Files (*.json)")

            if not dlg.exec_():
                return

            import_file = dlg.selectedFiles()[0]
            with open(import_file, "r") as f:
                imported = json.load(f)

            def _apply(imported_dict, widgets_dict, config_ref):
                for k, v in imported_dict.items():
                    if isinstance(v, dict) and isinstance(widgets_dict.get(k), dict):
                        # recurse
                        _apply(v, widgets_dict[k], config_ref.setdefault(k, {}))
                    else:
                        w = widgets_dict.get(k)
                        if w is not None and not isinstance(w, dict):
                            self.set_widget_value(w, v)
                        else:
                            config_ref[k] = v

            _apply(imported, self.widgets, self.config)

            # handle logo (base64) if present
            try:
                logo_data = imported.get("Appearance", {}).get("Logo File")
                if isinstance(logo_data, dict) and "content" in logo_data and "filename" in logo_data:
                    logo_bytes = base64.b64decode(logo_data["content"])
                    logo_path = os.path.join(config_dir, "import.png")
                    with open(logo_path, "wb") as out:
                        out.write(logo_bytes)
                    self.config["Appearance"]["Logo File"] = logo_path
                    self.selected_logo_file = logo_path
                    self.gen_logo_button(logo_path)
            except Exception as e:
                print(f"Logo import warning: {e}")

            self.on_configuration_changed()
            QMessageBox.information(self, "Import Complete", "Settings successfully imported. Press 'Save' to apply changes.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to import settings: {e}")

    def export_settings(self):
        try:
            # Collect all current settings
            export_data = {}
            for category, settings in self.config.items():
                export_data[category] = settings

            # Handle the custom logo (convert to base64)
            logo_file_path = self.config["Appearance"].get("Logo File", "")
            if logo_file_path and os.path.isfile(logo_file_path):
                with open(logo_file_path, "rb") as logo_file:
                    encoded_logo = base64.b64encode(logo_file.read()).decode("utf-8")
                    export_data["Appearance"]["Logo File"] = {
                        "filename": os.path.basename(logo_file_path),
                        "content": encoded_logo
                    }

            # Open a file dialog to select where to save the export
            file_dialog = QFileDialog(self)
            file_dialog.setAcceptMode(QFileDialog.AcceptSave)
            file_dialog.setNameFilter("JSON Files (*.json)")
            file_dialog.setDefaultSuffix("json")

            if file_dialog.exec_():
                export_file = file_dialog.selectedFiles()[0]
                with open(export_file, "w") as f:
                    json.dump(export_data, f, indent=4)

                QMessageBox.information(self, "Export Complete", "Settings successfully exported.")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export settings: {e}")

    def get_freerdp_version(self, freerdp_path):
        try:
            res = subprocess.run([freerdp_path, '+version'], capture_output=True, text=True)
            if res.returncode != 0:
                return None
            lines = [ln.strip() for ln in res.stdout.splitlines() if ln.strip()]
            if not lines:
                return None
            parts = lines[0].split()
            # Find something like 3.3.17 or 3.8 etc.
            for token in parts:
                if re.match(r'^\d+\.\d+(\.\d+)?$', token):
                    return token
            return None
        except Exception as e:
            print(f"Error retrieving FreeRDP version: {e}")
            return None

    def get_printers(self):

        if self.get_os() == "macos":

            # Run the lpstat -p command to get the list of printers
            try:
                result = subprocess.run(['lpstat', '-p'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

                # Check if the command executed successfully
                if result.returncode != 0:
                    print("Failed to run lpstat command. Error:", result.stderr)
                    return []

                # Initialize a list to store printer and driver pairs
                printers = []

                # Path to CUPS PPD directory
                ppd_dir = '/etc/cups/ppd'

                # Parse the output to find printer names and look for their corresponding PPD files
                for line in result.stdout.splitlines():
                    match = re.match(r'printer\s+(\S+)', line)
                    if match:
                        printer_name = match.group(1)
                        ppd_file = os.path.join(ppd_dir, f'{printer_name}.ppd')

                        # Check if the PPD file exists for this printer
                        if os.path.exists(ppd_file):
                            # Extract driver information from the PPD file
                            driver = self.get_driver(ppd_file)
                            printers.append((printer_name, driver))
                        else:
                            printers.append((printer_name, None))  # No PPD file found, driver is None

                # Debugging: Print the list of printers found
                print("Printers found:", printers)

                return printers

            except Exception as e:
                print(f"An error occurred: {e}")
                return []
        # elif self.get_os() == "linux":
        else:
            return []

    def get_driver(self, ppd_file):

        if self.get_os() == "macos":

            # Read the PPD file and extract the driver name
            try:
                with open(ppd_file, 'r') as f:
                    for line in f:
                        # Find the line that starts with *NickName or *DriverName, which contains the driver info
                        if line.startswith('*NickName:') or line.startswith('*DriverName:'):
                            # Extract the driver name from the line
                            driver_name = line.split(':', 1)[1].strip().strip('"')
                            return driver_name
            except Exception as e:
                print(f"Error reading PPD file {ppd_file}: {e}")
                return None
        else:
            return None

    def get_freerdp_bin_path(self):
        """
        Prefer the repo-bundled xfreerdp for the current OS/arch, then PATH.
        """
        osname = self.get_os()

        # Map OS -> bundled path
        if osname == 'macos':
            cand = self.get_path('freerdp/macos/xfreerdp')
        elif osname == 'linux':
            cand = self.get_path('freerdp/linux/xfreerdp')
        else:
            cand = None

        if cand and os.path.exists(cand) and os.access(cand, os.X_OK):
            return cand

        # If present but not executable, try to make it so
        if cand and os.path.exists(cand) and not os.access(cand, os.X_OK):
            try:
                os.chmod(cand, 0o755)
                return cand
            except Exception:
                pass

        # Fallback to PATH
        return shutil.which('xfreerdp') or 'xfreerdp'

    def gen_command(self):

        # Get the path to the bundled xfreerdp
        freerdp_path = self.get_freerdp_bin_path()

        # Get FreeRDP version
        freerdp_version = self.get_freerdp_version(freerdp_path)

        # Determine major version number (e.g., 2.x or 3.x)
        major_version = int(freerdp_version.split('.')[0]) if freerdp_version else None

        # Construct the command using the bundled xfreerdp
        command = [freerdp_path]

        # ---- Safe defaults to avoid activation stalls ----
        command += [
            "/cert:ignore",     # ignore certificate by default
            "/sec:nla",         # explicit security (same as most servers expect)
            "-multitransport",  # avoid RDPEUDP weirdness through NAT/middleboxes
            "/timeout:30000",   # 30 second connection timeout
        ]

        # Enable debug logging if set
        if self.config["Administration"]["Debug logging"]:
            command += ["/log-level:DEBUG"]

        # Gather the configuration values, retrieving from widgets if necessary
        general_server_address = self.config["General"]["Server Address"] or self.server_edit.text()
        general_port = self.config["General"]["Port"] or self.port_edit.value()
        general_username = self.config["General"]["Username"] or self.username_edit.text()
        general_password = self.config["General"]["Password"] or self.password_edit.text()
        general_domain = self.config["General"]["Domain"] or self.domain_edit.text()
        display_resolution = self.config["FreeRDP"]["Display"]["Resolution"]
        display_use_all_monitors = self.config["FreeRDP"]["Display"]["Use all monitors"]
        display_fullscreen = self.config["FreeRDP"]["Display"]["Start session in fullscreen"]
        display_fit_window = self.config["FreeRDP"]["Display"]["Fit session to window"]
        audio_play_sound = self.config["FreeRDP"]["Devices"]["Play sound"]
        audio_record_sound = self.config["FreeRDP"]["Devices"]["Record sound"]
        devices_printers = self.config["FreeRDP"]["Devices"]["Printers"]
        devices_smart_cards = self.config["FreeRDP"]["Devices"]["Smart Cards"]
        devices_ports = self.config["FreeRDP"]["Devices"]["Ports"]
        devices_drives = self.config["FreeRDP"]["Devices"]["Drives"]
        folders_redirect = self.config["FreeRDP"]["Folders"]["Redirect"]
        folders_folders = self.config["FreeRDP"]["Folders"]["Folders"]
        experience_clipboard = self.config["FreeRDP"]["Experience"]["Clipboard"]
        experience_remotefx = self.config["FreeRDP"]["Experience"]["RemoteFX"]
        experience_smooth_fonts = self.config["FreeRDP"]["Experience"]["Smooth Fonts"]
        experience_desktop_composition = self.config["FreeRDP"]["Experience"]["Desktop Composition"]
        experience_full_window_drag = self.config["FreeRDP"]["Experience"]["Full Window Drag"]
        experience_menu_animations = self.config["FreeRDP"]["Experience"]["Menu Animations"]
        experience_disable_themes = self.config["FreeRDP"]["Experience"]["Disable Themes"]
        experience_disable_wallpaper = self.config["FreeRDP"]["Experience"]["Disable Wallpaper"]

        # Add server address and port
        if general_port:
            command.append(f"/v:{general_server_address}:{general_port}")
        else:
            command.append(f"/v:{general_server_address}")

        # Add username and domain
        if general_username:
            command.append(f"/u:{general_username}")
        if general_domain:
            command.append(f"/d:{general_domain}")

        # Add password securely
        if general_password:
            if major_version and major_version >= 3:
                command.append("/from-stdin:force")
            else:
                command.append("/from-stdin")

        # Add display settings
        if display_resolution:
            command.append(f"/size:{display_resolution}")
        if display_use_all_monitors:
            command.append("/multimon")
        if display_fullscreen:
            command.append("/f")
        if display_fit_window:
            command.append("/smart-sizing")

        # Add Audio settings
        if major_version and major_version < 3:
            if audio_play_sound == "Never":
                command.append("/sound:off")
            elif audio_play_sound == "On this computer":
                command.append("/sound:sys:alsa")
            elif audio_play_sound == "On the remote computer":
                command.append("/sound:sys:rdpsnd")
        else:
            # Adjust the sound options for FreeRDP 3.x
            if audio_play_sound == "Never":
                command.append("/audio-mode:2")
            elif audio_play_sound == "On this computer":
                command.append("/audio-mode:0")
            elif audio_play_sound == "On the remote computer":
                command.append("/audio-mode:1")

        # Add Devices Settings
        if devices_printers:
            command.append("/printer")
        if devices_drives:
            command.append("/drives")
        if devices_ports:
            command.append("/usb:auto")
        # if major_version and major_version < 3:
        #     if devices_smart_cards:
        #         command.append("/smartcard")
        #     if devices_ports:
        #         command.append(f"/serial:{redirect_ports}")
        # else:
            # Adjust the redirection options for FreeRDP 3.x
        #     if devices_smart_cards:
        #         command.append("/smartcard:off")
        #     if devices_ports:
        #         command.append("/serial:off")

        # Add Experiance Settings
        if experience_clipboard:
            command.append("+clipboard")
        if experience_remotefx:
            command.append("/rfx /gfx /gfx-h264 /gdi:hw")
        if experience_smooth_fonts:
            command.append("+fonts")
        if experience_desktop_composition:
            command.append("+aero")
        if experience_full_window_drag:
            command.append("+window-drag")
        if experience_menu_animations:
            command.append("+menu-anims")
        if experience_disable_themes:
            command.append("-themes")
        if experience_disable_wallpaper:
            command.append("-wallpaper")

        # Debugging: Print the final command
        if self.config["Administration"]["Debug logging"]:
            print(f"Generated freerdp({freerdp_version}) command:")
            debug_cmd = []
            for tok in command:
                if tok.startswith("/p:"):
                    debug_cmd.append("/p:********")
                else:
                    debug_cmd.append(tok)
            print(" ".join(debug_cmd))

        return command

    def _svg_to_pixmap(self, svg_path: str, size: QSize = QSize(42, 42)) -> QPixmap:
        """
        Render an SVG to a hi-DPI-aware QPixmap for use in QMessageBox.
        """
        renderer = QSvgRenderer(svg_path)
        dpr = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0
        w = max(1, int(size.width()  * dpr))
        h = max(1, int(size.height() * dpr))
        pm = QPixmap(w, h)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        renderer.render(painter)
        painter.end()
        if dpr != 1.0:
            pm.setDevicePixelRatio(dpr)
        return pm

    def _msgbox(self, title: str, text: str, icon_key: str = "info", buttons: tuple = ("OK",), default: str | None = None, parent=None) -> str:
        parent = parent or self
        m = QMessageBox(parent)
        m.setWindowTitle(title)
        m.setText(text)
        m.setObjectName("customMsgBox")  # lets your QSS style it

        # map logical keys to your Bootstrap-ish icon file names (adjust to your set)
        icon_map = {
            "info":     "info-circle.svg",
            "success":  "check-circle.svg",
            "warning":  "exclamation-triangle.svg",
            "error":    "x-octagon.svg",
            "question": "question-circle.svg",
        }
        svg = self.get_path(os.path.join("icons", icon_map.get(icon_key, icon_map["info"])))
        if svg and os.path.exists(svg):
            m.setIconPixmap(self._svg_to_pixmap(svg, QSize(42, 42)))
        else:
            # graceful fallback to a built-in icon
            builtins = {
                "info": QMessageBox.Information,
                "success": QMessageBox.Information,
                "warning": QMessageBox.Warning,
                "error": QMessageBox.Critical,
                "question": QMessageBox.Question,
            }
            m.setIcon(builtins.get(icon_key, QMessageBox.Information))

        # buttons
        label_to_std = {
            "OK": QMessageBox.Ok,
            "Cancel": QMessageBox.Cancel,
            "Yes": QMessageBox.Yes,
            "No": QMessageBox.No,
            "Retry": QMessageBox.Retry,
            "Ignore": QMessageBox.Ignore,
            "Close": QMessageBox.Close,
            "Open log": QMessageBox.ActionRole,  # special, will add as an action button
        }
        clicked_label = None
        added = []
        for b in buttons:
            if b == "Open log":
                btn = m.addButton("Open log", QMessageBox.ActionRole)
            else:
                btn = m.addButton(label_to_std.get(b, QMessageBox.Ok))
            added.append((b, btn))

        if default:
            for lbl, btn in added:
                if lbl == default:
                    m.setDefaultButton(btn if isinstance(btn, QMessageBox.StandardButton) else None)
                    try:
                        m.setEscapeButton(btn)
                    except Exception:
                        pass

        m.exec_()
        which = m.clickedButton()
        for lbl, btn in added:
            if btn is which:
                clicked_label = lbl
                break
        return clicked_label or ""

    def show_log(self, text: str, focus: str = None):
        # focus becomes initial filter; lines not matching are hidden; matches are yellow
        self.log_window = LogWindow(self, text=text, filter_text=focus)
        self.log_window.show()
        self.log_window.raise_()
        self.log_window.activateWindow()

    def open_last_log(self):
        text = self.last_log_text or ""
        if not text.strip():
            self._msgbox("No log available",
                        "There is no connection log yet. Try connecting first.",
                        icon_key="info")
            return
        self.show_log(text, focus="ERROR")

    def connect_to_server(self):

        # Create a "connecting" message and a spinner
        self.connection_dialog = QProgressDialog("Connecting to server...", "Cancel", 0, 0, self)
        self.connection_dialog.setWindowModality(Qt.WindowModal)
        self.connection_dialog.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.CustomizeWindowHint | Qt.WindowCloseButtonHint)
        self.connection_dialog.setMinimumDuration(0)  # Show immediately
        self.connection_dialog.setAutoReset(False)
        self.connection_dialog.setFixedWidth(300)

        # Add a cancel button
        self.cancel_button = QPushButton("Cancel", self.connection_dialog)
        self.cancel_button.setObjectName("CancelBTN")
        self.cancel_button.clicked.connect(self.connection_timeout)
        self.cancel_button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.connection_dialog.setCancelButton(self.cancel_button)

        # Show the dialog
        self.connection_dialog.show()

        # Start the connection
        self.connect()

    def connect(self):
        command = self.gen_command()
        show_cert_warning = self.config["FreeRDP"]["Experience"].get("Show certificate warning", False)
        debug_enabled = self.config.get("Administration", {}).get("Debug logging", False)
        general_password = self.config["General"]["Password"] or getattr(self, "password_edit", QLineEdit()).text()
        stdin_password = general_password if any(arg.startswith("/from-stdin") for arg in command) else None
        self.connection_thread = ConnectionThread(command, show_cert_warning=show_cert_warning, stdin_password=stdin_password, debug_enabled=debug_enabled)
        self.connection_thread.connection_success.connect(self.on_connection_success)
        self.connection_thread.connection_failed.connect(self.on_connection_failed)
        self.connection_thread.connection_info.connect(self.on_connection_info)
        self.connection_thread.start()

    def on_connection_info(self, line: str):
        try:
            self.connection_dialog.setLabelText(f"Connecting…\n{line}")
        except Exception:
            pass

    def on_connection_success(self):
        self.connection_dialog.hide()
        self._msgbox("Connected", "Connection to the server was successful.", icon_key="success")
        self.reset_ui()

    def on_connection_failed(self, title: str, details: str, raw_log: str):
        self.last_log_text = raw_log or ""
        self.connection_dialog.hide()
        debug_enabled = self.config.get("Administration", {}).get("Debug logging", False)

        # choose icon
        icon_key = "info" if title.lower().startswith("disconnected") else "error"
        # include Open log when debugging
        btns = ("Open log","OK") if debug_enabled and self.last_log_text.strip() else ("OK",)
        choice = self._msgbox(title, details, icon_key=icon_key, buttons=btns, default="OK")

        if choice == "Open log":
            self.show_log(self.last_log_text)

        self.reset_ui()

    def connection_timeout(self):

        # If the cancel button is pressed, stop the thread and close the dialog
        if self.connection_thread.isRunning():
            self.connection_thread.stop()  # Signal the thread to stop
            self.connection_thread.wait()  # Wait for the thread to finish

        self.connection_dialog.reject()  # Close the dialog
        self.reset_ui()  # Reset the UI

if __name__ == "__main__":
    app = QApplication([])
    QApplication.setStyle('Fusion')
    client_window = Client()
    client_window.show()
    sys.exit(app.exec_())
