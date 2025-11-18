#!/usr/bin/env python3
# src/network/__init__.py

from .diagnostic import Diagnostic
from .wifi import WiFi
from .openvpn import OpenVPN
from .wireguard import WireGuard

__version__ = "1.0.0"

__all__ = ["Diagnostic", "WiFi", "OpenVPN", "WireGuard"]
