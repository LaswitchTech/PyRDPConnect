#!/usr/bin/env python3
# src/main.py

import sys

from app.application import Application
from client.client import Client

def main():
    app = Application(sys.argv)

    # Create main window and register it with Application
    win = Client()
    app.set_mainWindow(win)

    # All other code gets app via QApplication.instance()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
