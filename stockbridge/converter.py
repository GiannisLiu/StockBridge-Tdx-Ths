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


def name_to_pinyin(name):
    result = pinyin(name, style=Style.FIRST_LETTER)
    return "".join([p[0] for p in result])


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
