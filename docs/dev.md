# Setting Up the Development Environment

## Prerequisites - macOS

Ensure you are using Python 3.6 or later. You can check your Python version with:

```sh
python3 --version
```

Then, install the necessary dependencies:

```sh
brew install python
brew install python3
brew install freerdp
```

## Prerequisites - Linux

Ensure you have the following packages installed:

```sh
sudo apt-get install -y build-essential libssl-dev libffi-dev libqt5svg5 python3-dev qt5-* qtbase5-dev qtchooser qtbase5-dev-tools qttools5-dev-tools
```

### Dependency Overview

- **Python/Python3:** Required for running and managing the Python scripts within the project.
- **FreeRDP:** A critical component for handling RDP connections, required for both development and runtime.
- **Qt5 Libraries:** These are necessary for building the GUI components of the application.

## Clone

**Clone the Repository**:

```sh
git clone https://github.com/LaswitchTech/PyRDPConnect.git
```

## Build

**Run the Build Script**: Use the provided build.sh script to set up the Python environment, install necessary dependencies, and build the application:

```sh
./build.sh
```

The `build.sh` script will:

  - Check if a Python virtual environment is available and create one if not.
  - Install necessary Python packages within the environment.
  - Detect the operating system and package the correct version of FreeRDP.
  - Bundle all necessary resources, including styles, icons, and images.
  - Generate the final application package using PyInstaller, with appropriate resources included.

**Platform-Specific Notes:**

- **macOS:** Ensure XQuartz is installed if you're planning to run the application in a graphical environment.
- **Linux:** If any dependencies fail to install, verify that your package list is up-to-date with `sudo apt-get update`.

## Running the Application

After building, the application can be run directly from the generated `.app` bundle on macOS or from the executable on Linux.

## Packaging for Distribution

To package the application for distribution, the `build.sh` script is used. It handles the entire packaging process and ensures all necessary components are bundled appropriately for the target operating system.
