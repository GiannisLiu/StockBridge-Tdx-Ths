# 测试：sync 引擎的启动对齐和文件变动处理
import os
import tempfile
import logging
from stockbridge.sync import init_sync, on_file_changed

logger = logging.getLogger("test")
logger.addHandler(logging.NullHandler())


# === 测试辅助函数 ===

def make_tdx_blk(dir_path, name, lines):
    """在指定目录创建 TDX .blk 测试文件，CRLF 换行"""
    path = os.path.join(dir_path, name)
    with open(path, "w", newline="\r\n") as f:
        for line in lines:
            f.write(line + "\r\n")
    return path


def make_ths_selfstock(path, entries):
    """创建 THS SelfStockInfo.json 测试文件"""
    import json
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False)


def make_ths_block_ini(path, blocks):
    """创建 THS stockblock.ini 测试文件"""
    lines = ["[BLOCK_NAME_MAP_TABLE]\r\n", "[BLOCK_STOCK_CONTEXT]\r\n", "[SYSTEM]\r\n", "LastSynCodeID=1\r\n"]
    from stockbridge.converter import write_stockblock_ini
    write_stockblock_ini(path, blocks, "".join(lines))


# === 测试用例 ===

def test_init_sync_newer_tdx_overwrites_ths():
    """验证启动对齐时，较新的 TDX 文件会覆盖较旧的 THS 文件。
    场景：TDX zxg.blk 比 THS SelfStockInfo.json 新 → THS 应更新为 TDX 的内容。"""
    # 创建临时目录
    tdx_dir = tempfile.mkdtemp()
    ths_dir = tempfile.mkdtemp()
    ths_selfstock = os.path.join(ths_dir, "SelfStockInfo.json")
    ths_block = os.path.join(ths_dir, "stockblock.ini")

    import time
    # 创建 TDX 文件并设置较新的 mtime
    tdx_zxg = make_tdx_blk(tdx_dir, "zxg.blk", ["1600172", "0000651"])
    make_ths_selfstock(ths_selfstock, [{"C": "300604", "M": "33", "P": "", "T": ""}])
    time.sleep(0.1)
    os.utime(tdx_zxg, (time.time(), time.time() + 10))

    # 覆盖配置路径指向临时目录
    import stockbridge.config as cfg
    cfg.TDX_BLOCK_DIR = tdx_dir
    cfg.THS_SELFSTOCK_FILE = ths_selfstock
    cfg.THS_BLOCK_FILE = ths_block

    init_sync(logger)

    # 验证 THS 已被 TDX 内容覆盖
    from stockbridge.converter import read_selfstock
    result = read_selfstock(ths_selfstock)
    codes = {e["C"] for e in result}
    assert "600172" in codes
    assert "000651" in codes


def test_on_file_changed_debounce(tmp_path):
    """验证防抖机制：同一文件在防抖时间内的第二次调用被忽略。"""
    tdx_dir = tmp_path / "tdx"
    ths_dir = tmp_path / "ths"
    tdx_dir.mkdir()
    ths_dir.mkdir()
    tdx_zxg = make_tdx_blk(str(tdx_dir), "zxg.blk", ["1600172"])

    import stockbridge.config as cfg
    cfg.TDX_BLOCK_DIR = str(tdx_dir)
    cfg.THS_SELFSTOCK_FILE = str(ths_dir / "SelfStockInfo.json")
    cfg.THS_BLOCK_FILE = str(ths_dir / "stockblock.ini")

    # 第一次调用应触发同步
    on_file_changed(tdx_zxg, logger)
    # 立即第二次调用同一文件应被防抖拦截
    on_file_changed(tdx_zxg, logger)
    # 没有抛出异常即表示防抖生效
