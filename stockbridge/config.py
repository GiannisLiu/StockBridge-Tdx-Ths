import os

TDX_PATH = "C:/new_tdx64"
THS_PATH = "C:/同花顺软件/同花顺"
THS_USER_ID = "mx_514154534"

TDX_BLOCK_DIR = os.path.join(TDX_PATH, "T0002", "blocknew")
THS_USER_DIR = os.path.join(THS_PATH, THS_USER_ID)
THS_SELFSTOCK_FILE = os.path.join(THS_USER_DIR, "SelfStockInfo.json")
THS_BLOCK_FILE = os.path.join(THS_USER_DIR, "stockblock.ini")

DEBOUNCE_MS = 500
LOG_DIR = "logs"
