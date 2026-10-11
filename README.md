# Anatrading

用本地行情研究股票：看清单股趋势与量价变化，比较两只股票的关系，再检查一组股票或板块样本的强弱与覆盖。优先服务 A 股日线波段和分钟复盘，逐步扩展到国际股票、中长期择时与组合研究。

**长期目标：数据分析能力对标 TradingView 高级功能，并在分析深度和功能丰富度上显著超越 TradingView。** 架构与算法路线按这一目标设计，循序渐进地研究、实现和验证。该目标不代表当前已经达到；具体能力、任务效果与性能提升须有可复核的证据，当前完成范围以下文为准。

本轮已接通三个首版日线研究流程，**Linux 自动化回归通过，完整验收仍有开放项**：

1. **个股研究**：趋势估计与 EMA 对照、原始收益波动、固定突破条件，以及同定义历史事件的后续价格变化和失败样本。
2. **双股对比**：共同日期的相对强弱、收益相关与 beta、此前窗口拟合后的当前偏离，直接显示遗漏与不可计算原因。
3. **多股研究**：同一截止日期下的动量、波动、回撤分项与排名；明确成员的板块复用这一流程，显示有效覆盖和样本广度。

已有基础包括本地导入、精确源值保存、数据版本、图表、JSON/Parquet 导出、备份恢复，以及价格通道、ATR、量能、路径效率、确认拐点、分钟聚合和当前池筛选。新增日线算法的定义及评审见 [实施方案](docs/plans/2026-10-11-research-workflows.md)、[算法研究](docs/research/026-causal-signals-and-evaluation.md)和[独立复核](docs/reviews/2026-10-11-research-workflows-review.md)。

