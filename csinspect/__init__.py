from __future__ import annotations

import sys

import sentry_sdk
from loguru import logger

from csinspect.config import DEBUG_LOGGING, DEV_MODE, SENTRY_DSN, SENTRY_TRACES_SAMPLE_RATE

if not DEV_MODE and SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
    )


# --- formats ---
TIME_FORMAT = "<red>[{time:h:mm:ss A}]</red>"
LEVEL_FORMAT = "<level>{level: <8}</level>"
MESSAGE_FORMAT = "<bold>{message}</bold>"
LOG_FORMAT = f"{TIME_FORMAT} {LEVEL_FORMAT} | {MESSAGE_FORMAT}"

CONFIG = {
    "handlers": [
        {"sink": sys.stdout, "format": LOG_FORMAT, "level": "DEBUG" if DEV_MODE or DEBUG_LOGGING else "INFO"},
    ]
}

logger.configure(**CONFIG)  # type: ignore[arg-type]
