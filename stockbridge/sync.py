# 同步引擎：通达信(TDX) ←→ 同花顺(THS) 板块双向同步
#
# 核心机制：
#   1. 内容指纹缓存：记录每次同步后两边各板块的内容指纹，
#      后续文件变动时先比对指纹，只有内容真正变化才触发同步，
#      避免了全量重同步和双向震荡（同步后立即更新缓存，watchdog
#      触发的后续事件发现内容未变→跳过）。
#   2. 拼音文件名分配：用 _assign_blk_names() 将 THS 中文板块名
#      转为 TDX .blk 拼音文件名，拼音碰撞时自动追加数字后缀。
#   3. 冲突策略：启动时以文件 mtime 为准（较新的覆盖较旧的），
#      运行中以实时变动为准。

import os
import time
from stockbridge import config
from stockbridge import converter


# === 全局缓存 ===

_debounce_cache = {}   # 防抖缓存: {文件路径小写: 上次事件时间戳}
_last_ths_blocks = {}  # THS板块内容缓存: {hex_id: frozenset("M:C"字符串)}
_last_tdx_blks = {}    # TDX板块内容缓存: {blk文件名: frozenset(行文本)}


def _stocks_fingerprint(stocks):
    """生成股票列表的内容指纹（顺序无关）。
    将每只股票序列化为 '市场码:代码' 字符串，组成不可变集合(frozenset)。"""
    return frozenset(f"{s['M']}:{s['C']}" for s in stocks)


def _assign_blk_names(ths_blocks):
    """为所有 THS 板块分配唯一的 TDX .blk 文件名。
    按中文名排序后逐个分配拼音首字母，碰撞时追加数字后缀。
    返回 {hex_id: blk_name}，结果确定可重复。"""
    # 按中文名排序确保确定性
    sorted_blocks = sorted(ths_blocks.items(), key=lambda x: x[1]["name"])
    taken = set()
    result = {}
    for hex_id, info in sorted_blocks:
        name = converter.name_to_pinyin(info["name"], taken)
        taken.add(name)
        result[hex_id] = name
    return result


# === 防抖 ===

def _debounce(path):
    """防抖检查：同一文件在 DEBOUNCE_MS 毫秒内的重复事件返回 True（应忽略）。"""
    now = time.time()
    path_lower = path.lower()
    if path_lower in _debounce_cache:
        if now - _debounce_cache[path_lower] < config.DEBOUNCE_MS / 1000.0:
            return True
    _debounce_cache[path_lower] = now
    return False


# === 文件名工具 ===

def _get_block_name_from_blk(path):
    """从 .blk 文件路径提取板块名（不含扩展名）。"""
    basename = os.path.basename(path)
    return os.path.splitext(basename)[0]  # "tjg.blk" -> "tjg"


def _find_ths_counterpart(tdx_blk_name, ths_blocks):
    """在 THS 板块列表中查找与 TDX .blk 文件名匹配的板块。
    通过 _assign_blk_names 计算 THS 各板块对应的拼音文件名，
    然后与给定的 tdx_blk_name 比对。返回匹配的 hex_id 或 None。
    正确处理了拼音碰撞场景（如三板→sb, 四板→sb2）。"""
    names = _assign_blk_names(ths_blocks)
    for hex_id, blk_name in names.items():
        if blk_name == tdx_blk_name:
            return hex_id
    return None


def _next_hex_id(blocks):
    """分配下一个可用的十六进制板块ID（当前最大ID+1）。"""
    max_id = 0
    for hex_id in blocks:
        try:
            val = int(hex_id, 16)
            if val > max_id:
                max_id = val
        except ValueError:
            pass
    return format(max_id + 1, "X")


# === 单项同步函数 ===

