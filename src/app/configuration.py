#!/usr/bin/env python3
# src/app/configuration.py
from __future__ import annotations

import os
import json
import shutil
import sys
from collections import defaultdict
from typing import Any, Tuple, Optional, TYPE_CHECKING

from PyQt5.QtCore import pyqtSignal, QObject
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QTabWidget, QWidget, QFormLayout,
    QLabel, QPushButton, QHBoxLayout, QApplication, QFileDialog,
    QLineEdit, QComboBox, QCheckBox, QSpinBox
)

# Allow this module to be used both as part of the 'app' package and as a standalone script
try:
    from .helper import Helper
    from .ui import Form
except ImportError:  # likely running as a top-level script
    from helper import Helper
    from ui import Form

if TYPE_CHECKING:
    # For type hints only, avoids circular import at runtime
    from app.application import Application

class Configuration(QObject):

    # Emitted after a successful save (or when we choose to later)
    configChanged = pyqtSignal(dict)

    def __init__(
        self,
        helper: Optional[Helper] = None,
        filename: str = "configuration.cfg"
    ):

        # Initialize QObject
        super().__init__()

        # Retrieve the application instance (may be None in CLI usage)
        self._app: Application | None = QApplication.instance()  # type: ignore[valid-type]

        # Ensure we have either an Application or an explicit Helper
        if self._app is None and helper is None:
            raise RuntimeError(
                "Configuration must be created after QApplication/Application or with an explicit Helper."
            )

        # --- auto-wire from QApplication if not provided ---
        if helper is None and self._app is not None:
            # narrow the type for linters / IDEs
            # no runtime import to avoid circular imports
            helper = self._app.helper          # type: ignore[attr-defined]

        # Helper
        self._helper: Helper = helper

        # Parent
        self._parent = None

        # Root directory for config files
        self.root_dir = helper.root_dir
        self._filename = filename

        # Actual config values (nested dict)
        self._data: dict[str, Any] = {}

        # Schema: key -> {"default": ..., "widget": "text"/"select"/...}
        self._schema: dict[str, dict[str, Any]] = {}

        # UI widgets mapped by config key
        self._widgets: dict[str, Any] = {}

        # Actual QLabel widgets mapped by config key (for show/hide)
        self._widget_labels: dict[str, Any] = {}

        # Labels: key → display label (e.g. "freerdp" -> "FreeRDP",
        #      "freerdp.display" -> "Display")
        self._labels: dict[str, str] = {}

        # Load existing file if any
        self.load()

        # Add built-in administration actions
        self.add("administration.import", None, "button", label="Import Configuration", action=self.import_cfg)
        self.add("administration.export", None, "button", label="Export Configuration", action=self.export_cfg)

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def load(self, file: str | None = None) -> None:
        if file is not None:
            self._filename = file

        config_dir = self._get_config_dir()
        os.makedirs(config_dir, exist_ok=True)

        path = os.path.join(config_dir, self._filename)
        if not os.path.exists(path):
            # Nothing yet, keep empty data
            self._data = {}
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._data = data
            else:
                self._data = {}
        except Exception as e:
            print(f"[Configuration] Failed loading {self._filename}: {e}")
            self._data = {}

    def save(self) -> None:
        config_dir = self._get_config_dir()
        os.makedirs(config_dir, exist_ok=True)

        path = os.path.join(config_dir, self._filename)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
            # Notify listeners
            self.configChanged.emit(self._data)
        except Exception as e:
            print(f"[Configuration] Failed saving {self._filename}: {e}")

    def add(self, key: str, default_value: Any, widget: str | None = None, **options: Any) -> None:
        self._schema[key] = {
            "default": default_value,
            "widget": widget,
            "options": options or {},
        }

        # If there's no value yet in self._data, apply the default now
        try:
            current = self.get(key, _no_fallback=True)
        except KeyError:
            # Not present at all → set default
            self.set(key, default_value)

    def get(self, key: str, default: Any | None = None, _no_fallback: bool = False) -> Any:
        parts = key.split(".")
        node: Any = self._data

        for part in parts:
            if not isinstance(node, dict) or part not in node:
                # Missing key
                if _no_fallback:
                    raise KeyError(key)
                # explicit default wins
                if default is not None:
                    return default
                # fall back to schema default if any
                meta = self._schema.get(key)
                if meta is not None:
                    return meta.get("default")
                return None
            node = node[part]

        return node

    def set(self, key: str, value: Any) -> None:
        parts = key.split(".")
        if not parts:
            return

        node = self._data
        for part in parts[:-1]:
            if part not in node or not isinstance(node[part], dict):
                node[part] = {}
            node = node[part]

        node[parts[-1]] = value

    def input(self, key: str, show_label: bool = False) -> QWidget:
        if key not in self._schema:
            raise KeyError(f"Configuration key not defined in schema: {key}")

        widget, label_text = self._build_widget_for_key(key)

        if not show_label:
            return widget

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(label_text)
        layout.addWidget(label)
        layout.addWidget(widget)
        return container

    def label(self, key: str, label: str | None = None) -> str:
        if label is not None:
            self._labels[key] = label

        if key in self._labels:
            return self._labels[key]

        # Fallback: nice label from the last segment
        return self._nice_label(key.split(".")[-1])

    def reload(self, key: str, value: Any) -> None:
        self.set(key, value)
        w = self._widgets.get(key)
        if w is None:
            return

        if isinstance(w, QLineEdit):
            w.setText(str(value) if value is not None else "")
        elif isinstance(w, QComboBox):
            idx = w.findText(str(value))
            if idx >= 0:
                w.setCurrentIndex(idx)
        elif isinstance(w, QCheckBox):
            w.setChecked(bool(value))
        elif isinstance(w, QSpinBox):
            try:
                w.setValue(int(value))
            except Exception:
                pass
        else:
            # Custom widgets (ColorButton, FileInput, PictureButton, etc.)
            # Prefer a color-specific API if available, then fall back to a generic setter.
            if hasattr(w, "setHex") and callable(getattr(w, "setHex")):
                # Color button / color-like widget
                w.setHex(value)
            elif hasattr(w, "setValue") and callable(getattr(w, "setValue")):
                w.setValue(value)

    def visibility(self, key: str, visible: bool) -> None:
        w = self._widgets.get(key)
        if w is not None:
            w.setVisible(visible)

        lbl = self._widget_labels.get(key)
        if lbl is not None:
            lbl.setVisible(visible)

    def reset(self, save: bool = False) -> None:
        # Start with a clean configuration dict
        self._data = {}

        # 1) Rebuild data from schema defaults
        for key, meta in self._schema.items():
            default = meta.get("default")
            self.set(key, default)

        # 2) Push defaults into widgets so the UI reflects the new values
        for key in self._schema.keys():
            try:
                value = self.get(key, _no_fallback=True)
            except KeyError:
                continue
            self.reload(key, value)

        # 3) Optionally persist and notify listeners
        if save:
            self.save()

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def data(self) -> dict[str, Any]:
        return self._data

    @property
    def schema(self) -> dict[str, dict[str, Any]]:
        return self._schema

    # ------------------------------------------------------------------
    # UI dialog builder
    # ------------------------------------------------------------------

    def show(self, parent=None):

        # Only use a QWidget as dialog parent, otherwise use None

        if parent is not None and isinstance(parent, QWidget):
            self._parent = parent

        dlg = QDialog(self._parent)
        dlg.setWindowTitle("Configuration")
        dlg.setObjectName("configurationWindow")

        root = QVBoxLayout(dlg)
        tabs = QTabWidget()
        root.addWidget(tabs)

        # structure[category][subcategory] = [(full_key, meta), ...]
        structure: dict[str, dict[str | None, list[Tuple[str, dict[str, Any]]]]] = defaultdict(
            lambda: defaultdict(list)
        )

        for full_key, meta in self._schema.items():
            parts = full_key.split(".")
            if len(parts) == 1:
                category = parts[0]
                subcat: str | None = None
                name = parts[0]
            elif len(parts) == 2:
                category = parts[0]
                subcat = None
                name = parts[1]
            else:
                category = parts[0]
                subcat = parts[1]
                name = ".".join(parts[2:])  # rare case of deeper nesting

            structure[category][subcat].append((full_key, meta))

        # Build tabs
        self._widgets.clear()
        self._widget_labels.clear()

        for category, subcats in structure.items():
            # Top-level tab widget
            cat_widget = QWidget()
            cat_layout = QVBoxLayout(cat_widget)

            # If there's more than one subcategory (or exactly one non-None),
            # we add a nested QTabWidget, otherwise a simple form.
            non_none_subs = [s for s in subcats.keys() if s is not None]

            if non_none_subs:
                # There are sub-tabs
                subtabs = QTabWidget()
                cat_layout.addWidget(subtabs)

                # subcat == None → put those fields in a "General" sub-tab
                if None in subcats:
                    general_tab = QWidget()
                    general_form = QFormLayout(general_tab)
                    self._populate_form(general_form, subcats[None])
                    subtabs.addTab(general_tab, "General")

                for subcat_name, fields in subcats.items():
                    if subcat_name is None:
                        continue
                    sub_widget = QWidget()
                    sub_form = QFormLayout(sub_widget)
                    self._populate_form(sub_form, fields)
                    subtabs.addTab(sub_widget, self.label(f"{category}.{subcat_name}"))
            else:
                # Only a single bucket (no sub-tabs)
                only_fields = subcats.get(None, [])
                form = QFormLayout()
                cat_layout.addLayout(form)
                self._populate_form(form, only_fields)

            tabs.addTab(cat_widget, self.label(category))

        # Buttons row (Reset / Cancel / Save)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        reset_btn = QPushButton("Reset")
        save_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        btn_row.addWidget(reset_btn)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        root.addLayout(btn_row)

        # Wire buttons
        def on_save():
            self._update_from_widgets()
            self.save()
            dlg.accept()

        def on_cancel():
            dlg.reject()

        def on_reset():
            # Reset all values back to their defaults and keep the dialog open.
            # Do not save immediately; let the user confirm with Save.
            self.reset(save=False)

        save_btn.clicked.connect(on_save)
        cancel_btn.clicked.connect(on_cancel)
        reset_btn.clicked.connect(on_reset)

        dlg.exec_()

    # ------------------------------------------------------------------
    # Import / Export
    # ------------------------------------------------------------------

    def _import_dict(self, imported: dict[str, Any]) -> bool:
        if not isinstance(imported, dict):
            print(f"[Configuration] Imported configuration is not a dict: {type(imported)}")
            return False

        collected_keys: list[str] = []

        def _apply(prefix: str, node: dict[str, Any]) -> None:
            for key, value in node.items():
                if isinstance(value, dict):
                    new_prefix = f"{prefix}.{key}" if prefix else key
                    _apply(new_prefix, value)
                else:
                    full_key = f"{prefix}.{key}" if prefix else key
                    # Use the existing setter so we don't stomp entire blocks
                    self.set(full_key, value)
                    collected_keys.append(full_key)

        _apply("", imported)

        # After applying, reload each key recursively with imported values
        for full_key in collected_keys:
            node = imported
            parts = full_key.split(".")
            for part in parts[:-1]:
                node = node.get(part, {})
            value = node.get(parts[-1], None)
            self.reload(full_key, value)

        # Persist and notify listeners via save()
        self.save()
        return True

    def import_from_path(self, path: str) -> bool:
        try:
            with open(path, "r", encoding="utf-8") as f:
                imported = json.load(f)
        except Exception as e:
            print(f"[Configuration] Failed importing configuration from {path}: {e}")
            return False

        return self._import_dict(imported)

    def import_cfg(self, parent: Optional[QWidget] = None) -> bool:
        # Allow this method to be called as a Qt slot callback (clicked(bool)), where parent might be a bool
        if not isinstance(parent, QWidget):
            parent = self._parent if isinstance(self._parent, QWidget) else None
        path, _ = QFileDialog.getOpenFileName(
            parent,
            "Import configuration",
            "",
            "Config files (*.cfg);;All files (*)",
        )
        if not path:
            return False  # User cancelled

        try:
            with open(path, "r", encoding="utf-8") as f:
                imported = json.load(f)
        except Exception as e:
            print(f"[Configuration] Failed importing configuration from {path}: {e}")
            return False

        return self._import_dict(imported)

    def export_cfg(self, parent: Optional[QWidget] = None) -> bool:
        # Allow this method to be called as a Qt slot callback (clicked(bool)), where parent might be a bool
        if not isinstance(parent, QWidget):
            parent = self._parent if isinstance(self._parent, QWidget) else None
        path, _ = QFileDialog.getSaveFileName(
            parent,
            "Export configuration",
            "configuration.cfg",
            "Config files (*.cfg);;All files (*)",
        )
        if not path:
            return False  # User cancelled

        # Ensure latest config is written to disk
        self.save()

        config_dir = self._get_config_dir()
        src = os.path.join(config_dir, self._filename)

        try:
            shutil.copy2(src, path)
            return True
        except Exception as e:
            print(f"[Configuration] Failed exporting configuration to {path}: {e}")
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_widget_for_key(self, full_key: str) -> Tuple[QWidget, str]:
        meta = self._schema.get(full_key, {})
        widget_type = meta.get("widget")
        options = meta.get("options", {}) or {}
        current_value = self.get(full_key)

        # Infer widget type if not explicitly set
        if widget_type is None:
            if isinstance(current_value, bool):
                widget_type = "checkbox"
            elif isinstance(current_value, int):
                widget_type = "spin"
            elif isinstance(current_value, str) and "choices" in options:
                widget_type = "select"
            else:
                widget_type = "text"

        # Build widget via Form helpers
        if widget_type == "checkbox":
            w = Form.checkbox(checked=bool(current_value))
        elif widget_type in ("spin", "integer", "number"):
            w = Form.spin(
                value=int(current_value) if current_value is not None else 0,
                minimum=options.get("min", 0),
                maximum=options.get("max", 65535),
            )
        elif widget_type == "select":
            w = Form.select(
                items=options.get("choices", []),
                current=current_value,
            )
        elif widget_type == "password":
            w = Form.password(
                text=current_value or "",
                placeholder=options.get("placeholder", "")
            )
        elif widget_type == "color":
            w = Form.color(initial=current_value or "#000000")
        elif widget_type == "picture":
            w = Form.picture(initial=current_value or "")
        elif widget_type == "file":
            w = Form.file(
                initial=current_value or "",
                caption=options.get("caption", "Select File"),
                directory=options.get("directory", ""),
                filter=options.get("filter", "All Files (*)"),
                as_base64=options.get("as_base64", False),
                on_changed=options.get("on_changed", None),
            )
        elif widget_type == "button":
            w = Form.button(
                label=options.get("label", "Button"),
                icon=options.get("icon", None),
                action=options.get("action", None)
            )
        else:
            # default: text line
            w = Form.text(
                text=current_value or "",
                placeholder=options.get("placeholder", "")
            )

        # --- generic on_changed wiring for basic widgets ---
        callback = options.get("on_changed")
        if callback is not None:
            from PyQt5.QtWidgets import QLineEdit, QComboBox, QCheckBox, QSpinBox

            try:
                if isinstance(w, QCheckBox):
                    w.toggled.connect(callback)
                elif isinstance(w, QLineEdit):
                    w.textChanged.connect(callback)
                elif isinstance(w, QSpinBox):
                    w.valueChanged.connect(callback)
                elif isinstance(w, QComboBox):
                    w.currentTextChanged.connect(callback)

                # Initial call so state (e.g. visibility) is correct
                callback(current_value)
            except Exception as e:
                print(f"[Configuration] on_changed for {full_key} failed: {e}")

        # Register this widget for saving (used by _update_from_widgets)
        self._widgets[full_key] = w

        label_text = options.get(
            "label",
            self.label(full_key)
        )
        return w, label_text

    def _populate_form(
        self,
        form_layout,
        fields: list[Tuple[str, dict[str, Any]]]
    ) -> None:
        for full_key, _meta in fields:
            w, label_text = self._build_widget_for_key(full_key)
            label_widget = QLabel(label_text)
            form_layout.addRow(label_widget, w)

            # Keep track of the label widget so we can hide/show it
            self._widget_labels[full_key] = label_widget

    def _nice_label(self, raw: str) -> str:
        s = raw.replace("_", " ").replace("-", " ")
        if not s:
            return ""
        return s[0].upper() + s[1:]

    def _update_from_widgets(self) -> None:
        for key, widget in self._widgets.items():
            value: Any

            if isinstance(widget, QLineEdit):
                value = widget.text()
            elif isinstance(widget, QComboBox):
                value = widget.currentText()
            elif isinstance(widget, QCheckBox):
                value = widget.isChecked()
            elif isinstance(widget, QSpinBox):
                value = widget.value()
            else:
                if hasattr(widget, "hex") and callable(getattr(widget, "hex")):
                    value = widget.hex()
                elif hasattr(widget, "value") and callable(getattr(widget, "value")):
                    value = widget.value()
                else:
                    continue

            self.set(key, value)

    def _get_config_dir(self) -> str:
        # Legacy default (macOS, Windows, etc.)
        default_dir = os.path.join(self.root_dir, "config")

        # Try to get OS name from helper to stay consistent with Application
        try:
            os_name = self._helper.get_os()
        except Exception:
            os_name = None

        # Only change behavior on Linux and when we have an application name
        if os_name == "linux":
            app_name = ""

            # If we have an Application instance, try to use its name
            if self._app is not None:
                try:
                    # Prefer the Application.name property if available
                    if hasattr(self._app, "name"):
                        app_name = self._app.name  # type: ignore[attr-defined]
                    else:
                        app_name = self._app.applicationName()
                except Exception:
                    app_name = ""

            # In CLI usage there may be no Application; fall back to the root_dir name
            if not app_name:
                try:
                    app_name = os.path.basename(self.root_dir) or ""
                except Exception:
                    app_name = ""

            if app_name:
                home = os.path.expanduser("~")
                if home:
                    return os.path.join(home, ".config", app_name)

        return default_dir

# ------------------------------------------------------------------
# CLI entrypoint
# ------------------------------------------------------------------

def _cli_main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    import argparse

    parser = argparse.ArgumentParser(description="Configuration helper")
    parser.add_argument(
        "--import",
        dest="import_path",
        metavar="PATH",
        help="Import configuration from the given file and save it to the default configuration location.",
    )
    args = parser.parse_args(argv)

    if not args.import_path:
        parser.print_help()
        return 0

    # Instantiate a helper and configuration without requiring a full Application
    helper = Helper()
    cfg = Configuration(helper=helper)

    if not os.path.exists(args.import_path):
        print(f"[Configuration] Config file not found: {args.import_path}", file=sys.stderr)
        return 1

    ok = cfg.import_from_path(args.import_path)
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(_cli_main())
