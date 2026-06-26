import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from stockbridge import config
from stockbridge.sync import on_file_changed


class BlockEventHandler(FileSystemEventHandler):
    def __init__(self, logger):
        self.logger = logger

    def on_modified(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

    def _handle(self, path):
        basename = os.path.basename(path).lower()
        if basename.endswith(".blk") or basename in ("selfstockinfo.json", "stockblock.ini"):
            on_file_changed(path, self.logger)


def start_watching(logger):
    observer = Observer()

    if os.path.isdir(config.TDX_BLOCK_DIR):
        observer.schedule(
            BlockEventHandler(logger),
            config.TDX_BLOCK_DIR,
            recursive=False
        )
        logger.info(f"监控 TDX: {config.TDX_BLOCK_DIR}")
    else:
        logger.warning(f"TDX 目录不存在: {config.TDX_BLOCK_DIR}")

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
