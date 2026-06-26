# 格式转换模块：通达信(TDX)与同花顺(THS)之间的市场码、股票条目、板块文件互转
#
# 支持的 TDX 文件格式：
#   .blk         — 文本格式，每行一个股票（市场前缀+代码），CRLF换行
#   blocknew.cfg — 120字节/板块的二进制注册表，lower字段存GBK中文名，upper字段存ASCII大写拼音
#   <NAME>.dat   — 80字节/股票的二进制元数据文件
#   blocknew.clr — 80字节/板块的颜色与显示名文件
#
# 支持的 THS 文件格式：
#   SelfStockInfo.json — UTF-8 JSON数组，自选股
#   stockblock.ini     — GBK INI格式，自定义板块

import json
import os
import re
from pypinyin import pinyin, Style

# === 市场码映射 ===
# TDX 用单字符前缀：0=深圳, 1=上海, 2=北交所
# THS 用数字：33=深圳, 17=上海, 120=北交所, 16=深圳创业板, 20=深圳中小板
_MARKET_TDX_TO_THS = {"0": "33", "1": "17", "2": "120"}
_MARKET_THS_TO_TDX = {"33": "0", "17": "1", "120": "2", "16": "1", "20": "1"}


def _infer_tdx_prefix(code):
    """当THS市场码未知时，根据股票代码推断TDX市场前缀。
    规则：6开头=上海主板, 688=科创板(上海), 5/7开头=上海,
          0/1/2/3开头=深圳, 8/9开头=北交所"""
    if len(code) == 6 and code.isdigit():
        first = code[0]
        if first in ("6", "5", "7"):  # 上海主板/ETF
            return "1"
        elif code.startswith("688"):  # 上海科创板
            return "1"
        elif first in ("0", "1", "2", "3"):  # 深圳主板/中小板/创业板/ETF
            return "0"
        elif first in ("8", "9"):  # 北交所(8xxx) / 北交所(9xxx)
            return "2"
    return None


# === 市场码互转 ===

def market_to_tdx(ths_market, code=None):
    """THS市场码 → TDX市场前缀。
    优先查映射表，查不到则通过股票代码推断，还不行则抛出KeyError。"""
    if ths_market in _MARKET_THS_TO_TDX:
        return _MARKET_THS_TO_TDX[ths_market]
    if code:
        prefix = _infer_tdx_prefix(code)
        if prefix is not None:
            return prefix
    raise KeyError(f"Unknown market code '{ths_market}'")


def market_to_ths(tdx_prefix):
    """TDX市场前缀 → THS市场码"""
    return _MARKET_TDX_TO_THS[tdx_prefix]


# === 单据条目互转 ===

def tdx_line_to_entry(line):
    """TDX单行文本 → THS条目字典。
    TDX格式: '1600172' → {'C':'600172', 'M':'17', 'P':'', 'T':''}
    首位为市场前缀，后6位为股票代码。"""
    line = line.strip()
    prefix = line[0]
    code = line[1:]
    return {"C": code, "M": market_to_ths(prefix), "P": "", "T": ""}


def entry_to_tdx_line(entry):
    """THS条目字典 → TDX单行文本。
    已知市场码则拼接前缀+代码，未知则返回纯代码作为后备。"""
    try:
        prefix = market_to_tdx(entry["M"], entry.get("C"))
        return f"{prefix}{entry['C']}"
    except KeyError:
        return entry["C"]


# === TDX 二进制文件常量 ===

_BLOCKNEW_CFG_SIZE = 120   # blocknew.cfg 每条板块记录120字节
_DAT_RECORD_SIZE = 0x50    # <NAME>.dat 每只股票记录80字节

# .dat 文件的最小有效记录模板（80字节），基于通达信原生格式。
# 只有 flag(0x00) 和 code(0x02) 两处会覆盖写入，其余字段保持模板值。
_DAT_TEMPLATE = bytes([
    0x00, 0x00,                                                                     # 0x00: 市场标志（将被覆盖）
    0x30, 0x30, 0x30, 0x30, 0x30, 0x30, 0x30,                                      # 0x02: 代码占位（将被覆盖）
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,                                # 0x09
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,                                # 0x11
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,                                      # 0x19 (7 bytes)
    0x00,                                                                           # 0x20
    0x12, 0x27, 0x35, 0x01, 0xf6, 0x28, 0x6c, 0x40,                                # 0x21 行情数据
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,                                      # 0x29
    0x00, 0x00, 0x00, 0x00, 0x00,                                                  # 0x30
    0xd0, 0x02, 0x00, 0x00,                                                        # 0x35
    0xec, 0xc8, 0x00, 0x00,                                                        # 0x39
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,                                # 0x3D
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,                                # 0x45
    0x00, 0x00,                                                                     # 0x4D
    0x01,                                                                           # 0x4F: 记录有效标志
])


