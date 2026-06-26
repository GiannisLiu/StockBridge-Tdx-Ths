import sys
import time
from stockbridge import config
from stockbridge.logger import setup_logging
from stockbridge.sync import init_sync
from stockbridge.watcher import start_watching


def main():
    logger = setup_logging(config.LOG_DIR)
    logger.info("StockBridge 启动")

    try:
        init_sync(logger)
    except Exception as e:
        logger.error(f"初始化同步失败: {e}")
        sys.exit(1)

    observer = start_watching(logger)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在退出...")
        observer.stop()
    observer.join()
    logger.info("StockBridge 已退出")


if __name__ == "__main__":
    main()
