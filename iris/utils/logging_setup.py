# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import json
import logging
from pathlib import Path
from datetime import datetime


class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter to prevent log injection attacks."""

    def format(self, record):
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


def configure_logging(output_dir: Path, console_level: int = logging.INFO) -> None:
    """
    Configure a logger that
    1) writes everything ≥ DEBUG to a timestamped file (JSON format), and
    2) echoes anything ≥ console_level to the console (JSON format).

    Args:
        output_dir: Directory to store log files
        console_level: Minimum level for console output (default: INFO)
    """
    # Console handler – always available
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)

    json_formatter = JSONFormatter()
    console_handler.setFormatter(json_formatter)

    handlers = [console_handler]

    # Try to set up file logging; fall back to console-only if filesystem is read-only
    try:
        log_dir = output_dir / "logs"
        log_dir.mkdir(exist_ok=True, parents=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = log_dir / f"{timestamp}.log"

        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(json_formatter)
        handlers.append(file_handler)
    except OSError:
        # Read-only filesystem or permission error — continue with console-only logging
        pass

    # Root config (basicConfig must be called only once)
    logging.basicConfig(
        level=logging.DEBUG,  # root collects every message
        handlers=handlers,
        force=True,  # overrides prior configs if any
    )

    for noisy in ["botocore", "urllib3"]:
        logging.getLogger(noisy).setLevel(logging.ERROR)
