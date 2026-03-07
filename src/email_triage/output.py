"""Terminal output utilities with ANSI color support and TTY detection.

Provides colored output for info/warning/error/success messages with automatic
fallback to plain text when stdout is not a TTY (cron-safe). Also provides
step-by-step guidance formatting and progressive counter for fetch progress.
"""

from __future__ import annotations

import sys


class Colors:
    """ANSI color codes with automatic TTY detection.

    Colors are disabled when stdout is not a TTY (e.g., cron, pipes),
    producing clean plain-text output suitable for log files.
    """

    _enabled: bool = sys.stdout.isatty()

    RESET = "\033[0m"
    INFO = "\033[36m"      # cyan
    WARN = "\033[33m"      # yellow
    ERROR = "\033[31m"     # red
    SUCCESS = "\033[32m"   # green
    BOLD = "\033[1m"

    @classmethod
    def info(cls, msg: str) -> str:
        """Wrap message in INFO (cyan) color if TTY."""
        return f"{cls.INFO}{msg}{cls.RESET}" if cls._enabled else msg

    @classmethod
    def warn(cls, msg: str) -> str:
        """Wrap message in WARN (yellow) color if TTY."""
        return f"{cls.WARN}{msg}{cls.RESET}" if cls._enabled else msg

    @classmethod
    def error(cls, msg: str) -> str:
        """Wrap message in ERROR (red) color if TTY."""
        return f"{cls.ERROR}{msg}{cls.RESET}" if cls._enabled else msg

    @classmethod
    def success(cls, msg: str) -> str:
        """Wrap message in SUCCESS (green) color if TTY."""
        return f"{cls.SUCCESS}{msg}{cls.RESET}" if cls._enabled else msg

    @classmethod
    def bold(cls, msg: str) -> str:
        """Wrap message in BOLD if TTY."""
        return f"{cls.BOLD}{msg}{cls.RESET}" if cls._enabled else msg


def print_info(msg: str) -> None:
    """Print an informational message to stdout with INFO color."""
    print(Colors.info(msg))


def print_warn(msg: str) -> None:
    """Print a warning message to stderr with WARN color."""
    print(Colors.warn(f"WARNING: {msg}"), file=sys.stderr)


def print_error(msg: str, *, suggestion: str | None = None) -> None:
    """Print an error message to stderr with ERROR color.

    If suggestion is provided, prints an actionable follow-up on the next line.
    """
    print(Colors.error(f"ERROR: {msg}"), file=sys.stderr)
    if suggestion:
        print(f"  -> {suggestion}", file=sys.stderr)


def print_success(msg: str) -> None:
    """Print a success message to stdout with SUCCESS color."""
    print(Colors.success(msg))


def print_step(step_num: int, total: int, msg: str) -> None:
    """Print a step-by-step guidance message with bold formatting.

    Used during first-run setup to guide the user through multi-step processes.
    Example output: [1/3] Opening browser for Google authorization...
    """
    print(Colors.bold(f"[{step_num}/{total}] {msg}"))


def print_progress(current: int, total: int, label: str = "Fetched") -> None:
    """Print a progressive counter that overwrites the current line.

    Uses carriage return to update in-place on TTY. On final call
    (current == total), prints a newline to finalize the line.
    """
    line = f"{label} {current}/{total} emails..."
    if Colors._enabled:
        print(f"\r{line}", end="", flush=True)
    else:
        # Non-TTY: just print each update on its own line
        print(line)
    if current == total:
        print()  # final newline
