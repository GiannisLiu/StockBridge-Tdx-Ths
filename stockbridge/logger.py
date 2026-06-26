# 日志模块：按日期滚动日志文件，同时输出到控制台
import logging
import os
from datetime import datetime


def setup_logging(log_dir):
    """初始化日志系统，返回配置好的 logger 实例。
    日志文件按日期命名：sync_YYYYMMDD.log，存放在 log_dir 目录下。
    同时输出到文件（UTF-8编码）和控制台。"""
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger("stockbridge")
    logger.setLevel(logging.INFO)

    # 按日期生成日志文件名
    date_str = datetime.now().strftime("%Y%m%d")
    log_file = os.path.join(log_dir, f"sync_{date_str}.log")

    # 文件处理器：写入日志文件
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.INFO)
    # 控制台处理器：输出到终端
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    # 统一日志格式：[时间] [级别] 消息内容
    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    fh.setFormatter(fmt)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger
