# 程序入口：启动时先做全量对齐，然后进入文件监控模式
import sys
import time
from stockbridge import config
from stockbridge.logger import setup_logging
from stockbridge.sync import init_sync
from stockbridge.watcher import start_watching


def main():
    """主函数：初始化日志 → 全量对齐 → 启动文件监控 → 保持运行。
    按 Ctrl+C 可安全退出，停止监控并清理资源。"""
    logger = setup_logging(config.LOG_DIR)
    logger.info("StockBridge 启动")

    # 第一步：全量对齐两边所有板块
    try:
        init_sync(logger)
    except Exception as e:
        logger.error(f"初始化同步失败: {e}")
        sys.exit(1)

    # 第二步：启动 watchdog 文件监控
    observer = start_watching(logger)

    # 第三步：主循环，保持进程运行直到收到中断信号
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
