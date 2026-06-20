"""
Logging configuration using loguru.
Provides structured logging with file rotation.
"""

import sys
from pathlib import Path
from loguru import logger
from voice_service.config import settings


def setup_logger():
    """Configure loguru logger with console and file outputs."""
    # Remove default logger
    logger.remove()
    
    # Console logger with colorized output
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=settings.LOG_LEVEL,
        colorize=True
    )
    
    # File logger with rotation
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    logger.add(
        log_dir / "voice_service_{time:YYYY-MM-DD}.log",
        rotation="1 day",
        retention="7 days",
        compression="zip",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        encoding="utf-8"
    )
    
    # Error logger for critical issues
    logger.add(
        log_dir / "errors.log",
        rotation="1 week",
        retention="30 days",
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        encoding="utf-8"
    )
    
    logger.info(f"Logger initialized with level: {settings.LOG_LEVEL}")
    return logger


# Initialize logger when module is imported
logger = setup_logger()


def get_logger():
    """Get the configured logger instance."""
    return logger