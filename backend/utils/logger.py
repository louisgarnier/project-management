import logging
import os
import sys
from datetime import date
from logging.handlers import TimedRotatingFileHandler

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = os.path.join(os.path.dirname(__file__), "../../logs")


def _file_handler(name: str) -> TimedRotatingFileHandler:
    os.makedirs(LOG_DIR, exist_ok=True)
    today = date.today().isoformat()
    path = os.path.join(LOG_DIR, f"{name}_{today}.log")
    handler = TimedRotatingFileHandler(path, when="midnight", backupCount=30)
    handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    return handler


def get_logger(module: str) -> logging.Logger:
    logger = logging.getLogger(f"calltracker.{module}")
    if not logger.handlers:
        logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
        logger.addHandler(logging.StreamHandler(sys.stdout))
        logger.addHandler(_file_handler("backend"))
    return logger


api_logger = get_logger("api")
db_logger = get_logger("database")
sse_logger = get_logger("sse")
claude_logger = get_logger("claude")
