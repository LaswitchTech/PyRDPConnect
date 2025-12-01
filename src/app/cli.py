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

        # Logger
        self._logger = Log()

        # Initialize command line
        self._commands: dict[str, Any] = {}

        # Add help command
        self.add("help", "Show this help message", self.help)

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

    def help(self) -> None:
        print(f"Usage: {self.name} [command] [options]")
        print()
        print(f"{self.name} - Available commands:")

        # Sort commands for stable output
        for cmd, info in sorted(self._commands.items()):
            desc = info.get("description", "")
            # Strip the leading dashes for display purposes only
            display_cmd = cmd[2:] if cmd.startswith("--") else cmd
            print(f"  {display_cmd:<16} {desc}")

    def add(self, command: str, description: str = "", callable: Optional[callable] = None) -> None:
        if not command.startswith("--"):
            command = f"--{command}"
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