def _sync_blk_to_ths(tdx_blk_path, logger):
    """TDX .blk → THS stockblock.ini（或 SelfStockInfo.json）。
    读取 .blk 文件，转换格式后写入 THS 对应文件。
    如果是 zxg.blk 则同步到自选股，否则同步到自定义板块。
    同步后立即更新缓存以阻止反向同步死循环。"""
    blk_name = _get_block_name_from_blk(tdx_blk_path)
    tdx_lines = converter.read_blk(tdx_blk_path)
    entries = [converter.tdx_line_to_entry(line) for line in tdx_lines]
    # 立即更新 TDX 缓存，防止后续 watchdog 事件误触发
    _last_tdx_blks[blk_name] = frozenset(tdx_lines)

    is_selfstock = (blk_name == "zxg")

    if is_selfstock:
        # 自选股：TDX zxg.blk → THS SelfStockInfo.json
        old_entries = converter.read_selfstock(config.THS_SELFSTOCK_FILE)
        converter.write_selfstock(config.THS_SELFSTOCK_FILE, entries, old_entries)
        logger.info(
            f"TDX->THS 自选股 | 股票数:{len(tdx_lines)} | {tdx_blk_path} -> {config.THS_SELFSTOCK_FILE}"
        )
    else:
        # 自定义板块：TDX xxx.blk → THS stockblock.ini
        ths_blocks, raw = converter.read_stockblock_ini(config.THS_BLOCK_FILE)
        existing_id = _find_ths_counterpart(blk_name, ths_blocks)
        if existing_id:
            # 已有同名板块：更新股票列表
            ths_blocks[existing_id]["stocks"] = entries
        else:
            # 新板块：自动创建
            new_id = _next_hex_id(ths_blocks)
            ths_blocks[new_id] = {"name": blk_name, "stocks": entries}
        converter.write_stockblock_ini(config.THS_BLOCK_FILE, ths_blocks, raw)
        # 更新 THS 缓存以阻止反向同步死循环
        for hex_id, info in ths_blocks.items():
            _last_ths_blocks[hex_id] = _stocks_fingerprint(info["stocks"])
        logger.info(
            f"TDX->THS 板块:{blk_name} | 股票数:{len(tdx_lines)} | {tdx_blk_path} -> stockblock.ini"
        )


def _sync_ths_to_tdx(ths_block_hex_id, ths_blocks, logger):
    """THS stockblock.ini 板块 → TDX .blk 文件。
    将 THS 板块写为 TDX 三件套：
      1. <拼音>.blk        — 股票列表文件
      2. blocknew.cfg       — 板块注册表（lower字段=GBK中文名，upper=大写拼音）
      3. <拼音>.clr + .dat  — 显示名颜色 + 股票元数据
    同步后立即更新缓存以阻止反向同步死循环。"""
    info = ths_blocks[ths_block_hex_id]
    blk_names = _assign_blk_names(ths_blocks)
    blk_name = blk_names[ths_block_hex_id]
    tdx_path = os.path.join(config.TDX_BLOCK_DIR, f"{blk_name}.blk")

    # 1. 写 .blk 股票列表
    lines = [converter.entry_to_tdx_line(s) for s in info["stocks"]]
    converter.write_blk(tdx_path, lines)
    # 立即更新两边缓存，阻止 watchdog 检测到 .blk 写入后反向同步
    _last_tdx_blks[blk_name] = frozenset(lines)
    _last_ths_blocks[ths_block_hex_id] = _stocks_fingerprint(info["stocks"])

    # 2. 写 blocknew.cfg 板块注册表（lower=GBK中文名, upper=大写拼音）
    cfg_path = os.path.join(config.TDX_BLOCK_DIR, "blocknew.cfg")
    converter.write_blocknew_cfg(cfg_path, [(info["name"], blk_name.upper())])

    # 3. 写 blocknew.clr 中文显示名 + 颜色
    clr_path = os.path.join(config.TDX_BLOCK_DIR, "blocknew.clr")
    converter.write_blocknew_clr(clr_path, {info["name"]: 0})

    # 4. 写 <NAME>.dat 股票元数据
    stocks = []
    for s in info["stocks"]:
        try:
            mkt = converter.market_to_tdx(s["M"], s.get("C"))
        except KeyError:
            continue  # 未知市场码的股票跳过，不写入 .dat
        stocks.append((mkt, s["C"]))
    if stocks:
        dat_path = os.path.join(config.TDX_BLOCK_DIR, f"{blk_name.upper()}.dat")
        converter.write_block_dat(dat_path, stocks)

    logger.info(
        f"THS->TDX 板块:{info['name']} | 股票数:{len(lines)} | stockblock.ini -> {tdx_path}"
    )


def _sync_selfstock_to_tdx(logger):
    """THS SelfStockInfo.json → TDX zxg.blk（自选股单向同步）。"""
    entries = converter.read_selfstock(config.THS_SELFSTOCK_FILE)
    lines = [converter.entry_to_tdx_line(e) for e in entries]
    tdx_path = os.path.join(config.TDX_BLOCK_DIR, "zxg.blk")
    converter.write_blk(tdx_path, lines)
    # 更新缓存
    _last_tdx_blks["zxg"] = frozenset(lines)
    logger.info(
        f"THS->TDX 自选股 | 股票数:{len(lines)} | SelfStockInfo.json -> {tdx_path}"
    )


def _compare_and_sync_block(tdx_path, ths_hex_id, ths_blocks, logger):
    """比较 TDX .blk 和其对应的 THS 板块的 mtime，以较新的覆盖较旧的。
    仅在启动时的全量对齐(init_sync)中使用。"""
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


# === 启动全量对齐 ===

