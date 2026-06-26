_MARKET_TDX_TO_THS = {"0": "33", "1": "17", "2": "120"}
_MARKET_THS_TO_TDX = {"33": "0", "17": "1", "120": "2"}


def market_to_tdx(ths_market):
    return _MARKET_THS_TO_TDX[ths_market]


def market_to_ths(tdx_prefix):
    return _MARKET_TDX_TO_THS[tdx_prefix]


def tdx_line_to_entry(line):
    line = line.strip()
    prefix = line[0]
    code = line[1:]
    return {"C": code, "M": market_to_ths(prefix), "P": "", "T": ""}


def entry_to_tdx_line(entry):
    prefix = market_to_tdx(entry["M"])
    return f"{prefix}{entry['C']}"
