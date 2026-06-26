# 测试：logger 模块的日志初始化和文件输出
import os
import tempfile
from stockbridge.logger import setup_logging


def test_setup_logging_returns_logger():
    """验证 setup_logging 返回有效的 logger 实例，级别为 INFO"""
    log_dir = tempfile.mkdtemp()
    logger = setup_logging(log_dir)
    assert logger is not None
    assert logger.level == 20  # INFO = 20


def test_setup_logging_creates_log_file():
    """验证日志消息被正确写入到按日期命名的日志文件中"""
    log_dir = tempfile.mkdtemp()
    logger = setup_logging(log_dir)
    logger.info("test message")
    files = os.listdir(log_dir)
    assert len(files) == 1
    with open(os.path.join(log_dir, files[0]), "r") as f:
        content = f.read()
    assert "test message" in content
