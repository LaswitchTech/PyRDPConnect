#!/usr/bin/env python3
# src/app/log.py
import threading
from collections import defaultdict
from typing import Iterable, Optional, TYPE_CHECKING

from PyQt5.QtCore import Qt, QRegExp
from PyQt5.QtGui import QTextCharFormat, QColor
from PyQt5.QtWidgets import (
    QDialog, QTextEdit, QLineEdit, QPushButton, QHBoxLayout,
    QVBoxLayout, QFileDialog, QWidget, QComboBox, QApplication
)

from .helper import Helper
from .ui import MsgBox

if TYPE_CHECKING:
    # For type hints only, avoids circular import at runtime
    from app.application import Application
    from app.configuration import Configuration

class Log:

    def __init__(self, helper: Helper | None = None):

        # Retrieve the application instance (may be None in CLI usage)
        self._app: Application | None = QApplication.instance()  # type: ignore[valid-type]

        # Ensure we have either an Application or an explicit Helper
        if self._app is None and helper is None:
            raise RuntimeError(
                "Configuration must be created after QApplication/Application or with an explicit Helper."
            )

        # --- auto-wire from QApplication if not provided ---
        if helper is None and self._app is not None:
            helper = self._app.helper          # type: ignore[attr-defined]

        # Helper
        self._helper: Helper = helper

        # Configuration
        self._configuration: Configuration = self._app.configuration
        self._configuration.add("log.level", "info", "select", choices=["debug", "info", "warning", "error", "none"])
        self._configuration.add("log.enabled", True, "checkbox")
        self._configuration.add("log.open", None, "button", label="Open Log", action=self.show)
        self._configuration.add("log.clear", False, "checkbox", label="Allow clearing log")
        self._configuration.add("log.verbose", False, "checkbox", label="Verbose logging")

        # Save any new defaults
        self._configuration.save()

        # Parent
        self._parent = None

        # Channel
        self._channel = None

        # Core storage
        self._lock = threading.Lock()
        self._buffers: dict[str, list[str]] = defaultdict(list)

    # ---------- core storage ----------

    def append(self, message: str, channel: str = "default", level: str = "info") -> None:

        # Check if logging is enabled and level is sufficient
        if not self._configuration.get("log.enabled"):
            return
        if self._configuration.get("log.level") == "none":
            return
        if self._configuration.get("log.level") == "error" and level != "error":
            return
        if self._configuration.get("log.level") == "warning" and level not in ("warning", "error"):
            return
        if self._configuration.get("log.level") == "info" and level not in ("info", "warning", "error"):
            return
        if self._configuration.get("log.level") == "debug" and level not in ("debug", "info", "warning", "error"):
            return
        if not message:
            return

        # Normalize to individual lines
        lines = message.splitlines() or [message]

        # Check if verbose logging is enabled and print to console
        if self._configuration.get("log.verbose"):
            for ln in lines:
                print(f"[{channel}] {ln}")

        # Append lines to the buffer
        with self._lock:
            self._buffers[channel].extend(lines)

    def extend(self, lines: Iterable[str], channel: str = "default") -> None:
        with self._lock:
            for ln in lines:
                if ln:
                    self._buffers[channel].append(str(ln))

    def get_text(self, channel: Optional[str] = None) -> str:
        with self._lock:
            # All channels
            if channel is None:
                if not self._buffers:
                    return ""
                # Just concatenate all logs in insertion order of channels
                parts: list[str] = []
                for ch, lines in self._buffers.items():
                    if not lines:
                        continue
                    # Optional header per channel (helps when viewing “All”)
                    parts.append(f"[{ch}]")
                    parts.extend(lines)
                    parts.append("")  # blank line between channels
                return "\n".join(parts).rstrip()
            # Single channel
            if channel not in self._buffers:
                return ""
            return "\n".join(self._buffers[channel])

    def clear(self, channel: Optional[str] = None) -> None:

        # Check if clearing is allowed
        if not self._configuration.get("log.clear"):
            return

        # Clear all channels if channel is None
        with self._lock:
            if channel is None:
                self._buffers.clear()
            else:
                self._buffers.pop(channel, None)

    def has_data(self, channel: str = "default") -> bool:
        with self._lock:
            return bool(self._buffers.get(channel))

    def has_any_data(self) -> bool:
        with self._lock:
            return any(bool(buf) for buf in self._buffers.values())

    # ---------- UI helper ----------

    def show(self, parent=None, channel: Optional[str] = None, filter_text: str | None = None):
        # If called from a clicked(bool) signal, parent may be a bool; ignore non-widget parents
        if not isinstance(parent, QWidget):
            parent = None

        if parent is not None and isinstance(parent, QWidget):
            self._parent = parent
        elif self._parent is None:
            # Try to parent to the currently active window (e.g. the configuration dialog)
            aw = QApplication.activeWindow()
            if isinstance(aw, QWidget):
                self._parent = aw

        # Remember last requested channel (can be None = all)
        self._channel = channel

        if channel is None:
            # All channels
            if not self.has_any_data():
                MsgBox.show(
                    title="No log available",
                    message="There is no log yet. Perform some actions first.",
                    icon="info",
                    buttons="OK",
                    default="OK",
                    icon_lookup_fn=self._helper.get_path,
                )
                return

            # Snapshot buffers for the dialog
            with self._lock:
                channels_text = {
                    ch: "\n".join(lines) for ch, lines in self._buffers.items()
                }
            text = self.get_text(None)  # all channels, formatted
        else:
            # Single channel
            if not self.has_data(channel):
                MsgBox.show(
                    title="No log available",
                    message="There is no log yet for this channel. Perform some actions first.",
                    icon="info",
                    buttons="OK",
                    default="OK",
                    icon_lookup_fn=self._helper.get_path,
                )
                return

            with self._lock:
                channels_text = {
                    ch: "\n".join(lines) for ch, lines in self._buffers.items()
                }
            text = self.get_text(channel)

        dlg = LogDialog(
            self._parent,
            text=text,
            filter_text=filter_text,
            channels_text=channels_text,
            initial_channel=channel,
        )
        # Run the log window as a modal dialog so it appears on top and is interactive
        dlg.exec_()
        return dlg

