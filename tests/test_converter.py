# 测试：converter 模块的所有格式转换函数
# 覆盖市场码互转、条目互转、blk/selfstock/ini/cfg/dat/clr 读写

# === 市场码互转测试 ===

from stockbridge.converter import (
    market_to_tdx,
    market_to_ths,
    tdx_line_to_entry,
    entry_to_tdx_line,
)


def test_market_to_tdx():
    """验证 THS→TDX 市场码映射：33→0(深圳), 17→1(上海), 120→2(北交所)"""
    assert market_to_tdx("33") == "0"
    assert market_to_tdx("17") == "1"
    assert market_to_tdx("120") == "2"


def test_market_to_ths():
    """验证 TDX→THS 市场码映射：0→33(深圳), 1→17(上海), 2→120(北交所)"""
    assert market_to_ths("0") == "33"
    assert market_to_ths("1") == "17"
    assert market_to_ths("2") == "120"


# === 条目互转测试 ===

def test_tdx_line_to_entry_shanghai():
    """TDX上海股票行 → THS条目：1600172 → {C:600172, M:17}"""
    result = tdx_line_to_entry("1600172")
    assert result == {"C": "600172", "M": "17", "P": "", "T": ""}


def test_tdx_line_to_entry_shenzhen():
    """TDX深圳股票行 → THS条目：0000651 → {C:000651, M:33}"""
    result = tdx_line_to_entry("0000651")
    assert result == {"C": "000651", "M": "33", "P": "", "T": ""}


def test_tdx_line_to_entry_beijing():
    """TDX北交所股票行 → THS条目：2920000 → {C:920000, M:120}"""
    result = tdx_line_to_entry("2920000")
    assert result == {"C": "920000", "M": "120", "P": "", "T": ""}


def test_entry_to_tdx_line_shanghai():
    """THS上海条目 → TDX行：上海17+600172 → '1600172'"""
    entry = {"C": "600172", "M": "17"}
    result = entry_to_tdx_line(entry)
    assert result == "1600172"


def test_entry_to_tdx_line_shenzhen():
    """THS深圳条目 → TDX行：深圳33+000651 → '0000651'"""
    entry = {"C": "000651", "M": "33"}
    result = entry_to_tdx_line(entry)
    assert result == "0000651"


def test_entry_to_tdx_line_beijing():
    """THS北交所条目 → TDX行：北交所120+920000 → '2920000'"""
    entry = {"C": "920000", "M": "120"}
    result = entry_to_tdx_line(entry)
    assert result == "2920000"


def test_market_to_tdx_with_code_fallback():
    """验证未知THS市场码时通过股票代码推断TDX前缀：
    600172(上海)的代码6开头 → 推断为'1'"""
    result = market_to_tdx("XX", code="600172")
    assert result == "1"


def test_market_to_tdx_unknown_no_code():
    """验证未知THS市场码且无代码时抛出KeyError"""
    import pytest
    with pytest.raises(KeyError):
        market_to_tdx("XX")


def test_entry_to_tdx_line_unknown_market():
    """验证未知THS市场码时仍可通过代码推断TDX前缀：
    600172 → 6开头推断上海 → '1600172'"""
    entry = {"C": "600172", "M": "XX"}
    result = entry_to_tdx_line(entry)
    assert result == "1600172"


def test_entry_to_tdx_line_bare_fallback():
    """验证完全无法推断市场时返回原始代码作为后备：
    1A0001（非6位数字代码）→ 直接返回'1A0001'"""
    entry = {"C": "1A0001", "M": "XX"}
    result = entry_to_tdx_line(entry)
    assert result == "1A0001"


def test_tdx_line_to_entry_strips_whitespace():
    """验证 tdx_line_to_entry 会去除行尾空白字符"""
    result = tdx_line_to_entry("1600172\r\n")
    assert result == {"C": "600172", "M": "17", "P": "", "T": ""}


# === TDX/THS 文件读写测试 ===

import os
import tempfile
from stockbridge.converter import (
    read_blk, write_blk,
    read_selfstock, write_selfstock,
    name_to_pinyin,
    read_stockblock_ini, write_stockblock_ini,
    read_blocknew_cfg, write_blocknew_cfg,
    read_block_dat, write_block_dat,
    _make_dat_record, _DAT_RECORD_SIZE, _BLOCKNEW_CFG_SIZE,
)


