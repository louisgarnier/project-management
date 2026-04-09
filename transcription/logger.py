import logging
import os
import sys
from datetime import date
from logging.handlers import TimedRotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(__file__), "../logs")


def get_transcription_logger(module: str) -> logging.Logger:
    logger = logging.getLogger(f"transcription.{module}")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        logger.addHandler(logging.StreamHandler(sys.stdout))
        os.makedirs(LOG_DIR, exist_ok=True)
        today = date.today().isoformat()
        handler = TimedRotatingFileHandler(
            os.path.join(LOG_DIR, f"transcription_{today}.log"),
            when="midnight",
            backupCount=30,
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(handler)
    return logger
