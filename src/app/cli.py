#!/usr/bin/env python3
# src/app/command-line.py
from typing import Any, Optional

from PyQt5.QtWidgets import QApplication

from .helper import Helper
from .configuration import Configuration
from .log import Log

# ---------------------------------------------------------------------------
# CommandLine class
# ---------------------------------------------------------------------------

class CommandLine(QApplication):

    def __init__(self, name: Optional[str] = None, argv=None):

        # Initialize QApplication
        super().__init__(argv or [])

        # Application name
        if name:
            self.setApplicationName(name)

        # Helper
        self._helper = Helper()

        # Configuration manager
        self._configuration = Configuration()
        self._configuration.configChanged.connect(self.reset)

        # Default configuration entries
        self._configuration.add("administration.update", None, "button", label="Check for Updates", action=self.update)

        # Save any new defaults
        self._configuration.save()

        # Logger
        self._logger = Log()

        # Initialize command line
        self._commands = dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Properties / accessors
    # ------------------------------------------------------------------

    @property
    def helper(self) -> Helper:
        return self._helper

    @property
    def logger(self) -> Log:
        return self._logger

    @property
    def configuration(self) -> Configuration:
        return self._configuration

    @property
    def name(self) -> str:
        return self.applicationName()

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def add(self, command: str, description: str = "", callable: Optional[callable] = None) -> None:
        self._commands[command] = {
            "description": description,
            "callable": callable,
        }

    def run(self, command: str, *args: Any, **kwargs: Any) -> Any:
        cmd = self._commands.get(command)
        if not cmd:
            raise ValueError(f"Command not found: {command}")
        func = cmd.get("callable")
        if not func:
            raise ValueError(f"Command has no callable: {command}")
        return func(*args, **kwargs)
