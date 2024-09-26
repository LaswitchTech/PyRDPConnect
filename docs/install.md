# PyRDPConnect Installation Guide

## Prerequisites for Running from Source

### macOS Users

**PyRDPConnect** requires XQuartz to function correctly on macOS. XQuartz is an open-source version of the X.Org X server, a component necessary for running remote desktop applications.

#### Step 1: Install XQuartz

1. Visit the official XQuartz website: [XQuartz Download Page](https://www.xquartz.org/).
2. Download and install the latest version of XQuartz.
3. (Optional) Restart your computer to ensure all necessary components are initialized.

#### Step 2: Install Python and Required Packages

```sh
brew install python3
pip3 install pyqt5
```

#### Step 3: Clone the Repository and Run from Source

1. Clone the PyRDPConnect repository:
    ```sh
    git clone https://github.com/LaswitchTech/PyRDPConnect.git
    ```
2. Navigate to the `src` directory and execute the application:
    ```sh
    python3 src/client.py
    ```

### Linux Users

For Linux users, **PyRDPConnect** requires Python 3, PyQt5, and FreeRDP to function correctly.

#### Step 1: Install Required Packages

Update your package list and install the necessary packages:

```sh
sudo apt-get update
sudo apt-get install -y git python3 python3-pip python3-pyqt5 python3-pyqt5.* freerdp2-x11
```

#### Step 2: Clone the Repository and Run from Source

1. Clone the PyRDPConnect repository:
    ```sh
    git clone https://github.com/LaswitchTech/PyRDPConnect.git
    ```
2. Navigate to the `src` directory and execute the application:
    ```sh
    python3 src/client.py
    ```

## Running the Pre-Built Application

### macOS Users

**PyRDPConnect** is available as a pre-built macOS application (`.app`). Before using the application, you must install XQuartz.

#### Step 1: Install XQuartz

1. Visit the official XQuartz website: [XQuartz Download Page](https://www.xquartz.org/).
2. Download and install the latest version of XQuartz.
3. (Optional) Restart your computer to ensure all necessary components are initialized.

#### Step 2: Run the PyRDPConnect Application

1. Locate the `PyRDPConnect.app` in the `dist/macos` directory or where you saved it.
2. Double-click the application to launch it.
3. **PyRDPConnect** should now open and run as expected.

**Troubleshooting**: If **PyRDPConnect** does not open or shows an error related to X11 or XQuartz, ensure that XQuartz is installed and running. You can manually start XQuartz from your Applications folder (`/Applications/Utilities/XQuartz.app`).

### Linux Users

**PyRDPConnect** is also available as a pre-built single-file executable on Linux.

#### Step 1: Download and Install Dependencies

Make sure FreeRDP is installed:

```sh
sudo apt-get install -y freerdp2-x11
```

#### Step 2: Run the PyRDPConnect Executable

1. Locate the `PyRDPConnect` executable in the `dist/linux` directory or where you saved it.
2. Make the file executable if it’s not already:
    ```sh
    chmod +x dist/linux/PyRDPConnect
    ```
3. Run the application:
    ```sh
    ./dist/linux/PyRDPConnect
    ```

## Additional Information

If you have any questions or need further assistance, feel free to open an issue in the [GitHub Repository](https://github.com/LaswitchTech/PyRDPConnect/issues).
