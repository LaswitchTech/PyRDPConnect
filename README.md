<p align="center"><img src="src/icons/icon.png" /></p>

# PyRDPConnect (DEV)(Not ready for production)
![License](https://img.shields.io/github/license/LaswitchTech/PyRDPConnect?style=for-the-badge)
![GitHub repo size](https://img.shields.io/github/repo-size/LaswitchTech/PyRDPConnect?style=for-the-badge&logo=github)
![GitHub top language](https://img.shields.io/github/languages/top/LaswitchTech/PyRDPConnect?style=for-the-badge)
![Version](https://img.shields.io/github/v/release/LaswitchTech/PyRDPConnect?label=Version&style=for-the-badge)

## Description
PyRDPConnect is a cross-platform Python application designed to provide a sleek, modern, and efficient front-end interface for connecting to Remote Desktop (RDP) sessions. Built with PyQt5, the application supports both macOS and Linux, offering an intuitive and user-friendly experience for users who need to manage RDP connections across multiple environments.

## Features
  - **Cross-Platform Compatibility**: PyRDPConnect is compatible with both macOS and Linux, with specific adjustments made to ensure seamless operation on both operating systems.
  - **Customizable Interface**: The application uses a customizable UI that allows users to define their preferred settings, such as server address, resolution, multi-monitor support, sound redirection, and more.
  - **Auto-Detection of FreeRDP Version**: The application automatically detects the version of FreeRDP installed on the system and adjusts the command syntax accordingly, ensuring compatibility with both older and newer versions of FreeRDP.
  - **Bundled FreeRDP**: PyRDPConnect includes the ability to package the correct version of FreeRDP within the application, simplifying deployment and reducing dependency issues.
  - **Certificate Handling**: The application handles SSL certificates during connection attempts, providing users with the option to accept or reject untrusted certificates through a dialog box.
  - **Resource Management**: The application efficiently manages resources, including styles, icons, and other assets, ensuring they are bundled correctly in the final application package.
  - **Connection Management**: The interface includes a progress dialog to indicate the status of connection attempts, with options to cancel the attempt if necessary.
  - **Logging and Debugging**: The application includes logging features for easier debugging and tracking of issues during the connection process.

## License
This software is distributed under the [MIT](LICENSE) license.

### Third-Party Licenses
This project uses FreeRDP, which is licensed under the [Apache License 2.0](THIRD_PARTY_LICENSES) license.

## Security
Please disclose any vulnerabilities found responsibly – report security issues to the maintainers privately. See [SECURITY.md](SECURITY.md) for more information.

## Contributing
Contributions to PyRDPConnect are welcome! If you have ideas for new features or have found bugs, please open an issue or submit a pull request.

### How to Contribute
  - **Fork the Repository**: Create a fork of the repository on GitHub.
  - **Create a New Branch**: For new features or bug fixes, create a new branch in your fork.
  - **Submit a Pull Request**: Once your changes are ready, submit a pull request to the main repository.

## Acknowledgments
  - **FreeRDP**: For providing a powerful and flexible open-source RDP client.
  - **PyQt5**: For making it easy to create a modern and responsive UI in Python.
  - **PyInstaller**: For simplifying the process of packaging Python applications for distribution.

## Wait, where is the documentation?
Review the [Documentation](docs/usage.md).
