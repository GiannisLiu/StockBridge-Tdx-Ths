# 配置文件：通过环境变量读取通达信/同花顺安装路径，未设置时使用默认值
import os

# 通达信安装根目录
TDX_PATH = os.environ.get("TDX_PATH", "C:/new_tdx64")
# 同花顺安装根目录
THS_PATH = os.environ.get("THS_PATH", "C:/同花顺软件/同花顺")
# 同花顺用户ID（即用户目录名，如 mx_514154534）
THS_USER_ID = os.environ.get("THS_USER_ID", "mx_514154534")

# 派生路径
TDX_BLOCK_DIR = os.path.join(TDX_PATH, "T0002", "blocknew")     # 通达信自定义板块目录
THS_USER_DIR = os.path.join(THS_PATH, THS_USER_ID)              # 同花顺用户数据目录
THS_SELFSTOCK_FILE = os.path.join(THS_USER_DIR, "SelfStockInfo.json")  # 同花顺自选股文件
THS_BLOCK_FILE = os.path.join(THS_USER_DIR, "stockblock.ini")         # 同花顺自定义板块文件

# 文件监控防抖时间（毫秒）：同一文件在此时长内的重复事件将被忽略
DEBOUNCE_MS = 500
# 日志输出目录
LOG_DIR = "logs"
