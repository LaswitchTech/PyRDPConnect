#!/usr/bin/env python3
from PyQt5.QtWidgets import (
    QApplication, QMessageBox, QDialog, QMainWindow,
    QWidget, QCheckBox, QFileDialog,
    QHBoxLayout, QPushButton, QLabel, QLineEdit, QFormLayout
)
from PyQt5.QtGui import (
    QIcon, QPixmap, QPainter
)
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtCore import Qt, QSize
import subprocess
import base64
import json
import sys
import os

class Client(QMainWindow):

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

    def update_application(self):
        try:
            subprocess.run(['git', 'pull'], check=True, cwd=self.root_dir)
            self._msgbox("Update", "Application updated successfully. Restarting...", icon_key="success")
            QApplication.quit()
            subprocess.run([sys.executable] + sys.argv)
        except subprocess.CalledProcessError as e:
            self._msgbox("Error", f"Failed to update the application: {e}", icon_key="error")

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
