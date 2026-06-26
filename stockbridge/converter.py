import json
import os
import re
from pypinyin import pinyin, Style

_MARKET_TDX_TO_THS = {"0": "33", "1": "17", "2": "120"}
_MARKET_THS_TO_TDX = {"33": "0", "17": "1", "120": "2", "16": "1", "20": "1"}


def _infer_tdx_prefix(code):
    """Infer TDX prefix from stock code when M code is unknown."""
    if len(code) == 6 and code.isdigit():
        first = code[0]
        if first in ("6", "5", "7"):  # Shanghai main/ETF
            return "1"
        elif code.startswith("688"):  # Shanghai STAR
            return "1"
        elif first in ("0", "1", "2", "3"):  # Shenzhen main/SME/ChiNext/ETF
            return "0"
        elif first in ("8", "9"):  # Beijing (8xxx) / Beijing (9xxx)
            return "2"
    return None


def market_to_tdx(ths_market, code=None):
    if ths_market in _MARKET_THS_TO_TDX:
        return _MARKET_THS_TO_TDX[ths_market]
    if code:
        prefix = _infer_tdx_prefix(code)
        if prefix is not None:
            return prefix
    raise KeyError(f"Unknown market code '{ths_market}'")


def market_to_ths(tdx_prefix):
    return _MARKET_TDX_TO_THS[tdx_prefix]


def tdx_line_to_entry(line):
    line = line.strip()
    prefix = line[0]
    code = line[1:]
    return {"C": code, "M": market_to_ths(prefix), "P": "", "T": ""}


def entry_to_tdx_line(entry):
    try:
        prefix = market_to_tdx(entry["M"], entry.get("C"))
        return f"{prefix}{entry['C']}"
    except KeyError:
        return entry["C"]


_BLOCKNEW_CFG_SIZE = 120
_DAT_RECORD_SIZE = 0x50

# Minimal valid .dat record template (80 bytes), based on a known-good TDX record.
# We only vary the flag (offset 0x00) and code (offset 0x02); the rest is fixed.
_DAT_TEMPLATE = bytes([
    0x00, 0x00,                                                                     # 0x00: flag (overwritten)
    0x30, 0x30, 0x30, 0x30, 0x30, 0x30, 0x30,                                      # 0x02: code placeholder (overwritten)
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,                                # 0x09
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,                                # 0x11
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,                                      # 0x19 (7 bytes)
    0x00,                                                                           # 0x20
    0x12, 0x27, 0x35, 0x01, 0xf6, 0x28, 0x6c, 0x40,                                # 0x21
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,                                      # 0x29
    0x00, 0x00, 0x00, 0x00, 0x00,                                                  # 0x30
    0xd0, 0x02, 0x00, 0x00,                                                        # 0x35
    0xec, 0xc8, 0x00, 0x00,                                                        # 0x39
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,                                # 0x3D
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,                                # 0x45
    0x00, 0x00,                                                                     # 0x4D
    0x01,                                                                           # 0x4F
])


def _make_dat_record(market_tdx, code):
    """Build an 80-byte .dat record for a single stock."""
    rec = bytearray(_DAT_TEMPLATE)
    rec[0:2] = int(market_tdx).to_bytes(2, "little")
    code_bytes = code.encode("ascii")
    rec[2:9] = b"\x00" * 7
    rec[2:2 + len(code_bytes)] = code_bytes
    return bytes(rec)


def read_blk(path):
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return [line.strip() for line in f if line.strip()]


def write_blk(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="\r\n") as f:
        for line in lines:
            f.write(line + "\n")


def read_selfstock(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_selfstock(path, entries, old_entries=None):
    old_map = {}
    if old_entries:
        for e in old_entries:
            old_map[e["C"]] = e
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


def name_to_pinyin(name, taken=None):
    result = pinyin(name, style=Style.FIRST_LETTER)
    base = "".join([p[0] for p in result])
    if taken is None or base not in taken:
        return base
    i = 2
    while f"{base}{i}" in taken:
        i += 1
    return f"{base}{i}"


def _parse_ini_sections(content):
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


def read_stockblock_ini(path):
    blocks = {}
    if not os.path.exists(path):
        return blocks, ""
    with open(path, "r", encoding="gbk") as f:
        raw = f.read()
    sections = _parse_ini_sections(raw)

    name_section = sections.get("BLOCK_NAME_MAP_TABLE", "")
    name_map = {}
    for line in name_section.splitlines():
        m = re.match(r"^([0-9A-Fa-f]+)=(.*)", line)
        if m:
            name_map[m.group(1)] = m.group(2)

    stock_section = sections.get("BLOCK_STOCK_CONTEXT", "")
    stock_map = {}
    for line in stock_section.splitlines():
        m = re.match(r"^([0-9A-Fa-f]+)=(.*)", line)
        if m:
            stock_map[m.group(1)] = m.group(2)

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
    sections = _parse_ini_sections(raw_content)

    name_lines = []
    stock_lines = []
    known_ids = set(blocks.keys())

    for hex_id in sorted(blocks.keys()):
        name_lines.append(f"{hex_id}={blocks[hex_id]['name']}")
        stocks_str = ",".join(
            f"{s['M']}:{s['C']}" for s in blocks[hex_id]["stocks"]
        ) + ","
        stock_lines.append(f"{hex_id}={stocks_str}")

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

    sections["BLOCK_NAME_MAP_TABLE"] = "[BLOCK_NAME_MAP_TABLE]\r\n" + "\r\n".join(name_lines) + "\r\n"
    sections["BLOCK_STOCK_CONTEXT"] = "[BLOCK_STOCK_CONTEXT]\r\n" + "\r\n".join(stock_lines) + "\r\n"

    output = "".join(sections.values())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="gbk") as f:
        f.write(output)


