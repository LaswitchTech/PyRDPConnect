#!/usr/bin/env python3
# src/main.py

import sys

from app.application import Application
from app.cli import CommandLine
from client.client import Client

# ---------------------------------------------------------------------------
# Customization and start of the application
# ---------------------------------------------------------------------------

name = "PyRDPConnect"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def has_option():
    return any(arg.startswith('--') for arg in sys.argv)

# ---------------------------------------------------------------------------
# Start of the application
# ---------------------------------------------------------------------------

def start_app():
    app = Application(name,sys.argv)

    # Create main window and register it with Application
    win = Client()
    app.set_mainWindow(win)

    # All other code gets app via QApplication.instance()
    sys.exit(app.exec_())

def start_cli():
    app = CommandLine(name,sys.argv)

    # All other code gets app via QApplication.instance()
    sys.exit(app.exec_())

# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if has_option():
        start_cli()
    else:
        start_app()
