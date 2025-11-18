#!/usr/bin/env python3
# src/app/ui.py
from __future__ import annotations

from typing import Iterable, Optional, Callable, List

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QHBoxLayout, QPushButton,
    QLineEdit, QSpinBox, QComboBox, QCheckBox, QColorDialog,
    QSizePolicy, QStyle, QStyleOptionButton, QWidget, QFileDialog
)
from PyQt5.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QPen
)
from PyQt5.QtCore import QRect, Qt
from PyQt5.QtSvg import QSvgWidget, QSvgRenderer

import os
import base64

from .helper import Helper

class MsgBox(QDialog):

    ICONS = {
        "info":    "icons/info.svg",
        "error":   "icons/error.svg",
        "warning": "icons/warning.svg",
        "question":"icons/question.svg",
    }

    def __init__(
        self,
        parent=None,
        title: str = "",
        message: str = "",
        icon: Optional[str] = None,
        buttons: Iterable[str] = ("OK",),
        default: Optional[str] = None,
        icon_size: int = 64,
        icon_lookup_fn: Optional[Callable[[str], Optional[str]]] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setObjectName("MsgBox")
        self.setModal(True)

        self._selected: Optional[str] = None
        self._icon_lookup = icon_lookup_fn

        if isinstance(buttons, str):
            buttons = (buttons,)
        else:
            buttons = tuple(buttons)

        layout = QVBoxLayout(self)

        # --- Top area: icon + message ---
        top = QHBoxLayout()
        layout.addLayout(top)

        if icon:
            icon_path = self._resolve_icon_path(icon)
            if icon_path:
                svg = QSvgWidget(icon_path)
                svg.setFixedSize(icon_size, icon_size)
                svg.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
                top.addWidget(svg, alignment=Qt.AlignVCenter)

        # message text
        msg_label = QLabel(message)
        msg_label.setWordWrap(True)
        msg_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        top.addWidget(msg_label)

        # --- Buttons ---
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._buttons: dict[str, QPushButton] = {}

        for text in buttons:
            btn = QPushButton(text)
            self._buttons[text] = btn
            btn.clicked.connect(lambda _, t=text: self._on_click(t))
            btn_row.addWidget(btn)

        layout.addLayout(btn_row)

        # default selection
        if default and default in self._buttons:
            self._buttons[default].setDefault(True)
            self._buttons[default].setFocus()

    # -------------------------------------------------

    def _resolve_icon_path(self, icon: str) -> Optional[str]:
        """
        Resolve an icon name or path using ICONS + optional lookup function.
        """
        # Named icon → relative path from ICONS
        candidate = self.ICONS.get(icon, icon)

        if self._icon_lookup:
            resolved = self._icon_lookup(candidate)
            if resolved:
                return resolved

        return candidate

    def _on_click(self, text: str):
        self._selected = text
        self.accept()

    # -------------------------------------------------
    # Convenience static helper
    # -------------------------------------------------

    @staticmethod
    def show(
        parent=None,
        title: str = "",
        message: str = "",
        icon: Optional[str] = None,
        buttons: Iterable[str] = ("OK",),
        default: Optional[str] = None,
        icon_lookup_fn: Optional[Callable[[str], Optional[str]]] = None,
    ) -> str:
        """
        Show the dialog modally and return the label of the chosen button.
        """
        dlg = MsgBox(
            parent=parent,
            title=title,
            message=message,
            icon=icon,
            buttons=buttons,
            default=default,
            icon_lookup_fn=icon_lookup_fn,
        )
        dlg.exec_()
        return dlg._selected or default or ""

class ColorButton(QPushButton):
    def __init__(self, initial: str = "#265162", parent=None):
        super().__init__(parent)
        self._color = QColor(initial)
        self.clicked.connect(self._pick)

    def _pick(self):
        chosen = QColorDialog.getColor(self._color, self, "Choose Color")
        if chosen.isValid():
            self._color = chosen
            self.update()  # repaint

    def color(self) -> QColor:
        return self._color

    def hex(self) -> str:
        return self._color.name()

    def _styleOption(self):
        option = QStyleOptionButton()
        option.initFrom(self)
        option.text = self.text()
        option.icon = self.icon()
        return option

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Get content rect WITHIN QPushButton's styled padding
        content = self.style().subElementRect(
            QStyle.SE_PushButtonContents,
            self._styleOption(),
            self
        )

        pen = QPen(QColor(118, 121, 124))
        painter.setPen(pen)
        painter.setBrush(self._color)

        painter.drawRoundedRect(content, 4, 4)
        painter.end()

class PictureButton(QPushButton):
    def __init__(self, initial: Optional[str] = None, parent=None, max_size: int = 72):
        super().__init__(parent)
        self._b64: str = ""
        self._max_size = max_size

        # Visual setup
        self.setFixedSize(max_size + 16, max_size + 24)
        self.setStyleSheet("padding: 4px;")
        self.setText("Select Logo")

        # Initialize from existing config value
        if initial:
            self._init_from_value(initial)

        self.clicked.connect(self._pick)

    # ----- public API for Configuration -----

    def value(self) -> str:
        """
        Return the stored base64 string (or "" if none).
        """
        return self._b64

    # ----- internals -----

    def _init_from_value(self, raw: str):
        raw = raw.strip()
        if not raw:
            return

        # 1) Try as base64
        data: Optional[bytes] = None
        try:
            data = base64.b64decode(raw, validate=True)
        except Exception:
            data = None

        # 2) If not valid base64, treat as path
        if data is None:
            if os.path.isfile(raw):
                try:
                    with open(raw, "rb") as f:
                        data = f.read()
                except Exception as e:
                    print(f"[PictureButton] Failed to read logo file '{raw}': {e}")
                    return
            else:
                # Unknown format; give up silently
                return

        # At this point we have `data`
        pm = QPixmap()
        if not pm.loadFromData(data, "PNG"):
            return

        self._b64 = base64.b64encode(data).decode("ascii")
        self._set_pixmap(pm)

    def _pick(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Logo",
            "",
            "PNG Files (*.png)"
        )
        if not path:
            return

        try:
            with open(path, "rb") as f:
                data = f.read()

            pm = QPixmap()
            if not pm.loadFromData(data, "PNG"):
                print(f"[PictureButton] Not a valid PNG: {path}")
                return

            self._b64 = base64.b64encode(data).decode("ascii")
            self._set_pixmap(pm)
        except Exception as e:
            print(f"[PictureButton] Failed to load logo '{path}': {e}")

    def _set_pixmap(self, pm: QPixmap):
        scaled = pm.scaled(
            self._max_size,
            self._max_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.setIcon(QIcon(scaled))
        self.setIconSize(scaled.size())
        self.setText("")
        self.update()

class StepIndicator(QWidget):
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

class Form:

    @staticmethod
    def text(text: str = "", placeholder: str = "") -> QLineEdit:
        w = QLineEdit()
        if text:
            w.setText(text)
        if placeholder:
            w.setPlaceholderText(placeholder)
        return w

    @staticmethod
    def password(text: str = "", placeholder: str = "") -> QLineEdit:
        w = QLineEdit()
        w.setEchoMode(QLineEdit.Password)
        if text:
            w.setText(text)
        if placeholder:
            w.setPlaceholderText(placeholder)
        return w

    @staticmethod
    def checkbox(checked: bool = False) -> QCheckBox:
        w = QCheckBox()
        w.setChecked(checked)
        return w

    @staticmethod
    def spin(value: int = 0, minimum: int = 0, maximum: int = 65535) -> QSpinBox:
        w = QSpinBox()
        w.setRange(minimum, maximum)
        w.setValue(value)
        return w

    @staticmethod
    def number(value: int = 0, minimum: int = 0, maximum: int = 65535) -> QSpinBox:
        w = QSpinBox()
        w.setRange(minimum, maximum)
        w.setValue(value)
        return w

    @staticmethod
    def integer(value: int = 0, minimum: int = 0, maximum: int = 65535) -> QSpinBox:
        w = QSpinBox()
        w.setRange(minimum, maximum)
        w.setValue(value)
        return w

    @staticmethod
    def select(items: Iterable[str], current: Optional[str] = None) -> QComboBox:
        cb = QComboBox()
        vals: List[str] = list(items)
        cb.addItems(vals)
        if current is not None:
            idx = cb.findText(str(current))
            if idx >= 0:
                cb.setCurrentIndex(idx)
        return cb

    @staticmethod
    def color(initial: str = "#265162") -> ColorButton:
        return ColorButton(initial)

    @staticmethod
    def button(label: str, action: Callable | None, icon: str = "") -> QPushButton:
        helper = Helper()
        btn = QPushButton(label)
        if icon:
            icon_path = f"icons/{icon}.svg"
            if icon_path:
                if helper.file_exists(icon_path):
                    renderer = QSvgRenderer(icon_path)
                    pixmap = QPixmap(18, 18)
                    pixmap.fill(Qt.transparent)
                    painter = QPainter(pixmap)
                    renderer.render(painter)
                    painter.end()
                    icon = QIcon(pixmap)
                    btn.setIcon(icon)
                    btn.setIconSize(pixmap.size())
                    if label:
                        btn.setText("\u2002" + label)
        # btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        if action:
            btn.clicked.connect(action)
        return btn

    @staticmethod
    def picture(initial: Optional[str] = None) -> PictureButton:
        return PictureButton(initial=initial)
