import logging
import os
from datetime import datetime


def setup_logging(log_dir):
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger("stockbridge")
    logger.setLevel(logging.INFO)

    date_str = datetime.now().strftime("%Y%m%d")
    log_file = os.path.join(log_dir, f"sync_{date_str}.log")

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    fh.setFormatter(fmt)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger
