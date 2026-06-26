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


def test_tdx_line_to_entry_strips_whitespace():
    result = tdx_line_to_entry("1600172\r\n")
    assert result == {"C": "600172", "M": "17", "P": "", "T": ""}
