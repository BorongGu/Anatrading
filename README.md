# Anatrading

用本地行情研究股票：看清单股趋势与量价变化，比较两只股票的关系，再检查一组股票或板块样本的强弱与覆盖。优先服务 A 股日线波段和分钟复盘，逐步扩展到国际股票、中长期择时与组合研究。

**长期目标：数据分析能力对标 TradingView 高级功能，并在分析深度和功能丰富度上显著超越 TradingView。** 当前功能与验证范围如下，尚未达到这一目标。

当前已接入界面的功能（含045分钟历史记录）：

- **个股日线**：趋势与 EMA 对照、价格波动、固定突破及历史事件结果；检索旧路径、叠图，查看相邻原价。
- **双股日线**：相对强弱、收益相关与 beta、此前窗口拟合后的当前偏离；可展开历史相关与 β，按最新到最早每页50条核对全部共同日期、窗口、有效区间及独立缺失/覆盖原因。使用共同区间对数变化，[显示范围与验收](docs/qualification/062-pair-history-table.md)单列。
- **多股日线**：动量、波动、回撤与排名，条件筛选和双参考组解释（后者仅支持腾讯日线格式）；明确成员的板块复用这一流程，保留覆盖和失败行。
- **双窗相关检索**：多股页明确选择2–50个版本、目标股与截止日，在共同121端点上并列前60和当前60区间的全部候选、有符号相关、精确并列及原数据回查；使用简单源价变化，与旧双股log口径不同。合成链及固定8份来源、两组的有限真实兼容已核对；浏览器、性能与市场效果仍未验，见[范围](docs/qualification/peer-neighbor-workflow.md)。
- **全成对双窗相关**：多股页显式选择2–50个版本与截止日，无需目标股；一次核对两个60区间的全部成员对，常量与来源失败完整保留，两窗折叠、50对分页及双方原记录回查。当前通过合成/API、DTO/SSR与控制器有限验收；真实来源、实际浏览器、性能与金融效果未验，见[实施与边界](docs/reviews/2026-10-13-complete-pair-implementation.md)。
- **分钟记录**：在现有1m/5m详情中指定两个 HH:MM 标签，查看所选来源日及此前最多五个来源日期的端点收盘价与变化比例（两端共用价格尺度时）；缺失或坏日保留。

基础功能包括本地导入、精确原值、数据版本、图表、JSON/Parquet 导出和备份恢复，以及价格通道、ATR、量能、路径效率、确认拐点、分钟聚合和当前池筛选。其余离线实验、已停止的方向及各阶段结果见[研究记录](docs/research-status.md)。

