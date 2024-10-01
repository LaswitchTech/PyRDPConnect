#!/usr/bin/env python3
from PyQt5.QtWidgets import (
    QApplication, QProgressDialog, QMessageBox, QDialog, QMainWindow,
    QDesktopWidget, QWidget, QTabWidget, QCheckBox, QFrame, QSizePolicy,
    QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QLineEdit, QFormLayout,
    QGroupBox, QGridLayout, QComboBox, QSpinBox, QFileDialog
)
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QPalette, QColor
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtCore import Qt, QThread, pyqtSignal
import subprocess
import platform
import shutil
import base64
import json
import sys
import os
import re

class ConnectionThread(QThread):
    connection_success = pyqtSignal()
    connection_failed = pyqtSignal(str)
    stop_thread = False  # Flag to stop the thread

    def __init__(self, command, parent=None):
        super().__init__(parent)
        self.command = command

    def run(self):
        try:
            # Start the freerdp3 connection as a subprocess
            self.freerdp_process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Capture output and errors
            stdout, stderr = self.freerdp_process.communicate()

            # Check if the thread is supposed to stop
            if self.stop_thread:
                self.freerdp_process.terminate()  # Terminate the subprocess
                return

            # Check for errors in stderr
            if self.freerdp_process.returncode != 0:
                error_message = stderr.strip()
                self.connection_failed.emit(error_message)
            else:
                self.connection_success.emit()

        except Exception as e:
            # Emit failed signal with error message if any exception occurs
            self.connection_failed.emit(str(e))

    def stop(self):
        # Method to stop the thread
        self.stop_thread = True
        if self.freerdp_process:
            self.freerdp_process.terminate()  # Terminate the subprocess if running

