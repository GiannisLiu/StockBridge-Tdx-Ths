# StockBridge-Tdx-Ths

通达信(TDX)与同花顺(THS)自选板块双向自动同步工具。通过文件监控实时检测板块变动，以文件最后修改时间为准双向同步。

## 配置

环境变量（均可选，不设则使用默认值）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `TDX_PATH` | — | 通达信安装目录 |
| `THS_PATH` | — | 同花顺安装目录 |
| `THS_USER_ID` | — | 同花顺用户 ID（目录名） |

其他用户 clone 项目后只需设置环境变量指向自己的安装目录即可。

```powershell
$env:TDX_PATH = "D:/通达信"
$env:THS_PATH = "E:/同花顺"
$env:THS_USER_ID = "mx_123456789"
```

## 启动与停止

**⚠️ 必须在项目根目录执行**，不能进入 `stockbridge/` 子目录运行。

```powershell
# 启动（前台运行，Ctrl+C 停止）
cd <项目根目录>
python -m stockbridge.main

# 或后台运行（Windows PowerShell）
Start-Process -NoNewWindow python -ArgumentList "-m", "stockbridge.main"

# 停止
# 前台运行时按 Ctrl+C
# 后台运行时，找到进程并终止：
Get-Process python | Stop-Process
```

程序启动后先执行一次全量对齐，然后进入文件监控模式，实时检测变动并自动同步。

## 文件格式

### 通达信 (TDX)

- **位置**: `<TDX安装目录>/T0002/blocknew/`
- **自选股**: `zxg.blk`
- **自定义板块**: `<拼音首字母>.blk`（如 `tjg.blk`）
- **编码**: ASCII 文本，CRLF 换行
- **格式**: 每行一个股票，`市场前缀` + `6位代码`
  - `0` = 深圳（000xxx, 002xxx, 300xxx）
  - `1` = 上海（600xxx, 603xxx, 688xxx）
  - `2` = 北交所（920xxx）
  - 示例: `1600172` = 上海 600172

#### 板块注册表 `blocknew.cfg`

通达信通过此文件发现自定义板块。只写 `.blk` 而不注册此文件，通达信不会显示该板块。

- **格式**: 120 字节/板块，多板块连续存放
- **结构**（单条目 120 字节）:
  - `0x00-0x07`: 板块小写名（ASCII，如 `test`），null 补齐
  - `0x08-0x2F`: 保留（全零）
  - `0x30-0x31`: 标志位（`00 00` = 有效）
  - `0x32-0x37`: 板块大写名（ASCII，如 `TEST`），null 补齐
  - `0x38-0x77`: 保留（全零）

#### 板块元数据 `<NAME>.dat`

每只股票在该板块中的元数据。每个板块一个大写命名的 `.dat` 文件（如 `TEST.dat`）。

- **格式**: 80 字节 (0x50) / 每只股票，多股票连续存放
- **结构**（单条目 80 字节）:
  - `0x00-0x01`: 市场标志（`00 00`=深圳, `01 00`=上海）
  - `0x02-0x08`: 6 位股票代码（ASCII），null 补齐
  - `0x09-0x1F`: 保留（全零）
  - `0x20-0x4E`: 行情数据（价格、时间戳、排序权重等，由通达信维护）
  - `0x4F`: 记录有效标志（`01`）
- 写入新股票时使用模板记录，通达信启动后会自动更新行情数据字段

### 同花顺 (THS)

- **安装目录**: `<THS安装目录>/<用户ID>/`
- **自选股**: `SelfStockInfo.json`
  - **编码**: UTF-8
  - **格式**: JSON 数组，每项字段：
    - `C`: 股票代码（6位）
    - `M`: 市场代码（17=上海, 33=深圳, 120=北交所）
    - `P`: 现价
    - `T`: 更新日期 (YYYYMMDD)
- **自定义板块**: `stockblock.ini`
  - **编码**: GBK
  - **结构**:
    - `[BLOCK_NAME_MAP_TABLE]`: hex ID → 板块中文名
    - `[BLOCK_STOCK_CONTEXT]`: hex ID → 股票列表，格式 `市场:代码,`（如 `33:002741,17:603906,`）

### 市场码映射

| TDX 前缀 | THS M 值 | 市场 |
|----------|----------|------|
| 0 | 33 | 深圳 |
| 1 | 17 | 上海 |
| 2 | 120 | 北交所 |

## 同步规则