def _make_dat_record(market_tdx, code):
    """构建单只股票的80字节 .dat 记录。
    market_tdx: TDX市场前缀字符串（如 '0', '1'）
    code: 6位股票代码字符串（如 '600172'）"""
    rec = bytearray(_DAT_TEMPLATE)
    # 0x00-0x01: 市场标志（小端序）
    rec[0:2] = int(market_tdx).to_bytes(2, "little")
    code_bytes = code.encode("ascii")
    # 0x02-0x08: 7字节代码字段，先全部清零再写入6位代码
    rec[2:9] = b"\x00" * 7
    rec[2:2 + len(code_bytes)] = code_bytes
    return bytes(rec)


# === TDX .blk 文件读写 ===

def read_blk(path):
    """读取 TDX .blk 文件，返回每行的股票字符串列表（已去空白行）。"""
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return [line.strip() for line in f if line.strip()]


def write_blk(path, lines):
    """写入 TDX .blk 文件。自动创建父目录，CRLF 换行。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="\r\n") as f:
        for line in lines:
            f.write(line + "\n")


# === THS 自选股 JSON 读写 ===

def read_selfstock(path):
    """读取同花顺 SelfStockInfo.json，返回条目列表。"""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_selfstock(path, entries, old_entries=None):
    """写入同花顺 SelfStockInfo.json。
    如果提供了旧条目列表，则保留旧条目的行情字段（P=现价, T=更新日期），
    仅更新市场码和代码字段，避免覆盖同花顺维护的行情数据。"""
    # 构建旧条目的代码→行情字段映射
    old_map = {}
    if old_entries:
        for e in old_entries:
            old_map[e["C"]] = e
    # 合并：新条目的代码+市场码 + 旧条目的行情字段
    merged = []
    for e in entries:
        if e["C"] in old_map:
            old = old_map[e["C"]]
            merged.append({
                "C": e["C"], "M": e["M"],
                "P": old.get("P", ""), "T": old.get("T", "")
            })
        else:
            merged.append(e)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False)


# === 拼音转换 ===

def name_to_pinyin(name, taken=None):
    """中文板块名 → 拼音首字母（用于生成 TDX 文件名）。
    taken 参数为已占用的名称集合，碰撞时追加数字后缀（如 sb, sb2, sb3）。"""
    result = pinyin(name, style=Style.FIRST_LETTER)
    base = "".join([p[0] for p in result])
    if taken is None or base not in taken:
        return base
    # 拼音碰撞：依次尝试 base2, base3, ...
    i = 2
    while f"{base}{i}" in taken:
        i += 1
    return f"{base}{i}"


# === INI 文件解析（通用） ===

def _parse_ini_sections(content):
    """将 INI 文件内容按节(section)切分，返回 {节名: 原始文本} 字典。
    保留节内的原始格式（含换行），用于写回时保持其他节不变。"""
    sections = {}
    current_section = None
    current_lines = []
    for line in content.splitlines(keepends=True):
        m = re.match(r"^\[(.+)\]", line)
        if m:
            if current_section is not None:
                sections[current_section] = "".join(current_lines)
            current_section = m.group(1)
            current_lines = [line]
        else:
            current_lines.append(line)
    if current_section is not None:
        sections[current_section] = "".join(current_lines)
    return sections


# === THS stockblock.ini 读写 ===

def read_stockblock_ini(path):
    """读取同花顺 stockblock.ini，解析板块名称和股票列表。
    返回:
      blocks: {hex_id: {"name": str, "stocks": [{"M": str, "C": str}, ...]}, ...}
      raw: 原始文件内容字符串（用于写回时保留其他节）"""
    blocks = {}
    if not os.path.exists(path):
        return blocks, ""
    with open(path, "r", encoding="gbk") as f:
        raw = f.read()
    sections = _parse_ini_sections(raw)

    # 解析板块名称表 [BLOCK_NAME_MAP_TABLE]
    name_section = sections.get("BLOCK_NAME_MAP_TABLE", "")
    name_map = {}
    for line in name_section.splitlines():
        m = re.match(r"^([0-9A-Fa-f]+)=(.*)", line)
        if m:
            name_map[m.group(1)] = m.group(2)

    # 解析板块股票列表 [BLOCK_STOCK_CONTEXT]
    stock_section = sections.get("BLOCK_STOCK_CONTEXT", "")
    stock_map = {}
    for line in stock_section.splitlines():
        m = re.match(r"^([0-9A-Fa-f]+)=(.*)", line)
        if m:
            stock_map[m.group(1)] = m.group(2)

    # 组装板块数据：hex_id → {name, stocks}
    for hex_id, name in name_map.items():
        stocks = []
        if hex_id in stock_map:
            for item in stock_map[hex_id].split(","):
                item = item.strip()
                if ":" in item:
                    mkt, code = item.split(":", 1)
                    stocks.append({"M": mkt, "C": code})
        blocks[hex_id] = {"name": name, "stocks": stocks}

    return blocks, raw


def write_stockblock_ini(path, blocks, raw_content):
    """写入同花顺 stockblock.ini。
    保留原始文件中的其他节（如 [SYSTEM]、[@7] 等），只更新板块相关节。
    blocks 格式与 read_stockblock_ini 返回值一致。"""
    sections = _parse_ini_sections(raw_content)

    name_lines = []
    stock_lines = []
    known_ids = set(blocks.keys())

    # 生成当前板块的名称行和股票行
    for hex_id in sorted(blocks.keys()):
        name_lines.append(f"{hex_id}={blocks[hex_id]['name']}")
        stocks_str = ",".join(
            f"{s['M']}:{s['C']}" for s in blocks[hex_id]["stocks"]
        ) + ","
        stock_lines.append(f"{hex_id}={stocks_str}")

    # 保留不在当前板块列表中的旧条目（同花顺系统板块等）
    old_name_section = sections.get("BLOCK_NAME_MAP_TABLE", "")
    for line in old_name_section.splitlines():
        m = re.match(r"^([0-9A-Fa-f]+)=", line)
        if m and m.group(1) not in known_ids:
            name_lines.append(m.group(1) + "=" + line.split("=", 1)[1])

    old_stock_section = sections.get("BLOCK_STOCK_CONTEXT", "")
    for line in old_stock_section.splitlines():
        m = re.match(r"^([0-9A-Fa-f]+)=", line)
        if m and m.group(1) not in known_ids:
            stock_lines.append(m.group(1) + "=" + line.split("=", 1)[1])

    # 更新节内容（CRLF 换行以匹配 THS 格式）
    sections["BLOCK_NAME_MAP_TABLE"] = "[BLOCK_NAME_MAP_TABLE]\r\n" + "\r\n".join(name_lines) + "\r\n"
    sections["BLOCK_STOCK_CONTEXT"] = "[BLOCK_STOCK_CONTEXT]\r\n" + "\r\n".join(stock_lines) + "\r\n"

    output = "".join(sections.values())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="gbk") as f:
        f.write(output)


# === TDX blocknew.cfg 读写（板块注册表） ===

def read_blocknew_cfg(path):
    """读取 TDX blocknew.cfg，返回 [(lower_name, upper_name), ...] 列表。
    lower_name 通常为 GBK 编码的中文板块名，upper_name 为大写拼音首字母。
    文件不存在时返回空列表。"""
    if not os.path.exists(path):
        return []
    with open(path, "rb") as f:
        data = f.read()
    entries = []
    for offset in range(0, len(data), _BLOCKNEW_CFG_SIZE):
        chunk = data[offset:offset + _BLOCKNEW_CFG_SIZE]
        if len(chunk) < 8:
            continue
        # 0x00-0x07: lower name（GBK中文名或拼音）
        lower_raw = chunk[0:8].rstrip(b"\x00")
        if not lower_raw:
            continue
        lower = lower_raw.decode("gbk", errors="replace")
        if not lower:
            continue
        # 0x30-0x38: 前2字节为标志位，后6字节为 upper name（ASCII大写拼音）
        upper_raw = chunk[0x30:0x38]
        upper = upper_raw.lstrip(b"\x00").rstrip(b"\x00").decode("ascii", errors="ignore")
        if not upper:
            upper = lower.upper()
        entries.append((lower, upper))
    return entries


def write_blocknew_cfg(path, entries):
    """写入 TDX blocknew.cfg。与已有条目合并去重，以 lower_name 为键。
    entries 格式: [(lower_name, upper_name), ...]
    lower_name 可以是中文（GBK编码）或拼音，upper_name 必须是ASCII。"""
    existing = read_blocknew_cfg(path)
    merged = {}
    for lower, upper in existing:
        merged[lower] = upper
    for lower, upper in entries:
        merged[lower] = upper

    data = bytearray()
    for lower, upper in merged.items():
        entry = bytearray(_BLOCKNEW_CFG_SIZE)
        # 0x00-0x07: lower name，GBK编码（中文最多4个字，拼音最多8个字母）
        lower_bytes = lower.encode("gbk")[:8]
        upper_bytes = upper.encode("ascii")[:6]
        entry[0:len(lower_bytes)] = lower_bytes
        # 0x32-0x37: upper name，ASCII编码（大写拼音）
        entry[0x32:0x32 + len(upper_bytes)] = upper_bytes
        data.extend(entry)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


# === TDX <NAME>.dat 读写（板块股票元数据） ===

def read_block_dat(path):
    """读取 TDX <NAME>.dat 文件，返回 [(market_tdx, code), ...] 列表。
    market_tdx 为 TDX 市场前缀字符串（'0','1','2'），code 为6位股票代码。
    文件不存在时返回空列表。"""
    if not os.path.exists(path):
        return []
    with open(path, "rb") as f:
        data = f.read()
    entries = []
    for offset in range(0, len(data), _DAT_RECORD_SIZE):
        rec = data[offset:offset + _DAT_RECORD_SIZE]
        if len(rec) < 9:
            continue
        # 0x00: 市场标志（取低字节即可）
        market = str(rec[0])
        # 0x02-0x08: 6位股票代码（ASCII，null补齐）
        code_bytes = rec[2:9].rstrip(b"\x00")
        code = code_bytes.decode("ascii", errors="ignore")
        if code:
            entries.append((market, code))
    return entries


def write_block_dat(path, stocks):
    """写入 TDX <NAME>.dat 文件。
    stocks: [(market_tdx, code), ...] 列表，与已有记录合并去重。"""
    existing = read_block_dat(path)
    seen = set()
    records = []
    # 先保留已有记录
    for market, code in existing:
        key = (market, code)
        if key not in seen:
            seen.add(key)
            records.append(_make_dat_record(market, code))
    # 再追加新记录（去重）
    for market, code in stocks:
        key = (market, code)
        if key not in seen:
            seen.add(key)
            records.append(_make_dat_record(market, code))

    data = b"".join(records)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


# === TDX blocknew.clr 读写（板块颜色与显示名） ===

_CLR_SLOT_SIZE = 0x50            # blocknew.clr 每个槽位80字节
_CLR_DEFAULT_COLOR = 0x0088F8F0  # 新板块默认颜色（BGR格式）


def read_blocknew_clr(path):
    """读取 TDX blocknew.clr，返回 {GBK显示名: BGR颜色值} 字典。
    文件不存在时返回空字典。"""
    if not os.path.exists(path):
        return {}
    with open(path, "rb") as f:
        data = f.read()
    result = {}
    for offset in range(0, len(data), _CLR_SLOT_SIZE):
        slot = data[offset:offset + _CLR_SLOT_SIZE]
        if len(slot) < 0x38:
            continue
        if slot[0] == 0:
            continue  # 空槽位，跳过
        # 0x00-0x1F: GBK编码的板块显示名（最多31字节）
        name_bytes = slot[0:32]
        null_idx = name_bytes.find(b"\x00")
        if null_idx >= 0:
            name_bytes = name_bytes[:null_idx]
        name = name_bytes.decode("gbk", errors="ignore").strip()
        if not name:
            continue
        # 0x34-0x37: BGR颜色值（小端序）
        color = int.from_bytes(slot[0x34:0x38], "little")
        result[name] = color
    return result


def write_blocknew_clr(path, new_entries):
    """写入 TDX blocknew.clr 条目。
    new_entries: {显示名: BGR颜色, ...}，颜色为0时使用默认色。
    已有同名条目不覆盖，新条目优先填入空槽位，无空槽则追加到文件末尾。"""
    if os.path.exists(path):
        data = bytearray(open(path, "rb").read())
    else:
        data = bytearray()

    # 确保至少有一个槽位的大小
    while len(data) < _CLR_SLOT_SIZE:
        data.extend(bytearray(_CLR_SLOT_SIZE))

    existing = read_blocknew_clr(path)

    for name, color in new_entries.items():
        if name in existing:
            continue  # 已有同名条目，跳过

        if color == 0:
            color = _CLR_DEFAULT_COLOR

        # 构建80字节槽位
        slot = bytearray(_CLR_SLOT_SIZE)
        name_bytes = name.encode("gbk")[:31]    # 0x00-0x1E: GBK显示名（最多31字节）
        slot[0:len(name_bytes)] = name_bytes
        slot[0x34:0x38] = color.to_bytes(4, "little")  # BGR颜色值

        # 优先填入空槽位（首个字节为0x00表示空）
        placed = False
        for i in range(0, len(data), _CLR_SLOT_SIZE):
            if data[i] == 0:
                data[i:i + _CLR_SLOT_SIZE] = slot
                placed = True
                break
        if not placed:
            data.extend(slot)  # 无空槽，追加到文件末尾

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
