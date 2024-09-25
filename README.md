<p align="center"><img src="src/img/logo.png" /></p>

# PyRDPConnect
![License](https://img.shields.io/github/license/LaswitchTech/PyRDPConnect?style=for-the-badge)
![GitHub repo size](https://img.shields.io/github/repo-size/LaswitchTech/PyRDPConnect?style=for-the-badge&logo=github)
![GitHub top language](https://img.shields.io/github/languages/top/LaswitchTech/PyRDPConnect?style=for-the-badge)
![Version](https://img.shields.io/github/v/release/LaswitchTech/PyRDPConnect?label=Version&style=for-the-badge)

## Description
`PyRDPConnect` is a remote desktop client based on FreeRDP 2. It is a front-end for thin-clients.

## Features
  - Support Microsoft RDP Connections (Windows Terminal Server and Direct Connection)

## Planned
  - Support for openVPN

## License
This software is distributed under the [MIT](LICENSE) license.

## Requirements
* Python >= 3.0

## Security
Please disclose any vulnerabilities found responsibly – report security issues to the maintainers privately. See [SECURITY.md](SECURITY.md) for more information.

## Installation

### Requirements
```sh
sudo apt-get update
sudo apt-get install -y git python python3 pip python3-pyqt5 python3-pyqt5.* freerdp2-x11
```

### Clone
```sh
git clone https://github.com/LaswitchTech/PyRDPConnect.git
```

### Execute from source
```sh
./PyRDPConnect/src/client.py
```

### Build
```sh
sudo apt-get install -y build-essential libssl-dev libffi-dev python3-dev qt5-default qtbase5-dev qtchooser qt5-qmake qtbase5-dev-tools qttools5-dev-tools
sudo apt --fix-broken install
cd PyRDPConnect
./build.sh
```

## How do I use it?
Review the [Documentation](docs/).
