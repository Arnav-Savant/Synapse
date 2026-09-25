"""Centralized logging configuration.

Call `configure_logging()` once, at process startup (`main.py`, before
anything else runs), so every module's `logging.getLogger(__name__)` call
inherits a consistent format/level. Without this, Python falls back to its
silent "handler of last resort" (WARNING+ to stderr, unformatted) — which
is what "no logger configured at all" meant in practice.
"""

import logging.config

from app.core.config import get_server_config


def configure_logging() -> None:
    server_config = get_server_config()
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "level": server_config.log_level,
                },
            },
            "root": {
                "handlers": ["console"],
                "level": server_config.log_level,
            },
        }
    )