第二批已完成内部紧凑读取和[分钟采样诊断 A](docs/research/028-intraday-research-candidates.md#9-a-纯函数实现记录2026-10-11)。紧凑读取保留公开查询、导出、精确源值与研究身份；分钟 A 仅为已复核的单日期来源模板纯函数，尚未接入 API 或界面，也不提供实时分钟功能。第三批已实现腾讯日线/新浪分钟的有界取数、恢复和离线捕获导入，本地测试与独立实现复核通过；40 份旧真实捕获已完成离线入库对账，新命令的真实联网仍受阻，详见下文。

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

原有四种格式为 `tdx-public-day-v1`、`tdx-public-text-v1`、`baostock-decoded-v0.9.4` 和 `tdx-http-market-v1`；新增 `tencent-daily-capture-v1`、`sina-minute-capture-v1`，读取带请求与来源字节的固定捕获格式。它们各有固定形状；分钟文本须保留支持的标题、列和页脚，不能把任意 CSV 改名后导入。普通 `import` 只读取本地文件，不自动联网。

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

## 腾讯日线与新浪分钟取数

第三批已实现 `acquire-public` 和 `resume-public`，仅支持显式声明为股票的沪深证券：腾讯日线按指定日期范围分块，新浪 1m/5m 读取最近窗口。代码和交易所格式通过不等于证券品类已核实；请求未复权也不自动证明来源调整口径。

在服务关闭时使用以下 Linux 命令示例；日期和证券须按实际任务修改：

```bash
.venv/bin/anatrading --root ./data/public acquire-public \
  --source tencent --symbol 601577.SH --asset-type stock --period 1d \
  --start 2026-10-01 --end 2026-10-09
.venv/bin/anatrading --root ./data/public acquire-public \
  --source sina --symbol 601577.SH --asset-type stock --period 1m --count 10
.venv/bin/anatrading --root ./data/public resume-public RUN_ID
```

`RUN_ID` 替换为原任务返回值，仅在结果允许恢复且原因已核清时使用。腾讯一次范围最多 310 个自然日、按最多 31 日分块；新浪 count 为 1–240，默认 10，不接受历史起止日期。每任务最多 10 次发送，跨恢复累计；失败会停止，不能靠新任务、换目录或换来源绕过阻断。原件保留全部返回上下文，目标区间视图不删原始行，也不自动拼接多个数据版本。

当前验收分开记录：

- 40 份旧捕获按独立旧记录版本导入、重复复用和关闭重开后逐字段核对通过。保留 38,900 条源行；目标视图 34,205 条，差额为较早日线上下文。分钟数据只是近期窗口。原始数量字符串保留，数量/金额单位未认证，不据此开放量能或 VWAP。
- 新命令真实联网的首个腾讯日线请求返回 `transport_network_error`，未取得响应、捕获或数据版本；发送计数持久保留为 1，新浪未发，也未重试。具体网络原因尚不确定，旧脚本成功不能证明新命令网络链路通过。
- 当前新采集命令要求可靠的目录级安全读写与同步能力；Windows 会在联网前因能力不足拒绝，尚无 Windows 自动采集通过结论。原有通用导入、存储与研究功能的跨平台范围不变。

详细实现范围与证据见[自动取数方案](docs/plans/2026-10-11-automatic-market-data.md)、[格式和来源验收](docs/qualification/public-market-formats.md)、[新命令真实验收](docs/qualification/public-acquisition.md)、[独立实现复核](docs/reviews/2026-10-11-automatic-market-data-review.md)。没有持续调度、全市场下载、完整历史分钟或来源可用性保证。

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

2026-10-11 第三批工作区冻结版本验证：

- Linux Python 全套：**1,937 通过、0 失败、49 跳过、1 项警告**，用时 68.86 s。48 项因缺少私有真实样本跳过，1 项为 Windows 原生进程证据；警告为锁定依赖中的 Starlette/httpx 弃用提示。
- 前端本片未修改；最近一次验证为 **72 通过、0 失败、0 跳过**，TypeScript 与 Vite 生产构建通过。构建仍提示主包超过 500 kB，并有 npm 环境配置警告；不据此声称首次交互性能达标。
- [首版实现复核](docs/qualification/research-implementation-review.md)已关闭来源冲突和隔离资格问题；[紧凑读取复核](docs/reviews/2026-10-11-compact-research-reads-review.md)300 项定向测试通过；[分钟 A 复核](docs/reviews/2026-10-11-intraday-candidate-review.md)接受限定纯函数，相关 124 项测试通过。这些定向结果已包含在全套中，不累计相加。
- [自动取数独立复核](docs/reviews/2026-10-11-automatic-market-data-review.md)：全部 public 测试 455 项通过，其中独立对抗测试 173 项通过；已包含于全套，不累计相加。真实离线入库和新网络失败如上单列。
- 第二批[性能复验](docs/qualification/research-performance.md#内部紧凑读取复验当前实现)：39 次正式 ASGI 请求通过，完整/紧凑读取结果、来源原件和身份一致，主矩阵响应与旧基准逐字节相等。200,000 行集合中，10×20,000 的中位耗时由 15.298 s 降至 11.988 s，50×4,000 由 14.719 s 降至 12.888 s；各三次测量，仍有十余秒等待，未含真实网络或浏览器。

上述结果来自本地冻结版本验证，仓库尚未配置 GitHub CI。它们覆盖首版研究、内部紧凑读取、分钟 A 纯函数、新有界取数及格式、HTTP 边界和 Linux 通用修复；跳过项不能计为通过，前端单测及构建也不代替真实浏览器操作。

尚未完成：新取数命令的真实网络成功链路、真实浏览器操作、研究接口的实际 socket/网络 HTTP、并发等待/尾延迟与峰值内存、Windows 原生回归、用户真实导出的逐字段对账，以及严格样本外预测增量。[浏览器验收](docs/qualification/research-browser.md)已获用户授权，但同环境 Chromium 在创建页面前遭本地 socket 权限拒绝，支持的提权重试仍失败；页面未加载、无界面截图，须在具备相应权限的受支持环境补验。合成性能的有限优化保留条件已通过，交互响应目标仍未验收。数据单位、复权、日历、成员历史和历史可得性未知时继续标示限制。首版双股和集合仅允许同一市场，沪/深/京归入同一 A 股市场；跨市场同步规则另行研究。

“计算正确”“真实来源兼容”“有预测或交易价值”分别验收。本轮研究按来源记录做历史描述；因果算法不使用未来柱，也不能证明当前拿到的历史版本在当时已经可得。事件后续价格变化不等于成交收益，双股偏离不等于协整或套利，所选样本广度不等于全市场或历史行业指数。

## 文档

- [当前路线](docs/ROADMAP.md)：近期交付、后续研究和未完成条件
- [总体方案](docs/MASTER_PLAN.md) / [架构](docs/ARCHITECTURE.md)：长期范围和现行约定
- [2026-10-11 实施方案](docs/plans/2026-10-11-research-workflows.md) / [算法定义与文献](docs/research/026-causal-signals-and-evaluation.md) / [竞品工作流研究](docs/research/027-competitor-workflows.md)
- [首版实现独立复核](docs/qualification/research-implementation-review.md) / [紧凑读取复核](docs/reviews/2026-10-11-compact-research-reads-review.md) / [性能复验](docs/qualification/research-performance.md)
- [自动取数方案](docs/plans/2026-10-11-automatic-market-data.md) / [来源研究](docs/research/029-automated-ashare-data.md) / [格式与来源验收](docs/qualification/public-market-formats.md) / [新命令真实验收](docs/qualification/public-acquisition.md) / [独立复核](docs/reviews/2026-10-11-automatic-market-data-review.md)
- [分钟候选及 A 纯函数](docs/research/028-intraday-research-candidates.md) / [分钟独立复核](docs/reviews/2026-10-11-intraday-candidate-review.md)：B/C 仍为研究候选，A 尚无 HTTP/UI
- [国内能力矩阵](docs/research/006-domestic-capabilities.md) / [国际能力矩阵](docs/research/007-international-capabilities.md)：广覆盖调研；具体版本与同任务实测仍需补齐
- 历史记录：[早期架构决策](docs/REVIEW_DECISIONS.md)、[数据格式约定](docs/contracts/INITIAL_DATA_CONTRACT.md)、[存储验收](docs/qualification/evidence-core.md)、[图形验收](docs/qualification/workbench.md)、[HTTP 约定](docs/contracts/WORKBENCH_HTTP.md)。旧计数、性能和平台结论只适用于各报告注明的版本与日期
