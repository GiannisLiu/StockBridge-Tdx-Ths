from stockbridge.converter import (
    market_to_tdx,
    market_to_ths,
    tdx_line_to_entry,
    entry_to_tdx_line,
)


def test_market_to_tdx():
    assert market_to_tdx("33") == "0"
    assert market_to_tdx("17") == "1"
    assert market_to_tdx("120") == "2"


def test_market_to_ths():
    assert market_to_ths("0") == "33"
    assert market_to_ths("1") == "17"
    assert market_to_ths("2") == "120"


def test_tdx_line_to_entry_shanghai():
    result = tdx_line_to_entry("1600172")
    assert result == {"C": "600172", "M": "17", "P": "", "T": ""}


def test_tdx_line_to_entry_shenzhen():
    result = tdx_line_to_entry("0000651")
    assert result == {"C": "000651", "M": "33", "P": "", "T": ""}


def test_tdx_line_to_entry_beijing():
    result = tdx_line_to_entry("2920000")
    assert result == {"C": "920000", "M": "120", "P": "", "T": ""}


def test_entry_to_tdx_line_shanghai():
    entry = {"C": "600172", "M": "17"}
    result = entry_to_tdx_line(entry)
    assert result == "1600172"


def test_entry_to_tdx_line_shenzhen():
    entry = {"C": "000651", "M": "33"}
    result = entry_to_tdx_line(entry)
    assert result == "0000651"


def test_entry_to_tdx_line_beijing():
    entry = {"C": "920000", "M": "120"}
    result = entry_to_tdx_line(entry)
    assert result == "2920000"


def test_market_to_tdx_with_code_fallback():
    result = market_to_tdx("XX", code="600172")
    assert result == "1"


def test_market_to_tdx_unknown_no_code():
    import pytest
    with pytest.raises(KeyError):
        market_to_tdx("XX")


def test_entry_to_tdx_line_unknown_market():
    entry = {"C": "600172", "M": "XX"}
    result = entry_to_tdx_line(entry)
    assert result == "1600172"


def test_entry_to_tdx_line_bare_fallback():
    entry = {"C": "1A0001", "M": "XX"}
    result = entry_to_tdx_line(entry)
    assert result == "1A0001"


def test_tdx_line_to_entry_strips_whitespace():
    result = tdx_line_to_entry("1600172\r\n")
    assert result == {"C": "600172", "M": "17", "P": "", "T": ""}


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


def test_read_blk():
    content = "1600172\r\n0000651\r\n"
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".blk") as f:
        f.write(content)
        path = f.name
    result = read_blk(path)
    os.unlink(path)
    assert result == ["1600172", "0000651"]


def test_write_blk():
    path = tempfile.mktemp(suffix=".blk")
    lines = ["1600172", "0000651"]
    write_blk(path, lines)
    with open(path, "r", newline="") as f:
        content = f.read()
    os.unlink(path)
    assert content == "1600172\r\n0000651\r\n"


def test_read_selfstock():
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
    path = tempfile.mktemp(suffix=".json")
    entries = [{"C": "600172", "M": "17", "P": "", "T": ""}]
    write_selfstock(path, entries)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    os.unlink(path)
    assert '"P":""' in content or '"P": ""' in content


def test_write_selfstock_merges_old_entries():
    path = tempfile.mktemp(suffix=".json")
    old = [{"C": "600172", "M": "17", "P": "41.68", "T": "20260526"}]
    new = [{"C": "600172", "M": "17", "P": "", "T": ""}, {"C": "300604", "M": "33", "P": "", "T": ""}]
    write_selfstock(path, new, old_entries=old)
    result = read_selfstock(path)
    os.unlink(path)
    assert result[0]["P"] == "41.68"
    assert result[0]["T"] == "20260526"
    assert result[1]["P"] == ""
    assert result[1]["T"] == ""


def test_name_to_pinyin():
    result = name_to_pinyin("条件股")
    assert result == "tjg"


def test_name_to_pinyin_chinese():
    result = name_to_pinyin("自选股")
    assert result == "zxg"


def test_read_stockblock_ini():
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


def test_make_dat_record():
    rec = _make_dat_record("0", "000720")
    assert len(rec) == _DAT_RECORD_SIZE
    assert rec[0:2] == b"\x00\x00"
    assert rec[2:8] == b"000720"
    assert rec[8] == 0x00  # null padding in 7-byte code field
    assert rec[-1] == 0x01

    rec = _make_dat_record("1", "600172")
    assert rec[0:2] == b"\x01\x00"
    assert rec[2:8] == b"600172"
    assert rec[8] == 0x00


def test_read_blocknew_cfg_empty():
    path = tempfile.mktemp(suffix=".cfg")
    result = read_blocknew_cfg(path)
    assert result == []


def test_write_and_read_blocknew_cfg():
    path = tempfile.mktemp(suffix=".cfg")
    write_blocknew_cfg(path, [("test", "TEST"), ("hz", "HZ")])
    result = read_blocknew_cfg(path)
    os.unlink(path)
    assert len(result) == 2
    names = {lower for lower, _ in result}
    assert "test" in names
    assert "hz" in names


def test_write_blocknew_cfg_merges_existing():
    path = tempfile.mktemp(suffix=".cfg")
    write_blocknew_cfg(path, [("test", "TEST")])
    write_blocknew_cfg(path, [("hz", "HZ")])
    result = read_blocknew_cfg(path)
    os.unlink(path)
    assert len(result) == 2


def test_read_block_dat_empty():
    path = tempfile.mktemp(suffix=".dat")
    result = read_block_dat(path)
    assert result == []


def test_write_and_read_block_dat():
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
    path = tempfile.mktemp(suffix=".dat")
    write_block_dat(path, [("0", "000720")])
    write_block_dat(path, [("0", "000720"), ("1", "600172")])
    result = read_block_dat(path)
    os.unlink(path)
    assert len(result) == 2


def test_blocknew_cfg_file_size():
    path = tempfile.mktemp(suffix=".cfg")
    write_blocknew_cfg(path, [("a", "A"), ("b", "B"), ("c", "C")])
    size = os.path.getsize(path)
    os.unlink(path)
    assert size == _BLOCKNEW_CFG_SIZE * 3
