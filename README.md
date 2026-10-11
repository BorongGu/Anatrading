# Anatrading

用本地行情研究股票：看清单股趋势与量价变化，比较两只股票的关系，再检查一组股票或板块样本的强弱与覆盖。优先服务 A 股日线波段和分钟复盘，逐步扩展到国际股票、中长期择时与组合研究。

本轮已接通三个首版日线研究流程，**Linux 自动化回归通过，完整验收仍有开放项**：

1. **个股研究**：趋势估计与 EMA 对照、原始收益波动、固定突破条件，以及同定义历史事件的后续价格变化和失败样本。
2. **双股对比**：共同日期的相对强弱、收益相关与 beta、此前窗口拟合后的当前偏离，直接显示遗漏与不可计算原因。
3. **多股研究**：同一截止日期下的动量、波动、回撤分项与排名；明确成员的板块复用这一流程，显示有效覆盖和样本广度。

已有基础包括本地导入、精确源值保存、数据版本、图表、JSON/Parquet 导出、备份恢复，以及价格通道、ATR、量能、路径效率、确认拐点、分钟聚合和当前池筛选。新增日线算法的定义及评审见 [实施方案](docs/plans/2026-10-11-research-workflows.md)、[算法研究](docs/research/026-causal-signals-and-evaluation.md)和[独立复核](docs/reviews/2026-10-11-research-workflows-review.md)。

一套 Python + TypeScript/React 代码库支持 Linux 与 Windows 的通用研究功能；通达信客户端调用和原生进程控制保留 Windows 专用适配器。仓库为私有仓库，真实行情、账户信息、密钥和本地运行文件均不提交。

## 安装与运行

使用 Python **3.14.0**。Python 依赖按 [requirements-workbench.lock](requirements-workbench.lock) 安装，前端使用 [web/package-lock.json](web/package-lock.json) 和 `npm ci`，不要自行升级到其他版本。

- 后端锁定：DuckDB **1.5.6**、PyArrow **25.0.1**、FastAPI **0.142.2**、Uvicorn **0.54.0**；测试 Pytest **9.1.1**、httpx **0.28.1**
- 前端锁定：React/React DOM **19.3.0**、Lightweight Charts **5.2.1**、TypeScript **7.0.2**、Vite **8.3.2**，其余依赖见 lock 文件
- 本轮 Linux 工具链：Node **24.19.0**、npm **11.9.0**；历史 Windows 构建环境：Node **24.15.0**、npm **11.12.1**，见[依赖记录](docs/qualification/workbench-dependencies.md)。本轮修改仍需 Windows 原生回归

以下命令均在仓库根目录运行，需事先安装对应 Python 和 Node。

### Linux

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -c requirements-workbench.lock -e ".[dev]"
.venv/bin/anatrading --help
(cd web && npm ci && npm run build)
.venv/bin/anatrading --root ./data/local serve --port 8765
```

### Windows PowerShell

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c requirements-workbench.lock -e ".[dev]"
.\.venv\Scripts\anatrading.exe --help
Push-Location web
npm ci
npm run build
Pop-Location
.\.venv\Scripts\anatrading.exe --root .\data\local serve --port 8765
```

打开 <http://127.0.0.1:8765/>。构建后的页面和 API 由同一本机服务提供；`npm run dev` 尚未配置 API 代理。服务持有数据目录的独占锁，普通导入、查询、备份等 CLI 操作须先退出服务；专门通过现有服务发布的采集命令另见后文。不要让 Linux 与 Windows 同时打开网络共享中的同一数据目录。

## 导入自己的数据

当前格式为 `tdx-public-day-v1`、`tdx-public-text-v1`、`baostock-decoded-v0.9.4` 和 `tdx-http-market-v1`。它们各有固定形状；分钟文本须保留已支持的标题、列和页脚，不能把任意 CSV 改名后导入。BaoStock 和 HTTP 格式读取已捕获的响应，普通导入不会自动联网。

例如在服务关闭时导入日线原文件。将路径、证券和市场替换为文件实际来源；身份声明保留为用户声明，不自动成为已核验事实。

```bash
.venv/bin/anatrading --root ./data/local import /path/to/600059.day \
  --format tdx-public-day-v1 --instrument 600059.SH --venue SH --asset-type stock
.venv/bin/anatrading --root ./data/local snapshots
```

Windows 使用同一参数：

```powershell
$imported = .\.venv\Scripts\anatrading.exe --root .\data\local import `
  'C:\行情导出\600059.day' --format tdx-public-day-v1 `
  --instrument 600059.SH --venue SH --asset-type stock | ConvertFrom-Json
.\.venv\Scripts\anatrading.exe --root .\data\local query $imported.snapshot_id `
  --cutoff '2026-09-30'
.\.venv\Scripts\anatrading.exe --root .\data\local export $imported.snapshot_id `
  --format parquet --cutoff '2026-09-30'
```

Linux 的查询和导出参数相同，将返回的 `snapshot_id` 传给 `query`/`export` 即可。界面将它称为“数据版本”；稳定的命令名、字段名和数据库标识保持兼容。

日线截止格式为 `YYYY-MM-DD`，分钟为 `YYYY-MM-DDTHH:MM`，均包含边界。原价格/金额以 Decimal 和精确字符串保留；重复、无法定位与错误记录有单独原因，不自动删点或补零。图形坐标可以使用浮点，原值和下载保持精确表示。浏览器单文件上限 16 MiB，查询范围上限 20,000 条；普通查看可显式指定源序号窗口，递推研究不能借截短历史绕过预算。

