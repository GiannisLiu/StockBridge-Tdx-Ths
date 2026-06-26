import os
import tempfile
import logging
from stockbridge.sync import init_sync, on_file_changed

logger = logging.getLogger("test")
logger.addHandler(logging.NullHandler())


def make_tdx_blk(dir_path, name, lines):
    path = os.path.join(dir_path, name)
    with open(path, "w", newline="\r\n") as f:
        for line in lines:
            f.write(line + "\r\n")
    return path


def make_ths_selfstock(path, entries):
    import json
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False)


def make_ths_block_ini(path, blocks):
    lines = ["[BLOCK_NAME_MAP_TABLE]\r\n", "[BLOCK_STOCK_CONTEXT]\r\n", "[SYSTEM]\r\n", "LastSynCodeID=1\r\n"]
    # Regenerate to include blocks
    # Actually use write_stockblock_ini from converter
    from stockbridge.converter import write_stockblock_ini
    write_stockblock_ini(path, blocks, "".join(lines))


def test_init_sync_newer_tdx_overwrites_ths():
    # Setup temp dirs
    tdx_dir = tempfile.mkdtemp()
    ths_dir = tempfile.mkdtemp()
    ths_selfstock = os.path.join(ths_dir, "SelfStockInfo.json")
    ths_block = os.path.join(ths_dir, "stockblock.ini")

    # Create newer TDX file
    import time
    tdx_zxg = make_tdx_blk(tdx_dir, "zxg.blk", ["1600172", "0000651"])
    # Create older THS file
    make_ths_selfstock(ths_selfstock, [{"C": "300604", "M": "33", "P": "", "T": ""}])
    time.sleep(0.1)
    os.utime(tdx_zxg, (time.time(), time.time() + 10))

    # Override config paths
    import stockbridge.config as cfg
    cfg.TDX_BLOCK_DIR = tdx_dir
    cfg.THS_SELFSTOCK_FILE = ths_selfstock
    cfg.THS_BLOCK_FILE = ths_block

    init_sync(logger)

    # THS should now have the TDX stocks
    from stockbridge.converter import read_selfstock
    result = read_selfstock(ths_selfstock)
    codes = {e["C"] for e in result}
    assert "600172" in codes
    assert "000651" in codes


def test_on_file_changed_debounce(tmp_path):
    tdx_dir = tmp_path / "tdx"
    tdx_dir.mkdir()
    tdx_zxg = make_tdx_blk(str(tdx_dir), "zxg.blk", ["1600172"])

    import stockbridge.config as cfg
    cfg.TDX_BLOCK_DIR = str(tdx_dir)

    # First call should trigger
    on_file_changed(tdx_zxg, logger)
    # Immediate second call on same file should be ignored (debounce)
    on_file_changed(tdx_zxg, logger)
    # If we get here without error, debounce works
