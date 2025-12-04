# Third-Party Licenses

PyRDPConnect bundles several third-party open-source components.
This file lists their licenses and provides links to their source, as required by their respective licenses.

---

## 1. FreeRDP
**License:** Apache License 2.0
**Project URL:** https://www.freerdp.com
**Source Code:** https://github.com/FreeRDP/FreeRDP

PyRDPConnect includes FreeRDP (`xfreerdp`) as a standalone executable.
No modifications were made.

---

## 2. OpenVPN
**License:** GNU General Public License v2 (GPLv2)
**Project URL:** https://openvpn.net
**Source Code:** https://openvpn.net/community-downloads/
(See “Source Tarball” section)

PyRDPConnect may include the OpenVPN binary in the `bin/` folder for compatibility.
No modifications were made.

---

## 3. WireGuard / WireGuard-Tools
**License:** GNU General Public License v2 (GPLv2)
**Project URL:** https://www.wireguard.com
**Source Code:** https://www.wireguard.com/repositories/

PyRDPConnect may include `wg`, `wg-quick`, or WireGuard-Tools in the `bin/` folder.
No modifications were made.

---

## 4. PyQt5
**License:** GPLv3 (or commercially licensed via Riverbank Computing)
**Project URL:** https://www.riverbankcomputing.com/software/pyqt
**Source Code:** https://www.riverbankcomputing.com/software/pyqt/download

Used for the PyRDPConnect graphical interface.

---

## 5. Python
**License:** Python Software Foundation License (PSFL)
**Project URL:** https://www.python.org
**Source Code:** https://www.python.org/downloads/source/

Python is used as the core runtime environment.

---

## 6. Icons / UI Resources
Some icons and interface resources used in this project are redistributed under permissive licenses (MIT, CC-BY, or similar).
See individual files for details where applicable.

---

# Redistribution Notes

PyRDPConnect distributes third-party binaries **as separate, unmodified executables**, consistent with GPL aggregation rules.

To comply with GPLv2/GPLv3:

- All licenses listed above are provided unmodified.
- All source-code links point to the original upstream repositories.
- PyRDPConnect does **not** statically or dynamically link to OpenVPN, WireGuard, or FreeRDP code; they are executed as standalone programs.

---

If you believe a required license or notice is missing, please open an issue at:
https://github.com/LaswitchTech/PyRDPConnect/issues