离线备份必须写入数据目录外的新目录，恢复也只接受新空目录：

```bash
.venv/bin/anatrading --root ./data/local backup ./artifacts/backup-01
.venv/bin/anatrading restore ./artifacts/backup-01 ./data/restored-01
.venv/bin/anatrading --root ./data/restored-01 snapshots
```

Windows 将可执行文件替换为 `.\.venv\Scripts\anatrading.exe`，其余参数相同。导入成功退出 0，拒绝/失败退出 2，接受取消退出 130；进入提交临界段后返回实际提交结果。恢复目录出现 `.restore-incomplete` 时不得当作可用数据库，保留现场并改用新空目录恢复。

## 通达信 Windows 接入

固定客户端的一次日线获取已有[历史真实验收](docs/qualification/tdx-daily-acquisition.md)，只覆盖报告中的安装、指纹、证券和日期。运行已核验并登录的 x64 客户端及本机服务后，可在另一个终端通过同一服务发布：

```powershell
.\.venv\Scripts\anatrading.exe --root .\data\local acquire-tdx `
  --client-directory D:\tdx_64 --symbol 600059.SH --target-date 2026-09-30
```

示例日期须替换为实际要观察的源日期；命令当前只允许 `600059.SH`、`000001.SZ`。获取失败或客户端任务未知时保留阻断，不能通过重启、换目录或新请求绕过。`read-tdx-minutes`、本地日线缓存和有限调度另有入口，可用 `--help` 查看；入口存在不代表分钟、持续更新、全市场和当前客户端兼容已验收。详见[缓存导入](docs/qualification/tdx-current-cache-import.md)、[分钟观察](docs/qualification/tdx-minute-after-hours.md)、[有限调度](docs/qualification/tdx-daily-schedule.md)。Linux 不执行 Windows 客户端适配操作。

## 测试与当前边界

```bash
.venv/bin/python -X utf8 -m pytest tests -q
(cd web && node --test tests/*.test.mjs && npm run build)
```

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests -q
Push-Location web
node --test tests/*.test.mjs
npm run build
Pop-Location
```

2026-10-11 当前工作区验证：

- Linux Python 全套：**1,274 通过、0 失败、49 跳过、1 项警告**，用时 44.72 s。48 项因缺少私有真实样本跳过，1 项为 Windows 原生进程证据；警告为锁定依赖中的 Starlette/httpx 弃用提示。
- 前端：**72 通过、0 失败、0 跳过**，TypeScript 与 Vite 生产构建通过。构建仍提示主包超过 500 kB，并有 npm 环境配置警告；不据此声称首次交互性能达标。
- [实现后独立复核](docs/qualification/research-implementation-review.md)：9 项对抗测试及合计 160 项定向测试通过，来源证券冲突、复权冲突和已隔离来源资格传递问题已关闭。该范围未发现未解决的阻断项。

上述结果覆盖首版研究实现、HTTP 边界和 Linux 通用修复；跳过项不能计为通过，前端单测及构建也不代替真实浏览器操作。

尚未完成：真实浏览器操作、5,000/20,000 行真实 HTTP 与最大集合性能的完整验收、Windows 原生回归、用户真实导出的逐字段对账，以及严格样本外预测增量。[浏览器验收](docs/qualification/research-browser.md)已获用户授权，但同环境 Chromium 在创建页面前遭本地 socket 权限拒绝，支持的提权重试仍失败；页面未加载、无界面截图，须在具备相应权限的受支持环境补验。性能扩展验证进行中。数据单位、复权、日历、成员历史和历史可得性未知时继续标示限制。首版双股和集合仅允许同一市场，沪/深/京归入同一 A 股市场；跨市场同步规则另行研究。

“计算正确”“真实来源兼容”“有预测或交易价值”分别验收。本轮研究按来源记录做历史描述；因果算法不使用未来柱，也不能证明当前拿到的历史版本在当时已经可得。事件后续价格变化不等于成交收益，双股偏离不等于协整或套利，所选样本广度不等于全市场或历史行业指数。

## 文档

- [当前路线](docs/ROADMAP.md)：近期交付、后续研究和未完成条件
- [总体方案](docs/MASTER_PLAN.md) / [架构](docs/ARCHITECTURE.md)：长期范围和现行约定
- [2026-10-11 实施方案](docs/plans/2026-10-11-research-workflows.md) / [算法定义与文献](docs/research/026-causal-signals-and-evaluation.md) / [竞品工作流研究](docs/research/027-competitor-workflows.md)
- [首版实现独立复核](docs/qualification/research-implementation-review.md)：问题复现、修复复验与仍未验证的范围
- [国内能力矩阵](docs/research/006-domestic-capabilities.md) / [国际能力矩阵](docs/research/007-international-capabilities.md)：广覆盖调研；具体版本与同任务实测仍需补齐
- 历史记录：[早期架构决策](docs/REVIEW_DECISIONS.md)、[数据格式约定](docs/contracts/INITIAL_DATA_CONTRACT.md)、[存储验收](docs/qualification/evidence-core.md)、[图形验收](docs/qualification/workbench.md)、[HTTP 约定](docs/contracts/WORKBENCH_HTTP.md)。旧计数、性能和平台结论只适用于各报告注明的版本与日期