def init_sync(logger):
    """启动时执行一次全量扫描和对齐。
    流程：
      1. 扫描 TDX blocknew/ 下所有 .blk 文件
      2. 读取 THS stockblock.ini 和 SelfStockInfo.json
      3. 按拼音文件名 / 板块名匹配两边板块
      4. 逐板块比较 mtime 对齐
      5. 为只在一边存在的板块在另一边创建对应文件
      6. 初始化内容指纹缓存"""
    os.makedirs(config.TDX_BLOCK_DIR, exist_ok=True)
    os.makedirs(config.THS_USER_DIR, exist_ok=True)

    # 收集 TDX 所有 .blk 文件
    tdx_files = {}
    for f in os.listdir(config.TDX_BLOCK_DIR):
        if f.endswith(".blk"):
            name = os.path.splitext(f)[0]
            tdx_files[name] = os.path.join(config.TDX_BLOCK_DIR, f)

    ths_blocks, _ = converter.read_stockblock_ini(config.THS_BLOCK_FILE)

    # === 自选股对齐 ===
    tdx_zxg = tdx_files.pop("zxg", None)
    tdx_zxg_mtime = os.path.getmtime(tdx_zxg) if tdx_zxg and os.path.exists(tdx_zxg) else 0
    ths_selfstock_mtime = os.path.getmtime(config.THS_SELFSTOCK_FILE) if os.path.exists(config.THS_SELFSTOCK_FILE) else 0

    if tdx_zxg_mtime >= ths_selfstock_mtime:
        if tdx_zxg:
            _sync_blk_to_ths(tdx_zxg, logger)
    else:
        _sync_selfstock_to_tdx(logger)

    # === 自定义板块对齐 ===
    seen_ths_ids = set()

    for tdx_name, tdx_path in tdx_files.items():
        match_id = _find_ths_counterpart(tdx_name, ths_blocks)
        if match_id:
            # 两边都有：以 mtime 为准
            seen_ths_ids.add(match_id)
            _compare_and_sync_block(tdx_path, match_id, ths_blocks, logger)
        else:
            # 仅 TDX 有 → 同步到 THS
            _sync_blk_to_ths(tdx_path, logger)

    # 仅 THS 有的板块 → 在 TDX 创建对应文件（三件套）
    blk_names = _assign_blk_names(ths_blocks)
    for hex_id, info in ths_blocks.items():
        if hex_id not in seen_ths_ids:
            blk_name = blk_names[hex_id]
            tdx_path = os.path.join(config.TDX_BLOCK_DIR, f"{blk_name}.blk")
            if not os.path.exists(tdx_path):
                _sync_ths_to_tdx(hex_id, ths_blocks, logger)

    # === 初始化内容指纹缓存 ===
    # 对齐完成后记录所有板块的当前内容，作为后续增量同步的基准
    ths_blocks, _ = converter.read_stockblock_ini(config.THS_BLOCK_FILE)
    for hex_id, info in ths_blocks.items():
        _last_ths_blocks[hex_id] = _stocks_fingerprint(info["stocks"])
    for f in os.listdir(config.TDX_BLOCK_DIR):
        if f.endswith(".blk"):
            name = os.path.splitext(f)[0]
            path = os.path.join(config.TDX_BLOCK_DIR, f)
            _last_tdx_blks[name] = frozenset(converter.read_blk(path))

    logger.info("init_sync 完成")


# === 运行中文件变动处理 ===

def on_file_changed(path, logger):
    """watchdog 文件变动事件的统一处理入口。
    先防抖，再按文件类型分发处理：
      .blk                 → 内容指纹对比后 TDX→THS 同步
      SelfStockInfo.json    → THS→TDX 自选股同步
      stockblock.ini        → 逐板块内容指纹对比后 THS→TDX 同步
    内容指纹缓存机制：只有内容真正变化的板块才触发同步，
    阻止了全量重同步和双向震荡。"""
    if _debounce(path):
        return

    path_lower = path.lower()
    logger.info(f"检测到文件变动: {path}")

    if path_lower.endswith(".blk"):
        # TDX 板块文件变动
        blk_name = _get_block_name_from_blk(path)
        lines = converter.read_blk(path)
        new_fp = frozenset(lines)
        # 内容指纹对比：与缓存不同才同步（阻止震荡）
        if _last_tdx_blks.get(blk_name) != new_fp:
            _sync_blk_to_ths(path, logger)

    elif path_lower.endswith("selfstockinfo.json"):
        # THS 自选股变动
        _sync_selfstock_to_tdx(logger)

    elif path_lower.endswith("stockblock.ini"):
        # THS 自定义板块变动：逐板块检查内容变化
        ths_blocks, _ = converter.read_stockblock_ini(config.THS_BLOCK_FILE)
        for hex_id, info in ths_blocks.items():
            new_fp = _stocks_fingerprint(info["stocks"])
            # 只同步内容变化的板块（不是全量！）
            if _last_ths_blocks.get(hex_id) != new_fp:
                _sync_ths_to_tdx(hex_id, ths_blocks, logger)