# --- .blk 文件 ---

def test_read_blk():
    """验证读取 TDX .blk 文件（CRLF换行）返回行列表"""
    content = "1600172\r\n0000651\r\n"
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".blk") as f:
        f.write(content)
        path = f.name
    result = read_blk(path)
    os.unlink(path)
    assert result == ["1600172", "0000651"]


def test_write_blk():
    """验证写入 TDX .blk 文件使用 CRLF 换行"""
    path = tempfile.mktemp(suffix=".blk")
    lines = ["1600172", "0000651"]
    write_blk(path, lines)
    with open(path, "r", newline="") as f:
        content = f.read()
    os.unlink(path)
    assert content == "1600172\r\n0000651\r\n"


# --- SelfStockInfo.json ---

def test_read_selfstock():
    """验证读取同花顺自选股JSON文件，返回完整条目列表（含行情字段）"""
    content = '[{"C":"600172","M":"17","P":"41.68","T":"20260526"},{"C":"300604","M":"33","P":"308.93","T":"20260624"}]'
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json", encoding="utf-8") as f:
        f.write(content)
        path = f.name
    result = read_selfstock(path)
    os.unlink(path)
    assert len(result) == 2
    assert result[0]["C"] == "600172"
    assert result[0]["M"] == "17"
    assert result[0]["P"] == "41.68"
    assert result[0]["T"] == "20260526"


def test_write_selfstock_preserves_old_fields():
    """验证写入自选股时保留空行情字段"""
    path = tempfile.mktemp(suffix=".json")
    entries = [{"C": "600172", "M": "17", "P": "", "T": ""}]
    write_selfstock(path, entries)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    os.unlink(path)
    assert '"P":""' in content or '"P": ""' in content


def test_write_selfstock_merges_old_entries():
    """验证写入时合并旧条目的行情字段（P=现价, T=日期），
    保留同花顺维护的数据不覆盖"""
    path = tempfile.mktemp(suffix=".json")
    old = [{"C": "600172", "M": "17", "P": "41.68", "T": "20260526"}]
    new = [{"C": "600172", "M": "17", "P": "", "T": ""}, {"C": "300604", "M": "33", "P": "", "T": ""}]
    write_selfstock(path, new, old_entries=old)
    result = read_selfstock(path)
    os.unlink(path)
    # 已有股票的行情字段被保留
    assert result[0]["P"] == "41.68"
    assert result[0]["T"] == "20260526"
    # 新股票的行情字段为空
    assert result[1]["P"] == ""
    assert result[1]["T"] == ""


# --- 拼音转换 ---

def test_name_to_pinyin():
    """验证中文板块名转拼音首字母：条件股 → tjg"""
    result = name_to_pinyin("条件股")
    assert result == "tjg"


def test_name_to_pinyin_chinese():
    """验证自选股转拼音：自选股 → zxg"""
    result = name_to_pinyin("自选股")
    assert result == "zxg"


# --- stockblock.ini ---