def read_blocknew_cfg(path):
    """Read TDX blocknew.cfg, return list of (lower_name, upper_name) tuples."""
    if not os.path.exists(path):
        return []
    with open(path, "rb") as f:
        data = f.read()
    entries = []
    for offset in range(0, len(data), _BLOCKNEW_CFG_SIZE):
        chunk = data[offset:offset + _BLOCKNEW_CFG_SIZE]
        if len(chunk) < 8:
            continue
        lower_raw = chunk[0:8].rstrip(b"\x00")
        if not lower_raw:
            continue
        lower = lower_raw.decode("gbk", errors="replace")
        if not lower:
            continue
        upper_raw = chunk[0x30:0x38]
        upper = upper_raw.lstrip(b"\x00").rstrip(b"\x00").decode("ascii", errors="ignore")
        if not upper:
            upper = lower.upper()
        entries.append((lower, upper))
    return entries


def write_blocknew_cfg(path, entries):
    """Write TDX blocknew.cfg. entries: list of (lower_name, upper_name)."""
    existing = read_blocknew_cfg(path)
    merged = {}
    for lower, upper in existing:
        merged[lower] = upper
    for lower, upper in entries:
        merged[lower] = upper

    data = bytearray()
    for lower, upper in merged.items():
        entry = bytearray(_BLOCKNEW_CFG_SIZE)
        lower_bytes = lower.encode("gbk")[:8]
        upper_bytes = upper.encode("ascii")[:6]
        entry[0:len(lower_bytes)] = lower_bytes
        entry[0x32:0x32 + len(upper_bytes)] = upper_bytes
        data.extend(entry)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def read_block_dat(path):
    """Read a TDX <NAME>.dat file, return list of (market_tdx, code) tuples."""
    if not os.path.exists(path):
        return []
    with open(path, "rb") as f:
        data = f.read()
    entries = []
    for offset in range(0, len(data), _DAT_RECORD_SIZE):
        rec = data[offset:offset + _DAT_RECORD_SIZE]
        if len(rec) < 9:
            continue
        market = str(rec[0])
        code_bytes = rec[2:9].rstrip(b"\x00")
        code = code_bytes.decode("ascii", errors="ignore")
        if code:
            entries.append((market, code))
    return entries


def write_block_dat(path, stocks):
    """Write a TDX <NAME>.dat file. stocks: list of (market_tdx, code)."""
    existing = read_block_dat(path)
    seen = set()
    records = []
    for market, code in existing:
        key = (market, code)
        if key not in seen:
            seen.add(key)
            records.append(_make_dat_record(market, code))
    for market, code in stocks:
        key = (market, code)
        if key not in seen:
            seen.add(key)
            records.append(_make_dat_record(market, code))

    data = b"".join(records)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


_CLR_SLOT_SIZE = 0x50  # 80 bytes per slot in blocknew.clr
_CLR_DEFAULT_COLOR = 0x0088F8F0  # default BGR color for new blocks


def read_blocknew_clr(path):
    """Read TDX blocknew.clr, return dict {display_name_gbk: color}."""
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
            continue  # empty slot
        name_bytes = slot[0:32]
        null_idx = name_bytes.find(b"\x00")
        if null_idx >= 0:
            name_bytes = name_bytes[:null_idx]
        name = name_bytes.decode("gbk", errors="ignore").strip()
        if not name:
            continue
        color = int.from_bytes(slot[0x34:0x38], "little")
        result[name] = color
    return result


def write_blocknew_clr(path, new_entries):
    """Write entries to blocknew.clr. new_entries: {display_name: color, ...}.
    Updates existing slots by name or fills empty slots. Color defaults if 0."""
    if os.path.exists(path):
        data = bytearray(open(path, "rb").read())
    else:
        data = bytearray()

    while len(data) < _CLR_SLOT_SIZE:
        data.extend(bytearray(_CLR_SLOT_SIZE))

    existing = read_blocknew_clr(path)

    for name, color in new_entries.items():
        if name in existing:
            continue

        if color == 0:
            color = _CLR_DEFAULT_COLOR

        slot = bytearray(_CLR_SLOT_SIZE)
        name_bytes = name.encode("gbk")[:31]
        slot[0:len(name_bytes)] = name_bytes
        slot[0x34:0x38] = color.to_bytes(4, "little")

        # Fill first empty slot or append
        placed = False
        for i in range(0, len(data), _CLR_SLOT_SIZE):
            if data[i] == 0:
                data[i:i + _CLR_SLOT_SIZE] = slot
                placed = True
                break
        if not placed:
            data.extend(slot)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
