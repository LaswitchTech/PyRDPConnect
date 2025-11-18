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
