# 文件监控模块：使用 watchdog 监控通达信和同花顺的板块文件变动
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from stockbridge import config
from stockbridge.sync import on_file_changed


class BlockEventHandler(FileSystemEventHandler):
    """文件系统事件处理器：当 .blk / stockblock.ini / SelfStockInfo.json
    发生变动时，调用 sync 引擎的处理入口。"""

    def __init__(self, logger):
        self.logger = logger

    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle(event.src_path)

    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle(event.src_path)

    def _handle(self, path):
        """过滤文件类型：只处理 .blk（板块）、stockblock.ini（自定义板块）
        和 SelfStockInfo.json（自选股）的变动。"""
        basename = os.path.basename(path).lower()
        if basename.endswith(".blk") or basename in ("selfstockinfo.json", "stockblock.ini"):
            on_file_changed(path, self.logger)


def start_watching(logger):
    """启动文件监控，同时监控 TDX 板块目录和 THS 用户目录。
    只监控目录本身（不递归），返回 Observer 实例。"""
    observer = Observer()

    # 监控通达信板块目录（blocknew/）
    if os.path.isdir(config.TDX_BLOCK_DIR):
        observer.schedule(
            BlockEventHandler(logger),
            config.TDX_BLOCK_DIR,
            recursive=False
        )
        logger.info(f"监控 TDX: {config.TDX_BLOCK_DIR}")
    else:
        logger.warning(f"TDX 目录不存在: {config.TDX_BLOCK_DIR}")

    # 监控同花顺用户目录
    if os.path.isdir(config.THS_USER_DIR):
        observer.schedule(
            BlockEventHandler(logger),
            config.THS_USER_DIR,
            recursive=False
        )
        logger.info(f"监控 THS: {config.THS_USER_DIR}")
    else:
        logger.warning(f"THS 目录不存在: {config.THS_USER_DIR}")

    observer.start()
    logger.info("文件监控已启动")
    return observer
