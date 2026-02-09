"""Centralized logging configuration for ZURK.

Sets up rotating file handlers so logs don't fill the disk.
Three outputs:
  - Console (stderr) for interactive/uvicorn use
  - logs/zurk.log — all INFO+ messages, rotated at 5 MB (3 backups)
  - logs/zurk-error.log — ERROR+ only, rotated at 2 MB (3 backups)
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"

# Rotation settings
MAX_BYTES = 5 * 1024 * 1024  # 5 MB
ERROR_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
BACKUP_COUNT = 3

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(*, debug: bool = False) -> None:
    """Configure logging for the application.

    Call once at startup (in the app factory or lifespan).
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    level = logging.DEBUG if debug else logging.INFO

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # --- Console handler (stderr) ---
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(level)
    console.setFormatter(formatter)

    # --- Rotating app log ---
    app_file = RotatingFileHandler(
        LOG_DIR / "zurk.log",
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    app_file.setLevel(level)
    app_file.setFormatter(formatter)

    # --- Rotating error log ---
    error_file = RotatingFileHandler(
        LOG_DIR / "zurk-error.log",
        maxBytes=ERROR_MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    error_file.setLevel(logging.ERROR)
    error_file.setFormatter(formatter)

    # Configure root "src" logger so all src.* loggers propagate here
    root = logging.getLogger("src")
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(app_file)
    root.addHandler(error_file)

    # Quiet down noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if debug else logging.WARNING
    )

    logging.getLogger("src").info(
        "Logging initialized (level=%s, log_dir=%s)", level, LOG_DIR
    )
