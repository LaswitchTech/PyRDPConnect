#!/usr/bin/env python3
# src/app/command-line.py
import sys
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

        # Set application mode
        self._mode = "cli"

        # Initialize command line
        self._commands: dict[str, Any] = {}

        # Add help command
        self.add("help", "Show this help message", self.help)

        # Helper
        self._helper = Helper()

        # Configuration manager
        self._configuration = Configuration()

        # Logger
        self._logger = Log()

        # Initialize core commands
        if hasattr(self._configuration, "cli") and callable(getattr(self._configuration, "cli")):
            self._configuration.cli(self)
        if hasattr(self._logger, "cli") and callable(getattr(self._logger, "cli")):
            self._logger.cli(self)

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

    @property
    def mode(self) -> str:
        return self._mode

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def help(self) -> None:
        print(f"Usage: {self.name} [command] [options]")
        print()
        print("Available commands:")
        print()

        entries: list[tuple[str, str]] = []

        # Build usage strings including required arguments
        for cmd, info in sorted(self._commands.items()):
            desc = info.get("description", "") or ""
            args_required = info.get("args_required", 0) or 0
            arg_names = info.get("arg_names") or []

            # Ensure we have at least `args_required` argument labels
            if len(arg_names) < args_required:
                # Pad with generic placeholders if needed
                start_index = len(arg_names) + 1
                for i in range(start_index, args_required + 1):
                    arg_names.append(f"<arg{i}>")

            usage = cmd
            if args_required > 0:
                usage += " " + " ".join(arg_names[:args_required])

            entries.append((usage, desc))

        # Compute padding for alignment
        if entries:
            max_cmd_len = max(len(usage) for usage, _ in entries)
        else:
            max_cmd_len = 0

        for usage, desc in entries:
            print(f"  {usage:<{max_cmd_len}}  {desc}")

    def add(self, command: str, description: str = "", callable: Optional[callable] = None, args: int = 0, arg_names: Optional[list[str]] = None) -> None:
        if not command.startswith("--"):
            command = f"--{command}"
        # Normalize argument names
        if arg_names is None:
            arg_names = []
        # Store command metadata
        self._commands[command] = {
            "description": description,
            "callable": callable,
            "args_required": args,
            "arg_names": arg_names,
        }

    def run(self, command: str, *args: Any, **kwargs: Any) -> Any:
        cmd = self._commands.get(command)
        if not cmd:
            raise ValueError(f"Command not found: {command}")

        required = cmd.get("args_required", 0)
        arg_names = cmd.get("arg_names") or []

        if len(arg_names) < required:
            # Pad missing argument names with generic placeholders
            start_index = len(arg_names) + 1
            for i in range(start_index, required + 1):
                arg_names.append(f"<arg{i}>")

        if len(args) < required:
            missing = required - len(args)
            missing_list = " ".join(arg_names[len(args):required])
            raise ValueError(f"Missing {missing} argument(s) for {command}: {missing_list}")

        func = cmd.get("callable")
        if not func:
            raise ValueError(f"Command has no callable: {command}")

        return func(*args, **kwargs)

    def exec(self) -> int:
        argv = list(self.arguments())  # includes program name as first element

        # No command provided: show help and exit 0
        if len(argv) < 2:
            self.help()
            return 0

        commands: list[tuple[str, list[str]]] = []

        current_cmd: Optional[str] = None
        current_args: list[str] = []

        # Parse argv into (command, args) groups
        for arg in argv[1:]:
            if arg.startswith("--"):
                # Starting a new command
                if current_cmd is not None:
                    commands.append((current_cmd, current_args))
                current_cmd = arg
                current_args = []
            else:
                # Positional argument for the current command
                if current_cmd is None:
                    # We got an argument before any command; treat as error
                    print(f"Error: unexpected argument '{arg}' before any command.", file=sys.stderr)
                    return 1
                current_args.append(arg)

        # Append the last pending command
        if current_cmd is not None:
            commands.append((current_cmd, current_args))

        # Still no valid command? Show help.
        if not commands:
            self.help()
            return 0

        exit_code = 0

        # Execute each command in sequence; stop on first error
        for command, cmd_args in commands:
            try:
                self.run(command, *cmd_args)
            except Exception as e:
                print(f"Error in {command}: {e}", file=sys.stderr)
                exit_code = 1
                break

        return exit_code
