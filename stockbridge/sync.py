import os
import time
from stockbridge import config
from stockbridge import converter


_debounce_cache = {}  # {path: last_event_timestamp}


def _debounce(path):
    now = time.time()
    path_lower = path.lower()
    if path_lower in _debounce_cache:
        if now - _debounce_cache[path_lower] < config.DEBOUNCE_MS / 1000.0:
            return True
    _debounce_cache[path_lower] = now
    return False


def _get_block_name_from_blk(path):
    basename = os.path.basename(path)
    return os.path.splitext(basename)[0]  # "tjg.blk" -> "tjg"


def _find_ths_counterpart(tdx_blk_name, ths_blocks):
    """Find the THS hex_id matching a TDX block name by pinyin."""
    for hex_id, info in ths_blocks.items():
        ths_pinyin = converter.name_to_pinyin(info["name"])
        if ths_pinyin == tdx_blk_name:
            return hex_id
    return None


def _sync_blk_to_ths(tdx_blk_path, logger):
    """Sync a TDX .blk file to THS stockblock.ini (or SelfStockInfo.json)."""
    blk_name = _get_block_name_from_blk(tdx_blk_path)
    tdx_lines = converter.read_blk(tdx_blk_path)
    entries = [converter.tdx_line_to_entry(line) for line in tdx_lines]

    is_selfstock = (blk_name == "zxg")

    if is_selfstock:
        old_entries = converter.read_selfstock(config.THS_SELFSTOCK_FILE)
        converter.write_selfstock(config.THS_SELFSTOCK_FILE, entries, old_entries)
        logger.info(
            f"TDX->THS 自选股 | 股票数:{len(tdx_lines)} | {tdx_blk_path} -> {config.THS_SELFSTOCK_FILE}"
        )
    else:
        ths_blocks, raw = converter.read_stockblock_ini(config.THS_BLOCK_FILE)
        existing_id = _find_ths_counterpart(blk_name, ths_blocks)
        if existing_id:
            ths_blocks[existing_id]["stocks"] = entries
        else:
            new_id = _next_hex_id(ths_blocks)
            ths_blocks[new_id] = {"name": blk_name, "stocks": entries}
        converter.write_stockblock_ini(config.THS_BLOCK_FILE, ths_blocks, raw)
        logger.info(
            f"TDX->THS 板块:{blk_name} | 股票数:{len(tdx_lines)} | {tdx_blk_path} -> stockblock.ini"
        )


def _next_hex_id(blocks):
    max_id = 0
    for hex_id in blocks:
        try:
            val = int(hex_id, 16)
            if val > max_id:
                max_id = val
        except ValueError:
            pass
    return format(max_id + 1, "X")


def _sync_ths_to_tdx(ths_block_hex_id, ths_blocks, logger):
    """Sync a THS custom block to a TDX .blk file."""
    info = ths_blocks[ths_block_hex_id]
    blk_name = converter.name_to_pinyin(info["name"])
    tdx_path = os.path.join(config.TDX_BLOCK_DIR, f"{blk_name}.blk")

    lines = [converter.entry_to_tdx_line(s) for s in info["stocks"]]
    converter.write_blk(tdx_path, lines)
    logger.info(
        f"THS->TDX 板块:{info['name']} | 股票数:{len(lines)} | stockblock.ini -> {tdx_path}"
    )


def _sync_selfstock_to_tdx(logger):
    """Sync THS SelfStockInfo.json to TDX zxg.blk."""
    entries = converter.read_selfstock(config.THS_SELFSTOCK_FILE)
    lines = [converter.entry_to_tdx_line(e) for e in entries]
    tdx_path = os.path.join(config.TDX_BLOCK_DIR, "zxg.blk")
    converter.write_blk(tdx_path, lines)
    logger.info(
        f"THS->TDX 自选股 | 股票数:{len(lines)} | SelfStockInfo.json -> {tdx_path}"
    )