class Client(QMainWindow):

    def __init__(self):
        super().__init__()

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
        Returns the full path to a file if it exists in either the 'src' or 'Resources' directory.
        Prints a debug message if the file is not found.

        :param path: Relative path to the file
        :return: Full path to the file if found, None otherwise
        """
        # Check the 'src' directory
        src_path = os.path.join(self.root_dir, 'src', path)
        if os.path.exists(src_path):
            return src_path

        # Check the 'Resources' directory
        resources_path = os.path.join(self.root_dir, 'Resources', path)
        if os.path.exists(resources_path):
            return resources_path

        # Debugging message if file is not found
        print(f"Could not find: [{self.root_dir}] {path}")
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
            "Display": {
                "Resolution": "",
                "Use all monitors": False,
                "Start session in fullscreen": False,
                "Fit session to window": False
            },
            "Devices": {
                "Play sound": ""
            },
            "Redirect": {
                "Printers": False,
                "Clipboard": False,
                "Smart Cards": False,
                "Ports": False,
                "Drives": False
            },
            "Folders": {
                "Redirect": False,
                "Folders": []
            },
            "Administration": {
                "Password": ""
            },
            "Appearance": {
                "Login Position": "center-center",
                "Logo Position": "top-center",
                "Logo File": "",
                "Hide Exit": False,
                "Hide Restart": False,
                "Hide Shutdown": False,
                "Fullscreen": False
            }
        }

        # Load config from file
        config_dir = os.path.join(self.root_dir, 'config')

        for category in self.config.keys():
            config_path = os.path.join(config_dir, f'{category.lower()}.cfg')
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    category_config = json.load(f)

                    # Loop through each config item and set the config value
                    for name, value in category_config.items():

                        # Check if the config item exists in the config
                        if name in self.config[category]:
                            if isinstance(self.config[category][name], list) and value is None:
                                # Make sure lists like Folders are not set to None
                                self.config[category][name] = []
                            else:
                                self.config[category][name] = value

        # Check if the custom logo exists in the 'config/' directory
        logo_path = os.path.join(self.root_dir, 'config', 'logo.png')
        if os.path.exists(logo_path):
            self.config["Appearance"]["Logo File"] = logo_path
        else:
            # Fallback to default logo in 'src/img/logo.png'
            self.config["Appearance"]["Logo File"] = self.get_path(os.path.join('img', 'logo.png'))

    def load_widgets(self):

        """
        Load all the widgets including logo selection and preview.
        """

        # Initialize QLineEdit for password with echo mode set to Password
        passwordLineEdit = QLineEdit()
        passwordLineEdit.setEchoMode(QLineEdit.Password)

        # Initialize QLineEdit for lock password with echo mode set to Password
        lockLineEdit = QLineEdit()
        lockLineEdit.setEchoMode(QLineEdit.Password)

        # Initialize QSpinBox for port with default value and range
        portSpinBox = QSpinBox()
        portSpinBox.setRange(1, 65535)
        portSpinBox.setValue(self.config["General"]["Port"])

        # Get current screen resolution
        screenResolution = QApplication.desktop().screenGeometry()
        currentResolution = f"{screenResolution.width()}x{screenResolution.height()}"
        self.config["Display"]["Resolution"] = currentResolution

        # Initialize resolution combo box with common resolutions
        resolutionComboBox = QComboBox()
        commonResolutions = ["800x600", "1024x768", "1280x720", "1366x768", "1920x1080", "3840x2160"]
        if currentResolution not in commonResolutions:
            commonResolutions.insert(0, currentResolution)
        resolutionComboBox.addItems(commonResolutions)
        resolutionComboBox.setCurrentText(currentResolution)

        # Initialize sound options combo box
        playSoundComboBox = QComboBox()
        playSoundOptions = ["Never", "On this computer", "On the remote computer"]
        playSoundComboBox.addItems(playSoundOptions)
        playSoundComboBox.setCurrentText(self.config["Devices"]["Play sound"])

        # Initialize login and logo positions
        positionsOptions = ["top-left", "top-center", "top-right", "center-left", "center-center", "center-right", "bottom-left", "bottom-center", "bottom-right"]
        loginPositionComboBox = QComboBox()
        loginPositionComboBox.addItems(positionsOptions)
        loginPositionComboBox.setCurrentText(self.config["Appearance"]["Login Position"])

        logoPositionComboBox = QComboBox()
        logoPositionComboBox.addItems(positionsOptions)
        logoPositionComboBox.setCurrentText(self.config["Appearance"]["Logo Position"])

        # Replace logo file text field with a button for file selection and preview
        logo_file = self.config["Appearance"]["Logo File"] or self.get_path(os.path.join('img', 'logo.png'))
        self.gen_logo_button(logo_file)

        # Initialize folder redirection
        self.folder_add_button = QPushButton("Add Folder")
        self.folder_add_button.clicked.connect(self.select_folder)
        self.folder_list_layout = QVBoxLayout()

        # Initialize widgets dictionary
        self.widgets = {
            "General": {
                "Server Address": QLineEdit(),
                "Port": portSpinBox,
                "Username": QLineEdit(),
                "Password": passwordLineEdit,
                "Domain": QLineEdit()
            },
            "Display": {
                "Resolution": resolutionComboBox,
                "Use all monitors": QCheckBox(),
                "Start session in fullscreen": QCheckBox(),
                "Fit session to window": QCheckBox()
            },
            "Devices": {
                "Play sound": playSoundComboBox
            },
            "Redirect": {
                "Printers": QCheckBox(),
                "Clipboard": QCheckBox(),
                "Smart Cards": QCheckBox(),
                "Ports": QCheckBox(),
                "Drives": QCheckBox()
            },
            "Folders": {
                "Redirect": QCheckBox(),
                "Folders": [],
            },
            "Administration": {
                "Password": lockLineEdit,
            },
            "Appearance": {
                "Login Position": loginPositionComboBox,
                "Logo Position": logoPositionComboBox,
                "Logo File": self.logo_file_button,
                "Hide Exit": QCheckBox(),
                "Hide Restart": QCheckBox(),
                "Hide Shutdown": QCheckBox(),
                "Fullscreen": QCheckBox()
            }
        }

        # Load configuration files and set widget values
        config_dir = os.path.join(self.root_dir, 'config')
        for category in self.widgets.keys():
            config_path = os.path.join(config_dir, f'{category.lower()}.cfg')
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    category_config = json.load(f)
                    for name, value in category_config.items():
                        widget = self.get_widget_from_config(category, name)
                        if widget:
                            self.set_widget_value(widget, value)

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
        self.setWindowIcon(QIcon(self.icon_path))

        # Load Style Sheets
        with open(self.get_path(os.path.join('styles/style.css')), 'r') as f:
            self.setStyleSheet(f.read())

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
        logo_file = self.config['Appearance']['Logo File']
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

    def set_svg_icon(self, button, svg_path, size=(18, 18)):
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
        # Confirm with the user
        reply = QMessageBox.question(self, 'System Restart',
                                     'Are you sure you want to restart the system?',
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            try:
                if sys.platform == "win32":
                    subprocess.run(["shutdown", "/r", "/t", "0"], check=True)
                else:
                    subprocess.run(["sudo", "shutdown", "-r", "now"], check=True)
            except subprocess.CalledProcessError as e:
                QMessageBox.critical(self, "Error", f"Failed to restart the system: {e}")

    def shutdown_system(self):
        # Confirm with the user
        reply = QMessageBox.question(self, 'System Shutdown',
                                     'Are you sure you want to shutdown the system?',
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            try:
                if sys.platform == "win32":
                    subprocess.run(["shutdown", "/s", "/t", "0"], check=True)
                else:
                    subprocess.run(["sudo", "shutdown", "-h", "now"], check=True)
            except subprocess.CalledProcessError as e:
                QMessageBox.critical(self, "Error", f"Failed to shutdown the system: {e}")

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
            self.config["Folders"]["Folders"].append(folder_data)
            self.add_folder_to_list(folder_data)

            # Call on_configuration_changed to highlight the Save button
            self.on_configuration_changed()

    def add_folder_to_list(self, folder_data):
        folder_widget = QWidget()
        folder_layout = QHBoxLayout(folder_widget)

        # Add the folder path label
        folder_label = QLabel(folder_data["path"])
        folder_layout.addWidget(folder_label)

        # Add the enable/disable checkbox
        folder_checkbox = QCheckBox("Enabled")
        folder_checkbox.setChecked(folder_data["enabled"])
        folder_layout.addWidget(folder_checkbox)

        # Connect the checkbox to update folder_data["enabled"]
        folder_checkbox.stateChanged.connect(lambda state, fd=folder_data: self.update_folder_enabled(fd, state))

        # Add a delete button
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(lambda: self.remove_folder(folder_widget, folder_data))
        folder_layout.addWidget(delete_button)

        # Add the folder widget to the list layout
        self.folder_list_layout.addWidget(folder_widget)

        # Call on_configuration_changed to highlight the Save button
        self.on_configuration_changed()

    def update_folder_enabled(self, folder_data, state):
        folder_data["enabled"] = bool(state)
        # Call on_configuration_changed to highlight the Save button
        self.on_configuration_changed()

    def remove_folder(self, folder_widget, folder_data):

        # Remove the folder from the list
        self.folder_list_layout.removeWidget(folder_widget)
        folder_widget.deleteLater()
        self.config["Folders"]["Folders"].remove(folder_data)

        # Call on_configuration_changed to highlight the Save button
        self.on_configuration_changed()

    def find_widget_index(layout, widget):
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
        Update the logo file button with the current logo path and a small 72px preview.
        """

        if os.path.isfile(logo_file):
            pixmap = QPixmap(logo_file)
            if not pixmap.isNull():  # Check if the pixmap is valid
                scaled_pixmap = pixmap.scaled(72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.logo_file_button.setIcon(QIcon(scaled_pixmap))
                self.logo_file_button.setIconSize(scaled_pixmap.size())
                self.logo_file_button.setText("")  # Clear text, only show image
            else:
                print(f"Failed to load logo: {logo_file}")
                self.logo_file_button.setText("Invalid Logo File")
        else:
            print(f"File not found: {logo_file}")
            self.logo_file_button.setText("Select Logo File")  # Fallback if no valid file

        # Force repaint
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
            QMessageBox.information(self, "Update", "Application updated successfully. Restarting...")
            QApplication.quit()
            subprocess.run([sys.executable] + sys.argv)
        except subprocess.CalledProcessError as e:
            QMessageBox.critical(self, "Error", f"Failed to update the application: {e}")

    def launch_configurations(self):

        # Create a password prompt
        self.configurations_dialog = QDialog(self)
        self.configurations_dialog.setWindowModality(Qt.WindowModal)
        self.configurations_dialog.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.CustomizeWindowHint | Qt.WindowCloseButtonHint)
        self.configurations_dialog.setObjectName("configurationsWindow")

        # Set the layout to the configurations dialog
        self.configurations_layout = QVBoxLayout(self.configurations_dialog)
        self.configurations_layout.setSpacing(0)  # Set spacing to 0 to remove space between rows

        # Create a tab widget
        self.configurations_tab_widget = QTabWidget()
        self.configurations_layout.addWidget(self.configurations_tab_widget)

        # Create tabs for each category
        for category, settings in self.widgets.items():
            tab = QWidget()
            layout = QFormLayout()
            tab.setLayout(layout)

            for name, widget in settings.items():
                if category == "Appearance" and name == "Logo File":
                    self.logo_layout = layout
                    self.logo_row = layout.addRow(QLabel(name), widget)
                elif isinstance(widget, dict):
                    # For nested settings like in "Redirect" under "Devices"
                    for sub_name, sub_widget in widget.items():
                        layout.addRow(QLabel(f"{sub_name}"), sub_widget)
                elif isinstance(widget, list):
                    # Handle lists for folder redirection
                    if name == "Folders":
                        layout.addRow(QLabel(name), self.folder_add_button)  # Folder selection button
                        for folder in self.config["Folders"]["Folders"]:
                            self.add_folder_to_list(folder)
                        layout.addRow(self.folder_list_layout)
                else:
                    layout.addRow(QLabel(name), widget)

                # Connect signals for widget changes
                if isinstance(widget, QLineEdit):
                    widget.textChanged.connect(self.on_configuration_changed)
                elif isinstance(widget, QCheckBox):
                    widget.stateChanged.connect(self.on_configuration_changed)
                elif isinstance(widget, QComboBox):
                    widget.currentTextChanged.connect(self.on_configuration_changed)
                elif isinstance(widget, QSpinBox):
                    widget.valueChanged.connect(self.on_configuration_changed)

            self.configurations_tab_widget.addTab(tab, category)

            # Add additionnal controls in the Administration tab
            if category == "Administration":

                # Add "Update" button in the Administration tab
                self.update_button = QPushButton("Update")
                self.update_button.clicked.connect(self.update_application)
                layout.addRow(QLabel("Update"), self.update_button)

                # Add "Import" button in the Administration tab
                self.import_button = QPushButton("Import")
                self.import_button.clicked.connect(self.import_settings)
                layout.addRow(QLabel("Import"), self.import_button)

                # Add "Export" button in the Administration tab
                self.export_button = QPushButton("Export")
                self.export_button.clicked.connect(self.export_settings)
                layout.addRow(QLabel("Export"), self.export_button)

        # Save Button
        self.save_button = QPushButton("Save")
        self.save_button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.configurations_layout.addWidget(self.save_button)
        self.save_button.clicked.connect(self.save_config)

        # Initialize palettes for save button
        self.originalPalette = self.save_button.palette()
        self.highlightedPalette = QPalette(self.originalPalette)
        self.highlightedPalette.setColor(QPalette.Button, QColor("#198754"))

        # show the dialog
        self.configurations_dialog.show()

    def on_configuration_changed(self):

        # Change background color of the save button to highlight
        self.save_button.setObjectName("unsavedChanges")  # Change object name to apply new style
        self.save_button.style().unpolish(self.save_button)  # Unpolish to clear the existing styling
        self.save_button.style().polish(self.save_button)  # Re-apply the stylesheet
        self.save_button.update()  # Update the button's appearance

    def save_config(self):

        """
        Save the current configuration, including the logo file path.
        """

        # Ensure the configuration directory exists
        config_dir = os.path.join(self.root_dir, 'config')
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)

        # Iterate over the widgets to save settings
        for category, settings in self.widgets.items():
            category_config = {}
            for name, value in settings.items():
                if name == "Folders":
                    # Save the folders list from self.config
                    category_config[name] = self.config["Folders"]["Folders"]
                elif isinstance(value, dict):
                    # For nested settings like in "Redirect" under "Devices"
                    category_config[name] = {sub_name: self.get_widget_value(sub_widget) for sub_name, sub_widget in value.items()}
                else:
                    category_config[name] = self.get_widget_value(value)

            # Ensure the default logo is saved if no file is selected
            if category == "Appearance" and "Logo File" in category_config:
                if hasattr(self, 'selected_logo_file'):
                    if os.path.isfile(self.selected_logo_file):
                        shutil.copyfile(self.selected_logo_file, os.path.join(config_dir, 'logo.png'))
                        category_config["Logo File"] = os.path.join(config_dir, 'logo.png')

            config_path = os.path.join(config_dir, f'{category.lower()}.cfg')
            with open(config_path, 'w') as f:
                json.dump(category_config, f)

        # Reset background color of the save button to default
        self.save_button.setObjectName("saveButton")  # Change object name back to default
        self.save_button.style().unpolish(self.save_button)  # Unpolish to clear the unsaved styling
        self.save_button.style().polish(self.save_button)  # Re-apply the stylesheet
        self.save_button.update()  # Update the button's appearance

        # Reset the UI
        self.reset_ui()

        # hide the dialog
        self.configurations_dialog.hide()

    def import_settings(self):
        try:

            # Ensure the configuration directory exists
            config_dir = os.path.join(self.root_dir, 'config')
            if not os.path.exists(config_dir):
                os.makedirs(config_dir)

            # Open a file dialog to select the import file
            file_dialog = QFileDialog(self)
            file_dialog.setAcceptMode(QFileDialog.AcceptOpen)
            file_dialog.setNameFilter("JSON Files (*.json)")

            if file_dialog.exec_():
                import_file = file_dialog.selectedFiles()[0]

                # Load the imported JSON file
                with open(import_file, "r") as f:
                    imported_data = json.load(f)

                # Update the current config with the imported data
                for category, settings in imported_data.items():
                    if category in self.config:
                        self.config[category].update(settings)

                # Handle the imported logo if it exists (base64 encoded)
                logo_data = self.config["Appearance"].get("Logo File", None)
                if isinstance(logo_data, dict) and "content" in logo_data and "filename" in logo_data:
                    logo_content = base64.b64decode(logo_data["content"])
                    logo_filename = logo_data["filename"]
                    logo_path = os.path.join(self.root_dir, "config", logo_filename)
                    print("PATH:",logo_path)

                    # Save the decoded logo to the config directory
                    with open(logo_path, "wb") as logo_file:
                        logo_file.write(logo_content)

                    # Update the path to the new logo file
                    self.config["Appearance"]["Logo File"] = logo_path

                # Save the imported settings
                self.save_config()

                # Update the UI to reflect the imported settings
                self.reset_ui()

                QMessageBox.information(self, "Import Complete", "Settings successfully imported.")

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
            result = subprocess.run([freerdp_path, '+version'], capture_output=True, text=True)
            version_line = result.stdout.splitlines()[0].strip()  # Get the first line of the output
            version_parts = version_line.split()  # Split the line into words
            if len(version_parts) > 4:  # Check if the version string is present
                return version_parts[4]  # The version is the fifth element in the split output
            elif len(version_parts) > 3:  # Check if the version string is present
                return version_parts[3]  # The version is the fourth element in the split output
            else:
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

    def gen_command(self):

        # Get the path to the bundled xfreerdp
        if self.get_os() == "macos":
            freerdp_path = self.get_path('freerdp/'+self.get_os()+'/xfreerdp')
        else:
            freerdp_path = "xfreerdp"

        # Get FreeRDP version
        freerdp_version = self.get_freerdp_version(freerdp_path)

        # Determine major version number (e.g., 2.x or 3.x)
        major_version = int(freerdp_version.split('.')[0]) if freerdp_version else None

        # Construct the command using the bundled xfreerdp
        command = [freerdp_path]

        # Gather the configuration values, retrieving from widgets if necessary
        server_address = self.config["General"]["Server Address"] or self.server_edit.text()
        port = self.config["General"]["Port"] or self.port_edit.value()
        username = self.config["General"]["Username"] or self.username_edit.text()
        password = self.config["General"]["Password"] or self.password_edit.text()
        domain = self.config["General"]["Domain"] or self.domain_edit.text()
        resolution = self.config["Display"]["Resolution"]
        use_all_monitors = self.config["Display"]["Use all monitors"]
        fullscreen = self.config["Display"]["Start session in fullscreen"]
        fit_window = self.config["Display"]["Fit session to window"]
        play_sound = self.config["Devices"]["Play sound"]
        redirect_printers = self.config["Redirect"]["Printers"]
        redirect_clipboard = self.config["Redirect"]["Clipboard"]
        redirect_smart_cards = self.config["Redirect"]["Smart Cards"]
        redirect_ports = self.config["Redirect"]["Ports"]
        redirect_drives = self.config["Redirect"]["Drives"]
        folder_redirect = self.config["Folders"]["Redirect"]
        folders = self.config["Folders"]["Folders"]

        # Add server address and port
        if port:
            command.append(f"/v:{server_address}:{port}")
        else:
            command.append(f"/v:{server_address}")

        # Add username and domain
        if username:
            command.append(f"/u:{username}")
        if domain:
            command.append(f"/d:{domain}")

        # Add password securely
        if password:
            command.append(f"/p:{password}")

        # Add display settings
        if resolution:
            command.append(f"/size:{resolution}")
        if use_all_monitors:
            command.append("/multimon")
        if fullscreen:
            command.append("/f")
        if fit_window:
            command.append("/smart-sizing")

        # Add sound settings
        # if major_version and major_version < 3:
        #     if play_sound == "Never":
        #         command.append("/sound:off")
        #     elif play_sound == "On this computer":
        #         command.append("/sound:sys:alsa")
        #     elif play_sound == "On the remote computer":
        #         command.append("/sound:sys:rdpsnd")
        # else:
        #     # Adjust the sound options for FreeRDP 3.x
        #     if play_sound == "Never":
        #         command.append("/audio-mode:2")
        #     elif play_sound == "On this computer":
        #         command.append("/audio-mode:0")
        #     elif play_sound == "On the remote computer":
        #         command.append("/audio-mode:1")

        # Add redirection settings
        if redirect_clipboard:
            command.append("+clipboard")
        # if major_version and major_version < 3:
        #     if redirect_printers:
        #         command.append("/printer")
        #     if redirect_smart_cards:
        #         command.append("/smartcard")
        #     if redirect_ports:
        #         command.append(f"/serial:{redirect_ports}")
        #     if redirect_drives:
        #         command.append("/drive:shared")
        # else:
        #     # Adjust the redirection options for FreeRDP 3.x
        #     if redirect_printers:
        #         for printer, driver in self.get_printers():
        #             if driver != "None":
        #                 command.append(f"/printer:{printer},'{driver}'")
        #     if redirect_smart_cards:
        #         command.append("/smartcard:off")
        #     if redirect_ports:
        #         command.append("/serial:off")
        #     if redirect_drives:
        #         command.append("/drive:off")

        # Ignore Certificate
        if major_version and major_version < 3:
            command.append("/cert-ignore")
        else:
            command.append("/cert:ignore")

        # Debugging: Print the final command
        print(f"Generated freerdp({freerdp_version}) command:")
        print(" ".join(command))

        return command

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

        # Construct the freerdp3 command using the dedicated method
        command = self.gen_command()

        # Create a thread for the connection process
        self.connection_thread = ConnectionThread(command)

        # Connect the success and failure signals to appropriate slots
        self.connection_thread.connection_success.connect(self.on_connection_success)
        self.connection_thread.connection_failed.connect(self.on_connection_failed)

        # Start the connection thread
        self.connection_thread.start()

    def on_connection_success(self):
        # Handle successful connection
        self.connection_dialog.hide()
        QMessageBox.information(self, "Connected", "Connection to the server was successful.")
        self.reset_ui()

    def on_connection_failed(self, error_message):
        # Handle failed connection
        self.connection_dialog.hide()
        QMessageBox.critical(self, "Error", f"Failed to connect to the server: {error_message}")
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
    client_window = Client()
    client_window.show()
    sys.exit(app.exec_())
