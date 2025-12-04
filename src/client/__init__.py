#!/usr/bin/env python3
# src/client/__init__.py

from .client import Client
from .freerdp import FreeRDP

__version__ = "1.0.0"

__all__ = ["Client", "FreeRDP"]
