"""
Logging utilities for Rekordbox Smart Playlists.

Provides consistent logging configuration across all modules with:
- Colored console output
- File logging support
- Progress indicators
- Context-aware formatting
"""

import logging
import sys
from pathlib import Path
from typing import Optional, Dict, Any, Type
from datetime import datetime
import colorama
from colorama import Fore, Style
from types import TracebackType

# Initialize colorama for cross-platform colored output
colorama.init(autoreset=True)


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colored output for different log levels."""

    COLORS = {
        "DEBUG": Fore.CYAN,
        "INFO": Fore.GREEN,
        "WARNING": Fore.YELLOW,
        "ERROR": Fore.RED,
        "CRITICAL": Fore.RED + Style.BRIGHT,
    }

    def format(self, record: logging.LogRecord) -> str:
        # Add color to the level name
        level_color = self.COLORS.get(record.levelname, "")
        record.levelname = f"{level_color}{record.levelname}{Style.RESET_ALL}"

        # Format the message
        formatted = super().format(record)

        return formatted


class ProgressLogger:
    """Helper class for logging progress with consistent formatting."""

    def __init__(
        self, logger: logging.Logger, total: int, description: str = "Processing"
    ):
        self.logger = logger
        self.total = total
        self.description = description
        self.current = 0
        self.start_time = datetime.now()

    def update(self, increment: int = 1, message: Optional[str] = None) -> None:
        """Update progress and optionally log a message."""
        self.current += increment

        if message:
            percentage = (self.current / self.total) * 100 if self.total > 0 else 0
            elapsed = datetime.now() - self.start_time
            self.logger.info(
                f"[{percentage:5.1f}%] {self.description}: {message} ({elapsed})"
            )

    def finish(self, message: Optional[str] = None) -> None:
        """Log completion message."""
        elapsed = datetime.now() - self.start_time
        final_message = message or f"{self.description} completed"
        self.logger.info(f"✅ {final_message} ({elapsed})")


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    console: bool = True,
    format_string: Optional[str] = None,
    include_timestamp: bool = True,
) -> logging.Logger:
    """
    Set up logging configuration.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path for file logging
        console: Whether to enable console logging
        format_string: Custom format string
        include_timestamp: Whether to include timestamps in logs

    Returns:
        Configured logger instance
    """
    # Convert string level to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Clear any existing handlers
    root_logger.handlers.clear()

    # Default format
    if format_string is None:
        if include_timestamp:
            format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        else:
            format_string = "%(name)s - %(levelname)s - %(message)s"

    # Console handler with colored output
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)

        # Use colored formatter for console
        console_formatter = ColoredFormatter(format_string)
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    # File handler if requested
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(numeric_level)

        # Use standard formatter for file (no colors)
        file_formatter = logging.Formatter(format_string)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name."""
    return logging.getLogger(name)


def log_function_call(
    func_name: str, args: Dict[str, Any], logger: logging.Logger
) -> None:
    """Log a function call with its arguments."""
    args_str = ", ".join(f"{k}={v}" for k, v in args.items())
    logger.debug(f"Calling {func_name}({args_str})")


def log_exception(
    logger: logging.Logger, exception: Exception, context: str = ""
) -> None:
    """Log an exception with context information."""
    context_str = f" in {context}" if context else ""
    logger.error(
        f"Exception{context_str}: {type(exception).__name__}: {exception}",
        exc_info=True,
    )


def log_section(logger: logging.Logger, title: str, level: str = "INFO") -> None:
    """Log a section header for better organization."""
    separator = "=" * 60
    getattr(logger, level.lower())(f"\n{separator}")
    getattr(logger, level.lower())(f"{title.upper()}")
    getattr(logger, level.lower())(separator)


def log_subsection(logger: logging.Logger, title: str, level: str = "INFO") -> None:
    """Log a subsection header."""
    separator = "-" * 40
    getattr(logger, level.lower())(f"\n{separator}")
    getattr(logger, level.lower())(title)
    getattr(logger, level.lower())(separator)


def log_success(logger: logging.Logger, message: str) -> None:
    """Log a success message with special formatting."""
    logger.info(f"✅ {message}")


def log_warning(logger: logging.Logger, message: str) -> None:
    """Log a warning message with special formatting."""
    logger.warning(f"⚠️  {message}")


def log_error(logger: logging.Logger, message: str) -> None:
    """Log an error message with special formatting."""
    logger.error(f"❌ {message}")


def log_info(logger: logging.Logger, message: str) -> None:
    """Log an info message with special formatting."""
    logger.info(f"ℹ️  {message}")


def log_debug(logger: logging.Logger, message: str) -> None:
    """Log a debug message with special formatting."""
    logger.debug(f"🔍 {message}")


class LoggingContext:
    """Context manager for temporary logging configuration."""

    def __init__(self, level: str):
        self.level = level
        self.original_level = logging.getLogger().level

    def __enter__(self) -> "LoggingContext":
        root_logger = logging.getLogger()
        self.original_level = root_logger.level
        root_logger.setLevel(getattr(logging, self.level.upper()))
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        if self.original_level is not None:
            logging.getLogger().setLevel(self.original_level)


def create_progress_logger(
    total: int, description: str = "Processing"
) -> ProgressLogger:
    """Create a progress logger instance."""
    logger = get_logger("progress")
    return ProgressLogger(logger, total, description)


# Convenience functions for common logging patterns
def setup_basic_logging(
    verbose: bool = False, log_file: Optional[str] = None
) -> logging.Logger:
    """Set up basic logging configuration based on verbosity."""
    level = "DEBUG" if verbose else "INFO"
    return setup_logging(level=level, log_file=log_file)


def setup_quiet_logging(log_file: Optional[str] = None) -> logging.Logger:
    """Set up quiet logging (warnings and errors only)."""
    return setup_logging(level="WARNING", log_file=log_file, console=True)


if __name__ == "__main__":
    # Example usage and testing
    logger = setup_logging(level="DEBUG")

    test_logger = get_logger("test")

    log_section(test_logger, "Testing Logging System")
    test_logger.debug("This is a debug message")
    test_logger.info("This is an info message")
    test_logger.warning("This is a warning message")
    test_logger.error("This is an error message")

    log_success(test_logger, "Logging system initialized successfully")
    log_warning(test_logger, "This is a test warning")
    log_error(test_logger, "This is a test error")

    # Test progress logger
    progress = create_progress_logger(10, "Test Progress")
    for i in range(10):
        progress.update(message=f"Processing item {i+1}")
    progress.finish("All items processed")