[安装与运行](#安装与运行) · [导入数据](#导入自己的数据) · [测试与限制](#测试与当前边界) · [后续路线](docs/ROADMAP.md)

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

`npm run build` 同时为构建的 JS/CSS 生成内部 gzip 文件与完整性清单；复制构建产物时须保留整个 `web/dist`（含隐藏文件）。单个原件或压缩件超过 2 MiB 会使构建失败。旧 dist 缺清单时普通公开文件仍按原方式发送；歧义文件名/路径、内部目标别名，以及多硬链接的旧静态普通文件统一拒绝（404），正常单链接文件与指向普通公开文件的符号链接保留；存在无效清单时启动失败，应重新构建。服务运行期间请勿更新构建目录，停止服务后替换完整目录并重启。目标 JS/CSS 使用独立 ETag，忽略 Range 与日期验证器；API、HTML 和导出不压缩。减少的是可接受 gzip 的传输字节，浏览器耗时和 Windows 原生尚未验收，见 [061 合同](docs/research/061-bounded-static-compression.md)。

首次使用可点击“导入第一份行情”，选择支持的文件及格式；导入后在“个股研究”中选择数据版本，设置“研究截止”，点击“更新图表”。

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

仅需检查已有数据库时，`snapshots`、`attempts`、`query`、`export`、`candle-geometry` 可显式加 `--read-only`：

```bash
.venv/bin/anatrading --root ./data/local snapshots --read-only
```

这一模式不新建或初始化数据库、不迁移或恢复导入状态，仍为 `running` 的记录按原状返回；缺库或不兼容结构会拒绝。它仍持有原目录排他锁，须先退出服务，也不承诺整个目录零写入；`export --read-only` 仍会生成导出文件，并拒绝数据库、恢复标记和锁等保留路径及其子路径/符号链接别名。默认命令和 HTTP/工作台未切换为此模式，见[显式只读方案](docs/plans/2026-10-11-read-only-store.md)。

日线截止格式为 `YYYY-MM-DD`，分钟为 `YYYY-MM-DDTHH:MM`，均包含边界。原价格/金额以 Decimal 和精确字符串保留；重复、无法定位与错误记录有单独原因，不自动删点或补零。图形坐标可以使用浮点，原值和下载保持精确表示。浏览器单文件上限 16 MiB，查询范围上限 20,000 条；普通查看可显式指定源序号窗口，递推研究不能借截短历史绕过预算。

离线备份必须写入数据目录外的新目录，恢复也只接受新空目录：

```bash
.venv/bin/anatrading --root ./data/local backup ./artifacts/backup-01
.venv/bin/anatrading restore ./artifacts/backup-01 ./data/restored-01
.venv/bin/anatrading --root ./data/restored-01 snapshots
```

Windows 将可执行文件替换为 `.\.venv\Scripts\anatrading.exe`，其余参数相同。导入成功退出 0，拒绝/失败退出 2，接受取消退出 130；进入提交临界段后返回实际提交结果。恢复目录出现 `.restore-incomplete` 时不得当作可用数据库，保留现场并改用新空目录恢复。

## 腾讯日线与新浪分钟取数

`acquire-public` 和 `resume-public` 已实现，仅支持显式声明为股票的沪深证券：腾讯日线按指定日期范围分块，新浪 1m/5m 读取最近窗口。代码和交易所格式通过不等于证券品类已核实；请求未复权也不自动证明来源调整口径。

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

当前限制：仓库内新采集命令的真实网络成功链路尚未验证；首个腾讯请求因 `transport_network_error` 失败，新浪未发。Windows 会因缺少所需目录安全与同步能力在联网前拒绝。40份旧捕获的离线导入已通过，数量/金额单位仍未认证，不据此开放量能或 VWAP。[完整取数记录](docs/research-status.md#取数与扩样记录)保留失败、发送计数和来源范围。

详细实现范围与证据见[自动取数方案](docs/plans/2026-10-11-automatic-market-data.md)、[格式和来源验收](docs/qualification/public-market-formats.md)、[新命令真实验收](docs/qualification/public-acquisition.md)、[独立实现复核](docs/reviews/2026-10-11-automatic-market-data-review.md)。没有持续调度、全市场下载、完整历史分钟或来源可用性保证。

### 后续日线扩样

120股的历史日线原件与独立新库已完成限定核查；自定义业务组和当前成员回顾不代表历史全市场。仓库外采集成功不替代仓库内命令验收，也未增加分钟历史、调度或产品采集入口。详见[数据范围与两阶段结果](docs/research-status.md#后续日线扩样)及[扩样资格](docs/qualification/expanded-daily-data.md)。

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

045阶段完整产品验证于2026-10-11完成，独立代码复审后冻结重跑；432个受检仓库文件回归前后哈希一致。见[研究记录](docs/research/045-minute-label-history.md)及[独立复审](docs/reviews/2026-10-11-minute-label-history-review.md)。

- **045最终冻结回归**：Linux产品 **3,198通过、0失败、49跳过**（48项缺私有真实样本、1项Windows原生证据），全Node **191通过、0失败/跳过**，TypeScript/Vite通过。既有Starlette/httpx警告、npm http-proxy提示及JS主包703.98 kB大于500 kB提示保留；独立针对性检查不累计相加；后续十份保存来源的[进程内完整字段链](docs/research/045-minute-label-history.md#保存来源完整字段链核查)已核对，附加新库物理字节不变条件未通过；浏览器和金融效果仍未验。

随后完成[界面文案整理](docs/reviews/2026-10-11-interface-language-review.md)：最终前端测试196通过，TypeScript/Vite构建通过；只改显示文字、样式注释与对应测试，未重跑后端或浏览器。

2026-10-12修正分钟历史及[九个上下文分析入口的超限提示](docs/reviews/2026-10-12-context-limit-guidance-review.md)：完整版本超过20,000条时，缩小显示窗口无效；双来源对账按可能超限的一侧给出恢复方式，普通查询分页提示保持。该提示修复阶段前端213项、新内存ASGI20项、类型检查与构建通过；当时未重跑完整后端、浏览器、真实行情及性能。

2026-10-12公开发布前，在目标main整合后的最终源码上重新执行完整产品回归：Linux Python `tests` **3,218通过、0失败、49跳过、1项既有警告**（119.66 s）；全Node **213通过、0失败/跳过**，TypeScript及Vite构建通过。49项跳过仍为48项缺私有真实样本及1项Windows原生证据；JS主包705.68 kB大于500 kB、npm配置及Starlette/httpx警告保留。本次未重跑扩展 `qualification`、真实行情、浏览器、Windows原生或金融效果验收；既有失败与未验边界不变。

2026-10-12随后收口分钟历史面板的[响应大小提示](docs/reviews/2026-10-11-minute-label-history-review.md#2026-10-12响应大小提示收口)：历史响应超过2 MiB时，缩小显示源序号窗口无效；可尝试较小来源数据版本，响应仍须满足大小限制。最终全Node **214通过、0失败/跳过**，TypeScript及Vite构建通过；JS主包705.90 kB大于500 kB及npm配置提示保留。本次仅修改局部提示及其测试，未改后端、API、预算、来源资格或算法，未重跑完整后端、浏览器、真实行情、Windows原生、性能或金融效果验收。

2026-10-12接入[共同端点单组](docs/qualification/group-endpoints.md)：多股研究中选择4–50个明确版本和同一a/b，保留N/K、精确正零负、全部失效行与原端点；仅完整组显示mean/median/Q1/Q3。沿030腾讯日线资格，无训练或新来源。合成范围Python **3262通过、1个Windows skip、34 deselected**，另14个真实样本实例随文件ignore未收集；全Node **275通过**、类型/构建通过。后续8份既有腾讯日线、6个固定案例已通过[有限真实来源核对](docs/qualification/group-endpoints.md#后续有限真实来源核对2026-10-12)及独立终审，覆盖精确原token到ASGI、前端DTO/静态SSR与日期前缀；仅含K=4/K=0，保留2份strict/6份legacy原限定与验收脚本失败历史。更多真实类别、浏览器、性能及效果仍未验，合成整套未重跑，不能称未过滤全套通过。

这些是本地冻结版本的自动检查，仓库尚未配置 GitHub CI。跳过项不能计为通过；较早版本的测试数不累计到本次结果。历次失败、修复、资源测试和独立复核完整保留在[研究记录](docs/research-status.md#测试与当前边界)。

2026-10-12新增[049同步双窗有符号相关检索](docs/qualification/peer-neighbor-workflow.md)：最终过滤合成Python **3287通过、1个Windows skip、34 deselected**，另14个真实样本实例随文件ignore未收集；全Node **482通过**、TypeScript/Vite通过。前两轮Python失败、外部runner main守卫修正及保留式临时产物迁移已单列，未改产品期待。独立数值、DTO/控制器和静态SSR核查不替代真实来源、浏览器、性能或真人/市场效果验收。

仍需验证：

- **实际操作**：浏览器视觉、键盘、窄屏、真实 React 交互及真人任务效果。上次 Chromium 在创建页面前遭本地 socket 权限拒绝，页面与截图未完成，详见[浏览器记录](docs/qualification/research-browser.md)。045完整 Query/历史报告、DTO与静态SSR仅覆盖固定十份保存来源，不替代真实浏览器验收。
- **运行与性能**：本轮 Windows 原生回归、研究接口的实际 socket/网络 HTTP、并发等待、稳定尾延迟和峰值内存。筛选内存仍有未达项，已有优化未关闭这些限制。
- **数据与研究效果**：用户真实导出的逐字段核对；未知单位、复权、日历、成员历史和历史可得性；严格样本外预测及交易价值。040条件收益仅通过合成验算，所需独立未复权原价核对仍为0/15。120股入库不扩大既有算法验证范围。

首版双股和集合仅允许同一市场，沪/深/京归入同一 A 股市场；跨市场同步规则另行研究。分钟采样诊断、同伴价格对照、误差与事件审计等仍限离线计算，具体范围见[功能与研究进展](docs/research-status.md#功能与研究进展)。

“计算正确”“真实来源兼容”“有预测或交易价值”分别验收。本轮研究按来源记录做历史描述；因果算法不使用未来柱，也不能证明当前拿到的历史版本在当时已经可得。事件后续价格变化不等于成交收益，双股偏离不等于协整或套利，所选样本广度不等于全市场或历史行业指数。

一套 Python + TypeScript/React 代码库支持 Linux 与 Windows 的通用研究功能；通达信客户端调用和原生进程控制保留 Windows 专用适配器。2026-10-12重新核实GitHub可见性为PUBLIC；用户已授权本批代码与研究文档公开，取代此前等待受众确认的状态。未更改仓库可见性。真实行情、账户信息、密钥和本地运行文件仍不提交。

## 文档

- [研究记录](docs/research-status.md)：各批次实现、离线实验、负结果、测试与完整文档索引
- [当前路线](docs/ROADMAP.md)：近期重点与未完成项
- [总体方案](docs/MASTER_PLAN.md) / [架构](docs/ARCHITECTURE.md)：长期范围与设计
- [TradingView 高级能力路线](docs/research/031-tradingview-advanced-roadmap.md)：长期目标与分步研究计划