1. **触发方式**: 文件监控实时触发（watchdog）
2. **同步粒度**: 整个板块文件为最小单元
3. **冲突策略**: 比较同名文件 mtime，较新的覆盖较旧的
4. **防抖动**: 文件变动后 500ms 内忽略同一文件的重复事件
5. **新建板块**: 在一侧新增板块后，自动在另一侧创建同名板块
6. **品种范围**: 同步全部品种（个股、ETF、可转债、指数等）
7. **板块匹配**: 两边各创建同名板块，通过拼音首字母对应
8. **TDX 三件套**: THS→TDX 同步时，同时写入 `.blk` + `blocknew.cfg` + `<NAME>.dat`，确保通达信能识别板块

## 项目结构

```
stockbridge/
├── main.py              # 入口，启动监控
├── config.py            # 配置：环境变量读取路径、监控参数
├── watcher.py           # watchdog 文件监控
├── converter.py         # 格式互转：TDX .blk/.cfg/.dat ↔ THS .json & .ini
├── sync.py              # 同步引擎：比较 mtime，执行覆盖
├── logger.py            # 日志：操作记录、冲突告警
├── requirements.txt     # 依赖：watchdog, pypinyin
└── tests/
    ├── test_converter.py
    └── test_sync.py
```

## 模块职责

### config.py

- 通过 `os.environ.get()` 读取 TDX/THS 安装路径和用户 ID，支持默认值
- 派生路径：`TDX_BLOCK_DIR`、`THS_USER_DIR` 等
- 监控防抖时间（默认 500ms）
- 日志文件路径

### watcher.py

- 使用 watchdog 同时监控 TDX `blocknew/` 和 THS 用户目录
- 文件创建/修改事件 → 回调 sync 引擎
- 防抖：同一文件 500ms 内不重复触发

### converter.py

**TDX ↔ THS 格式转换：**
- `market_to_tdx(ths_market, code)` / `market_to_ths(tdx_prefix)` — 市场码互转
- `tdx_line_to_entry(line)` / `entry_to_tdx_line(entry)` — 单行与条目互转

**TDX .blk 读写：**
- `read_blk(path)` / `write_blk(path, lines)` — 板块股票列表

**TDX 板块注册表（blocknew.cfg）：**
- `read_blocknew_cfg(path)` → 返回 `[(lower_name, upper_name), ...]` 列表
- `write_blocknew_cfg(path, entries)` — 写入并合并已有条目

**TDX 板块元数据（\<NAME\>.dat）：**
- `read_block_dat(path)` → 返回 `[(market_tdx, code), ...]` 列表
- `write_block_dat(path, stocks)` — 写入 80 字节记录，去重并保留已有数据
- `_make_dat_record(market_tdx, code)` — 生成单条 80 字节记录，与通达信原生格式逐字节一致

**THS 自选股：**
- `read_selfstock(path)` / `write_selfstock(path, entries, old_entries)` — JSON 读写，保留行情字段

**THS 自定义板块：**
- `read_stockblock_ini(path)` / `write_stockblock_ini(path, blocks, raw)` — INI 解析/写回
- `name_to_pinyin(name)` — 中文板块名 → 拼音首字母（用于生成 TDX 文件名）

### sync.py

- `init_sync()`: 启动时全量扫描，按 mtime 对齐所有板块
- `on_file_changed(path)`: 收到监控事件后的处理入口
- `_sync_blk_to_ths(tdx_path)`: TDX → THS 单向同步
- `_sync_ths_to_tdx(hex_id, ths_blocks)`: THS → TDX 单向同步
  - 同时写入 `.blk`、`blocknew.cfg`、`<NAME>.dat` 三个文件
- `_sync_selfstock_to_tdx()`: 自选股 THS → TDX 同步
- `_compare_and_sync_block()`: 比较 mtime，以新盖旧
- 防抖缓存: 记录最近触发事件的文件及时间戳

### logger.py

- 按日期滚动日志文件
- 格式: `[时间] [级别] 操作描述 | 板块:xxx | 股票数:xx→xx | 结果`
- 同时输出到控制台

## 编码约定

- TDX `.blk` 文件: **ASCII**（纯数字文本）
- TDX `blocknew.cfg`: **二进制**，板块名字段为 ASCII
- TDX `<NAME>.dat`: **二进制**，股票代码字段为 ASCII
- THS `stockblock.ini`: **GBK**（板块名为中文）
- THS `SelfStockInfo.json`: **UTF-8**
- Python 源码: **UTF-8**

## 初始化流程

1. 读取配置，验证两边路径存在
2. 扫描 TDX `blocknew/` 下所有 `.blk`
3. 扫描 THS `SelfStockInfo.json` 和 `stockblock.ini`
4. 按文件名/板块名匹配两边板块
5. 逐板块比较 mtime，较新的覆盖较旧的
6. 为只在一边存在的板块在另一边创建对应文件（TDX 侧同时写入三件套）
7. 初始对齐完成后启动 watchdog 监控
