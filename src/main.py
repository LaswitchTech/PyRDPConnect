#!/usr/bin/env python3
# src/main.py

import sys

from app.application import Application
from client.client import Client

if __name__ == "__main__":
    app = Application(sys.argv)
    app.set_mainWindow(Client(
        helper=app.helper,
        configuration=app.configuration,
        logger=app.logger,
    ))
    sys.exit(app.exec_())