def test_read_stockblock_ini():
    """验证解析 THS stockblock.ini，正确提取板块名和股票列表"""
    content = (
        "[ConfigInfo]\r\n"
        "ConfigName=stockblock\r\n"
        "[BLOCK_NAME_MAP_TABLE]\r\n"
        "23=条件股\r\n"
        "24=自选\r\n"
        "[BLOCK_STOCK_CONTEXT]\r\n"
        "23=33:002741,17:603906,\r\n"
        "24=17:600172,\r\n"
        "[SYSTEM]\r\n"
        "LastSynCodeID=100\r\n"
        "[@7]\r\n"
        "23=536871424\r\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".ini", encoding="gbk") as f:
        f.write(content)
        path = f.name
    blocks, raw = read_stockblock_ini(path)
    os.unlink(path)
    assert "23" in blocks
    assert blocks["23"]["name"] == "条件股"
    assert len(blocks["23"]["stocks"]) == 2
    assert blocks["23"]["stocks"][0] == {"M": "33", "C": "002741"}


def test_write_stockblock_ini_preserves_other_sections():
    """验证写入 INI 时保留其他节（如 [SYSTEM]），只更新板块相关节"""
    content = (
        "[ConfigInfo]\r\n"
        "ConfigName=stockblock\r\n"
        "[BLOCK_NAME_MAP_TABLE]\r\n"
        "23=条件股\r\n"
        "[BLOCK_STOCK_CONTEXT]\r\n"
        "23=33:002741,17:603906,\r\n"
        "[SYSTEM]\r\n"
        "LastSynCodeID=100\r\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".ini", encoding="gbk") as f:
        f.write(content)
        path = f.name
    blocks, raw = read_stockblock_ini(path)
    blocks["23"]["stocks"].append({"M": "17", "C": "600172"})
    write_stockblock_ini(path, blocks, raw)
    result = open(path, "r", encoding="gbk").read()
    os.unlink(path)
    assert "[SYSTEM]" in result
    assert "LastSynCodeID=100" in result
    assert "17:600172" in result


# --- TDX .dat 记录 ---

def test_make_dat_record():
    """验证生成的 .dat 记录长度、市场标志、代码字段和有效标志"""
    # 深圳股票 000720
    rec = _make_dat_record("0", "000720")
    assert len(rec) == _DAT_RECORD_SIZE  # 80字节
    assert rec[0:2] == b"\x00\x00"       # 市场标志：深圳=0
    assert rec[2:8] == b"000720"         # 6位代码
    assert rec[8] == 0x00                # 7字节代码字段的null补齐
    assert rec[-1] == 0x01               # 有效标志

    # 上海股票 600172
    rec = _make_dat_record("1", "600172")
    assert rec[0:2] == b"\x01\x00"       # 市场标志：上海=1（小端序）
    assert rec[2:8] == b"600172"
    assert rec[8] == 0x00


# --- blocknew.cfg ---

def test_read_blocknew_cfg_empty():
    """验证读取不存在的 blocknew.cfg 返回空列表"""
    path = tempfile.mktemp(suffix=".cfg")
    result = read_blocknew_cfg(path)
    assert result == []


def test_write_and_read_blocknew_cfg():
    """验证写入并回读 blocknew.cfg，条目数量一致"""
    path = tempfile.mktemp(suffix=".cfg")
    write_blocknew_cfg(path, [("test", "TEST"), ("hz", "HZ")])
    result = read_blocknew_cfg(path)
    os.unlink(path)
    assert len(result) == 2
    names = {lower for lower, _ in result}
    assert "test" in names
    assert "hz" in names


def test_write_blocknew_cfg_merges_existing():
    """验证两次写入 blocknew.cfg 会合并已有条目（以 lower_name 为键去重）"""
    path = tempfile.mktemp(suffix=".cfg")
    write_blocknew_cfg(path, [("test", "TEST")])
    write_blocknew_cfg(path, [("hz", "HZ")])
    result = read_blocknew_cfg(path)
    os.unlink(path)
    assert len(result) == 2


# --- <NAME>.dat ---

def test_read_block_dat_empty():
    """验证读取不存在的 .dat 文件返回空列表"""
    path = tempfile.mktemp(suffix=".dat")
    result = read_block_dat(path)
    assert result == []


def test_write_and_read_block_dat():
    """验证写入并回读 .dat 文件，股票代码正确"""
    path = tempfile.mktemp(suffix=".dat")
    stocks = [("0", "000720"), ("1", "600172")]
    write_block_dat(path, stocks)
    result = read_block_dat(path)
    os.unlink(path)
    assert len(result) == 2
    codes = {c for _, c in result}
    assert "000720" in codes
    assert "600172" in codes


def test_write_block_dat_deduplicates():
    """验证两次写入同一股票不会产生重复记录"""
    path = tempfile.mktemp(suffix=".dat")
    write_block_dat(path, [("0", "000720")])
    write_block_dat(path, [("0", "000720"), ("1", "600172")])
    result = read_block_dat(path)
    os.unlink(path)
    assert len(result) == 2  # 去重后仍是2只股票


def test_blocknew_cfg_file_size():
    """验证 blocknew.cfg 每个条目恰好120字节"""
    path = tempfile.mktemp(suffix=".cfg")
    write_blocknew_cfg(path, [("a", "A"), ("b", "B"), ("c", "C")])
    size = os.path.getsize(path)
    os.unlink(path)
    assert size == _BLOCKNEW_CFG_SIZE * 3  # 3个板块 = 360字节
