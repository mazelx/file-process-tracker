"""
Logging system configuration module
"""
import logging
import logging.handlers
from pathlib import Path
from typing import Optional


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    log_format: Optional[str] = None,
    max_bytes: int = 10485760,  # 10 MB
    rotation_count: int = 7,
    console: bool = True
) -> logging.Logger:
    """
    Configure the logging system for the application

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to the log file (optional)
        log_format: Log message format
        max_bytes: Maximum size of a log file before rotation
        rotation_count: Number of rotation files to keep
        console: Enable console output

    Returns:
        Configured logger
    """
    # Default format
    if log_format is None:
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    # Convert log level string to constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Formatter
    formatter = logging.Formatter(log_format)

    # Console handler
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # File handler with rotation
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            filename=str(log_path),
            maxBytes=max_bytes,
            backupCount=rotation_count,
            encoding='utf-8'
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Application-specific logger
    app_logger = logging.getLogger('file_process_tracker')
    app_logger.setLevel(numeric_level)

    # Initial log
    app_logger.info("Logging system initialized")
    app_logger.debug(f"Log level: {level}")
    if log_file:
        app_logger.debug(f"Log file: {log_file}")
        app_logger.debug(f"Rotation: {rotation_count} files of {max_bytes} bytes max")

    return app_logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a specific module

    Args:
        name: Module name (usually __name__)

    Returns:
        Logger configured for the module
    """
    return logging.getLogger(name)


class LogContext:
    """Context manager for temporary logs with different level"""

    def __init__(self, logger: logging.Logger, level: str = "DEBUG"):
        """
        Initialize the log context

        Args:
            logger: Logger to temporarily modify
            level: New temporary log level
        """
        self.logger = logger
        self.original_level = logger.level
        self.new_level = getattr(logging, level.upper(), logging.DEBUG)

    def __enter__(self):
        """Enter the context with the new level"""
        self.logger.setLevel(self.new_level)
        return self.logger

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Restore the original level when exiting the context"""
        self.logger.setLevel(self.original_level)


def log_exception(logger: logging.Logger, message: str = "Exception caught"):
    """
    Decorator to automatically log exceptions

    Args:
        logger: Logger to use
        message: Context message for the exception

    Usage:
        @log_exception(logger)
        def my_function():
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.exception(f"{message} dans {func.__name__}: {str(e)}")
                raise
        return wrapper
    return decorator


class ProgressLogger:
    """Specialized logger for displaying processing progress"""

    def __init__(self, logger: logging.Logger, total: int, prefix: str = "Progress"):
        """
        Initialize the progress logger

        Args:
            logger: Logger to use
            total: Total number of elements to process
            prefix: Prefix for progress messages
        """
        self.logger = logger
        self.total = total
        self.prefix = prefix
        self.current = 0
        self.last_percentage = -1

    def update(self, increment: int = 1, message: Optional[str] = None):
        """
        Update the progress

        Args:
            increment: Number of processed elements
            message: Optional message to display
        """
        self.current += increment
        percentage = int((self.current / self.total) * 100) if self.total > 0 else 100

        # Log only if percentage decade changes
        if percentage // 10 > self.last_percentage // 10:
            progress_msg = f"{self.prefix}: {self.current}/{self.total} ({percentage}%)"
            if message:
                progress_msg += f" - {message}"
            self.logger.info(progress_msg)
            self.last_percentage = percentage

    def complete(self, message: Optional[str] = None):
        """
        Mark the progress as complete

        Args:
            message: Optional completion message
        """
        self.current = self.total
        complete_msg = f"{self.prefix}: Complete ({self.total} elements)"
        if message:
            complete_msg += f" - {message}"
        self.logger.info(complete_msg)