class LogDialog(QDialog):

    def __init__(
        self,
        parent=None,
        text: str = "",
        filter_text: str | None = None,
        channels_text: Optional[dict[str, str]] = None,
        initial_channel: Optional[str] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Log")
        self.setObjectName("logWindow")
        self.setMinimumSize(720, 420)

        # Store per-channel logs (may be empty dict)
        self._channels_text: dict[str, str] = channels_text or {}
        self._current_channel: Optional[str] = initial_channel

        self._full_text = text or ""

        self.text = QTextEdit(self)
        self.text.setReadOnly(True)
        self.text.setPlainText(self._full_text)

        # Channel selector
        self.channel_box = QComboBox(self)
        self.channel_box.addItem("All channels", userData=None)
        for ch in sorted(self._channels_text.keys()):
            self.channel_box.addItem(ch, userData=ch)

        # Set initial selection
        if initial_channel is None:
            self.channel_box.setCurrentIndex(0)
        else:
            idx = self.channel_box.findData(initial_channel)
            if idx >= 0:
                self.channel_box.setCurrentIndex(idx)

        self.channel_box.currentIndexChanged.connect(self._on_channel_change)

        self.find_box = QLineEdit(self)
        self.find_box.setPlaceholderText("Filter...")
        self.find_box.textChanged.connect(self.apply_filter)

        self.copy_btn = QPushButton("Copy all")
        self.copy_btn.clicked.connect(
            lambda: self._copy_all()
        )
        self.save_btn = QPushButton("Save as...")
        self.save_btn.clicked.connect(self.save_as)

        top = QHBoxLayout()
        top.addWidget(self.channel_box)   # ⬅️ add channel selector to the toolbar row
        top.addWidget(self.find_box)
        top.addWidget(self.copy_btn)
        top.addWidget(self.save_btn)

        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(self.text)

        # If opened with an initial filter, apply it right away
        if filter_text:
            self.find_box.setText(filter_text)
        else:
            self.apply_filter()

    # ------ basic operations ------

    def set_text(self, text: str):
        self._full_text = text or ""
        self.apply_filter()

    def _copy_all(self):
        from PyQt5.QtWidgets import QApplication
        QApplication.clipboard().setText(self.text.toPlainText())

    def save_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save log", "log.txt",
            "Log Files (*.log);;Text Files (*.txt);;All Files (*)"
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.text.toPlainText())

    # ------ filtering + highlighting ------

    def apply_filter(self):

        needle = self.find_box.text().strip()
        if not needle:
            self._set_view_text(self._full_text)
            return

        filtered_lines = [
            ln for ln in self._full_text.splitlines()
            if needle.lower() in ln.lower()
        ]
        self._set_view_text("\n".join(filtered_lines))
        self._highlight_all(needle)

    def _set_view_text(self, s: str):
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

        fmt = QTextCharFormat()
        fmt.setBackground(QColor("yellow"))
        fmt.setForeground(QColor("black"))

        rx = QRegExp(needle)
        rx.setCaseSensitivity(Qt.CaseInsensitive)

        pos = 0
        plain = doc.toPlainText()
        while True:
            pos = rx.indexIn(plain, pos)
            if pos < 0:
                break
            match_cursor = self.text.textCursor()
            match_cursor.setPosition(pos)
            match_cursor.setPosition(pos + rx.matchedLength(), match_cursor.KeepAnchor)
            match_cursor.mergeCharFormat(fmt)
            pos += max(1, rx.matchedLength())

        cursor.endEditBlock()

    # ----- event handlers ------

    def _on_channel_change(self, idx: int):
        ch = self.channel_box.itemData(idx)  # None = All channels
        self._current_channel = ch

        if ch is None:
            # All channels: rebuild from the per-channel dict if available,
            # otherwise fall back to whatever initial text we had.
            if self._channels_text:
                parts: list[str] = []
                for name in sorted(self._channels_text.keys()):
                    txt = (self._channels_text.get(name) or "").strip()
                    if not txt:
                        continue
                    parts.append(f"[{name}]")
                    parts.append(txt)
                    parts.append("")
                self._full_text = "\n".join(parts).rstrip()
            else:
                self._full_text = self._full_text or ""
        else:
            self._full_text = self._channels_text.get(ch, "")

        self.apply_filter()
