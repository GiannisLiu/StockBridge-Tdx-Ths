import os
import tempfile
from stockbridge.logger import setup_logging


def test_setup_logging_returns_logger():
    log_dir = tempfile.mkdtemp()
    logger = setup_logging(log_dir)
    assert logger is not None
    assert logger.level == 20  # INFO


def test_setup_logging_creates_log_file():
    log_dir = tempfile.mkdtemp()
    logger = setup_logging(log_dir)
    logger.info("test message")
    files = os.listdir(log_dir)
    assert len(files) == 1
    with open(os.path.join(log_dir, files[0]), "r") as f:
        content = f.read()
    assert "test message" in content