def _compare_and_sync_block(tdx_path, ths_hex_id, ths_blocks, logger):
    """Compare mtime of a TDX blk and its THS counterpart, sync the newer one."""
    ths_path = config.THS_BLOCK_FILE
    tdx_mtime = os.path.getmtime(tdx_path) if os.path.exists(tdx_path) else 0
    ths_mtime = os.path.getmtime(ths_path) if os.path.exists(ths_path) else 0

    if not os.path.exists(tdx_path):
        ths_info = ths_blocks.get(ths_hex_id)
        if ths_info and ths_info["stocks"]:
            _sync_ths_to_tdx(ths_hex_id, ths_blocks, logger)
        return

    if tdx_mtime >= ths_mtime:
        _sync_blk_to_ths(tdx_path, logger)
    else:
        _sync_ths_to_tdx(ths_hex_id, ths_blocks, logger)


def init_sync(logger):
    """Full alignment on startup."""
    os.makedirs(config.TDX_BLOCK_DIR, exist_ok=True)
    os.makedirs(config.THS_USER_DIR, exist_ok=True)

    tdx_files = {}
    for f in os.listdir(config.TDX_BLOCK_DIR):
        if f.endswith(".blk"):
            name = os.path.splitext(f)[0]
            tdx_files[name] = os.path.join(config.TDX_BLOCK_DIR, f)

    ths_blocks, _ = converter.read_stockblock_ini(config.THS_BLOCK_FILE)

    # Sync selfstock
    tdx_zxg = tdx_files.pop("zxg", None)
    tdx_zxg_mtime = os.path.getmtime(tdx_zxg) if tdx_zxg and os.path.exists(tdx_zxg) else 0
    ths_selfstock_mtime = os.path.getmtime(config.THS_SELFSTOCK_FILE) if os.path.exists(config.THS_SELFSTOCK_FILE) else 0

    if tdx_zxg_mtime >= ths_selfstock_mtime:
        if tdx_zxg:
            _sync_blk_to_ths(tdx_zxg, logger)
    else:
        _sync_selfstock_to_tdx(logger)

    # Sync custom blocks
    seen_ths_ids = set()
    unmatched_ths = {}

    for tdx_name, tdx_path in tdx_files.items():
        match_id = _find_ths_counterpart(tdx_name, ths_blocks)
        if match_id:
            seen_ths_ids.add(match_id)
            _compare_and_sync_block(tdx_path, match_id, ths_blocks, logger)
        else:
            _sync_blk_to_ths(tdx_path, logger)

    # THS-only blocks: create corresponding TDX files
    for hex_id, info in ths_blocks.items():
        if hex_id not in seen_ths_ids:
            blk_name = converter.name_to_pinyin(info["name"])
            tdx_path = os.path.join(config.TDX_BLOCK_DIR, f"{blk_name}.blk")
            if not os.path.exists(tdx_path):
                _sync_ths_to_tdx(hex_id, ths_blocks, logger)

    logger.info("init_sync 完成")


def on_file_changed(path, logger):
    """Handle a watchdog file change event."""
    if _debounce(path):
        return

    path_lower = path.lower()
    logger.info(f"检测到文件变动: {path}")

    if path_lower.endswith(".blk"):
        _sync_blk_to_ths(path, logger)
    elif path_lower.endswith("selfstockinfo.json"):
        _sync_selfstock_to_tdx(logger)
    elif path_lower.endswith("stockblock.ini"):
        ths_blocks, _ = converter.read_stockblock_ini(config.THS_BLOCK_FILE)
        tdx_mtime_map = {}
        for f in os.listdir(config.TDX_BLOCK_DIR):
            if f.endswith(".blk"):
                full = os.path.join(config.TDX_BLOCK_DIR, f)
                tdx_mtime_map[os.path.splitext(f)[0]] = os.path.getmtime(full)
        for hex_id, info in ths_blocks.items():
            blk_name = converter.name_to_pinyin(info["name"])
            tdx_mtime = tdx_mtime_map.get(blk_name, 0)
            ths_mtime = os.path.getmtime(config.THS_BLOCK_FILE)
            if ths_mtime > tdx_mtime:
                _sync_ths_to_tdx(hex_id, ths_blocks, logger)
