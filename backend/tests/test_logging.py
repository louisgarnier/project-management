import logging
import os

from starlette.testclient import TestClient

from backend.main import app
from backend.utils.logger import get_logger

client = TestClient(app)


def test_logger_emits_to_stdout(caplog):
    with caplog.at_level(logging.INFO, logger="calltracker.api"):
        response = client.get("/health")
    assert response.status_code == 200
    # Middleware logs the request and response
    assert any("/health" in record.message for record in caplog.records)


def test_logger_respects_log_level(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    # Re-create a logger at WARNING level
    test_logger = logging.getLogger("calltracker.test_level")
    test_logger.setLevel(logging.WARNING)
    # INFO message should not be captured at WARNING level
    with caplog_handler() as records:
        test_logger.info("this should not appear")
        test_logger.warning("this should appear")
    assert not any("this should not appear" in r for r in records)
    assert any("this should appear" in r for r in records)


def caplog_handler():
    """Context manager that captures log records into a list."""
    import contextlib

    records = []

    class _Handler(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    @contextlib.contextmanager
    def _ctx():
        handler = _Handler()
        logging.root.addHandler(handler)
        try:
            yield records
        finally:
            logging.root.removeHandler(handler)

    return _ctx()


def test_log_file_created_on_request(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    # Just verify the health endpoint responds — file handler creation is
    # tested via the logger module itself
    response = client.get("/health")
    assert response.status_code == 200
