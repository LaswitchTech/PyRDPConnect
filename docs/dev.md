# Setting Up the Development Environment

## Prerequisites - macOS
```sh
brew install python
brew install python3
brew install freerdp
```

## Prerequisites - Linux
```sh
sudo apt-get install -y build-essential libssl-dev libffi-dev python3-dev qt5-default qtbase5-dev qtchooser qt5-qmake qtbase5-dev-tools qttools5-dev-tools
```

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

## Running the Application
After building, the application can be run directly from the generated ``.app`` bundle on macOS or from the executable on Linux.

## Packaging for Distribution
To package the application for distribution, the ``build.sh`` script is used. The script handles the following:
  - Checks if a Python virtual environment is available and creates one if not.
  - Installs necessary Python packages within the environment.
  - Detects the operating system and packages the correct version of FreeRDP.
  - Bundles all necessary resources, including styles, icons, and images.
  - Generates the final application package using PyInstaller, with appropriate resources included.
