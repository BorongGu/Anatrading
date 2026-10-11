# Anatrading

用本地行情研究股票：看清单股趋势与量价变化，比较两只股票的关系，再检查一组股票或板块样本的强弱与覆盖。优先服务 A 股日线波段和分钟复盘，逐步扩展到国际股票、中长期择时与组合研究。

**长期目标：数据分析能力对标 TradingView 高级功能，并在分析深度和功能丰富度上显著超越 TradingView。** 架构与算法路线按这一目标设计，循序渐进地研究、实现和验证。该目标不代表当前已经达到；具体能力、任务效果与性能提升须有可复核的证据，当前完成范围以下文为准。

本轮已接通三个首版日线研究流程，**Linux 自动化回归通过，完整验收仍有开放项**：

1. **个股研究**：趋势估计与 EMA 对照、原始收益波动、固定突破条件，以及同定义历史事件的后续价格变化和失败样本。
2. **双股对比**：共同日期的相对强弱、收益相关与 beta、此前窗口拟合后的当前偏离，直接显示遗漏与不可计算原因。
3. **多股研究**：同一截止日期下的动量、波动、回撤分项与排名；明确成员的板块复用这一流程，显示有效覆盖和样本广度。

已有基础包括本地导入、精确源值保存、数据版本、图表、JSON/Parquet 导出、备份恢复，以及价格通道、ATR、量能、路径效率、确认拐点、分钟聚合和当前池筛选。新增日线算法的定义及评审见 [实施方案](docs/plans/2026-10-11-research-workflows.md)、[算法研究](docs/research/026-causal-signals-and-evaluation.md)和[独立复核](docs/reviews/2026-10-11-research-workflows-review.md)。

第二批已完成内部紧凑读取和[分钟采样诊断 A](docs/research/028-intraday-research-candidates.md#9-a-纯函数实现记录2026-10-11)。紧凑读取保留公开查询、导出、精确源值与研究身份；分钟 A 仅为已复核的单日期来源模板纯函数，尚未接入 API 或界面，也不提供实时分钟功能。第三批已实现腾讯日线/新浪分钟的有界取数、恢复和离线捕获导入，本地测试与独立实现复核通过；40 份旧真实捕获已完成离线入库对账，仓库内采集命令的真实联网成功链路仍未验证；后续仓库外采集另行记录，详见下文。

第四批已通过后端联合回归与独立实现复核：

- **同伴价格对照 A**：按固定起止日，把目标与剔除目标后的同伴中位数/等权均值比较；目前仅纯函数，无 API/UI。
- **可解释股票筛选**：只读 API 可对动量、波动和回撤设置有限 AND/OR 条件，保留每只股票入选、排除或待核查的依据。已接入多股研究页面，前端模型/静态组件测试、构建与独立实现复核通过；真实浏览器操作和窄屏仍待验。

两项均只描述提供的来源价格和当前所选样本，不能据此推断选股效果或历史行业表现。方法、来源验证及后续路线见 [030 同伴研究](docs/research/030-peer-relative-research.md)、[032 筛选研究](docs/research/032-explainable-stock-filters.md)和[031 高级能力路线](docs/research/031-tradingview-advanced-roadmap.md)。

第五批对多股研究与筛选采用[逐源准备](docs/qualification/research-memory.md)：每只股票仍完整读取并核验历史，再释放不再需要的完整对象，保留完整覆盖信息和实际计算窗口。来源、结果、身份和错误行为保持一致。正式对照中旧/新36个进程峰值配对全部下降，名义20万行配置减少68.21%–83.90%，12个请求中位数均更快；但筛选相对集合的+16 MiB内存门槛仍有4/18未达。已决定分阶段保留这项改善，**这是保留未达项的后验工程取舍，原预注册整体保留条件未通过**。

第六批实现[一步源价格误差诊断](docs/qualification/forecast-diagnostics.md)，仅为纯函数，无新 API/UI。它把 Kalman、沿用上一收盘价（RW）和滞后 EMA 放在相同来源观察上比较，当前误差只与此前60个共同误差对照。**固定30股、2024-10-11至2026-10-09目标视图中，30/30股票的 Kalman 一步 MAE/RMSE 均高于 RW；三组 RW 经验范围虽更窄，平均区间评分仍略差于既有 EWMA 范围。** 本片定位为可复算的误差审计，保留反例；这些结果不支持算法优势宣传或据此推进经验范围界面，也不能外推为所有 Kalman、趋势描述或其它跨度无效。

第七批[突破事件与滞后路径背景](docs/qualification/swing-event-information.md)把既有突破、此前路径效率（ER）与后5来源步的价格标签连在同一事件账本中，保留未选、失败与遗漏，仅提供纯函数。**固定已见的2026内部描述段，ER≥1/2条件的主“未上涨”比例差为+27.30个百分点，14/30股票有两组支持；在同一14股支持集内只保留22/81个可比较事件，遗漏26/30个上涨事件。** 按预定规则，这个方向不获支持，停止扩展该ER条件，不调参挽救结果。本片价值限于完整连接与失败/遗漏审计，无新 API/UI、前向采集或样本外/交易效力结论。

**数据扩样：原组加深与新组扩展同时推进。** 已取得原30股加新增90股的120份日线原件，覆盖14个自定义业务研究组、29个CAPCO行业大类；银行18股、白酒14股，科创12股和创业12股属于另一个板块标签维度。完整120股独立库已通过入库、重复复用、重开及独立终核，原104阶段库保持不变；当前单次多股请求仍最多50成员。详见[数据扩样资格](docs/qualification/expanded-daily-data.md)。扩样没有改产品代码，034/035的算法证据仍只覆盖原30股，既有负结果和资源未验项不变。

第九批[固定双股映射审计](docs/qualification/pair-stability.md)已实现独立纯函数：用此前60个来源区间拟合两股简单价格变化的关系，冻结后在随后20个区间与“目标训练均值”“直接采用同期同伴变化”比较，逐项保留误差和缺失原因。唯一预定的原30股库银行配对中，映射误差低于均值基线、高于直接同伴基线，MSE与MAE方向一致。它需要后段同期同伴价格，只作来源回顾描述；没有新API/UI、经济关系稳定认证或未来预测结论。实现、冻结回归、有限资源与唯一真实来源核对通过独立终审，接受限定离线纯函数发布。

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
- 仓库内采集命令真实联网的首个腾讯日线请求返回 `transport_network_error`，未取得响应、捕获或数据版本；发送计数持久保留为 1，新浪未发，也未重试。具体网络原因尚不确定，旧脚本成功不能证明新命令网络链路通过。
- 当前新采集命令要求可靠的目录级安全读写与同步能力；Windows 会在联网前因能力不足拒绝，尚无 Windows 自动采集通过结论。原有通用导入、存储与研究功能的跨平台范围不变。

详细实现范围与证据见[自动取数方案](docs/plans/2026-10-11-automatic-market-data.md)、[格式和来源验收](docs/qualification/public-market-formats.md)、[新命令真实验收](docs/qualification/public-acquisition.md)、[独立实现复核](docs/reviews/2026-10-11-automatic-market-data-review.md)。没有持续调度、全市场下载、完整历史分钟或来源可用性保证。

### 后续日线扩样

经独立复核的仓库外工具沿已有代理采集腾讯日线，保留默认TLS校验；新增90份实际响应全部取得，合旧30份日线为76,724源行，2024-10-11至2026-10-09目标视图58,045行。14个自定义业务组不等于14个正式行业，当前成员回顾也不代表历史全市场。

原采集阶段75次中74成功、1次网络失败；另行审核批准的补充16次全部成功，其中包含失败项的一次追加尝试。原失败与两阶段账本保留；这不构成仓库内 `acquire-public`/`resume-public` 成功验收。完整120股已在独立新库完成验收，120份数据版本、76,724源行与58,045目标行逐项核对通过，原104股库保持不变。标准捕获格式、运输证据差异、日期缺席与限制见[扩样资格](docs/qualification/expanded-daily-data.md)；未新增分钟历史、调度或产品采集入口。

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

最近一次产品全仓验证为2026-10-11第九批036冻结版本，回归前后183个源码、测试、前端及锁定文件哈希一致；受影响集合与新片测试均为全套子集，不累计相加：

- Linux Python 全套：**2,741 通过、0 失败、49 跳过、1 项警告**，用时 103.19 s。48 项因缺少私有真实样本跳过，1 项为 Windows 原生进程证据；警告为锁定依赖中的 Starlette/httpx 弃用提示。
- [筛选界面验收](docs/qualification/research-filter-ui.md)：全前端 **128 通过、0 失败、0 跳过**，含 15 项独立反例；另 15 类 Python→TypeScript 合成响应桥接通过，TypeScript/Vite 构建及[最终实现复核](docs/reviews/2026-10-11-research-ui-review.md)通过。第九批未改前端，重跑仍为128项及构建通过，前后哈希一致；15类桥接沿用同一界面版本的第四批独立证据。JS 主包 636.49 kB，保留超过 500 kB 的警告；模型/静态组件与桥接测试不证明真实点击、字体、窄屏或加载性能。
- [036固定双股审计](docs/qualification/pair-stability.md)：97项新测试（含57项独立反例）与受影响724通过、10跳过均包含于全套；旧pair完整golden、错误行为和身份不变。一次固定资源矩阵35调用的全部门槛通过：A为每源5k/20k合成输入，完整进程峰值最高232.61 MiB；B为每源≤640行的合法捕获至完整Store读取，最高210.55 MiB；报告最大61,302 B。原B大规模方案因捕获硬限在测前撤回，不能称20k完整Store或任意规模已验；完整RSS增量、稳定尾延迟和跨平台仍未验。唯一真实配对完成4次查询、3次纯调用，来源/账本不变；真人五道判断任务未执行，当前仅核对字段可回答性。唯一真实来源终审通过，接受限定离线纯函数发布。
- [035事件连接验收](docs/qualification/swing-event-information.md)：独立针对性166通过、1项既有私有ER样本缺失跳过，均已包含于全套；14例旧event/signal完整输出分别保持相同。真实30×640共19,200源槽、120次纯调用与170次Store读取对账通过，0新网络；公开/紧凑读取、重复及重开一致，旧源与旧报告不变。固定一次5k/20k结构与次数验收通过；20k新函数中位1.177 s，对照0.514 s，完整JSON为14,908,076 B，对照6,714,481 B。完整审计有实际成本，无资源优势，函数增量RSS仍未验；独立终审及工程决定接受限定离线纯函数审计发布，无默认服务接入，不因程序通过扩展ER条件。
- [034误差诊断验收](docs/qualification/forecast-diagnostics.md)：45项独立对抗、369项相关测试通过，均包含在全套；12份改前完整单股报告及其API结果/身份保持相同。真实30×640共19,200来源槽单遍对账，244个预定用途对应243个唯一纯函数请求；用途结果241可计算、3个预期缺截止日期，公开/内部读取、重算与重开一致，原件未变。5,000/20,000行时延与输出体积满足本片预算；原RSS测量和一次修正测量均无法分辨诊断增量，内存预算仍未验证；依据独立终审，工程决定接受无新API/UI、无默认服务接入的纯诊断范围合并，内存资格继续开放。接入服务前须先补可分辨诊断增量的内存实验；本片不关闭033筛选RSS或稳定尾延迟门槛。
- [033实现与资源验收](docs/qualification/research-memory.md)：51项新增独立对抗、405项相关测试通过，均包含在全套中。真实60配置/260次ASGI复验通过，240份筛选响应与第四批逐字节相同，20次旧集合响应与原参考一致，来源原件、公开查询和账本不变。正式资源对照完整执行120次计时、24次预热及72个独立RSS进程；全部旧/新时延门槛与内存下降方向通过，+16 MiB筛选增量仍有4/18未达，原阈值和全部失败保留。稳定p95、浏览器和跨平台性能仍未验。
- [首版实现复核](docs/qualification/research-implementation-review.md)已关闭来源冲突和隔离资格问题；[紧凑读取复核](docs/reviews/2026-10-11-compact-research-reads-review.md)300 项定向测试通过；[分钟 A 复核](docs/reviews/2026-10-11-intraday-candidate-review.md)接受限定纯函数，相关 124 项测试通过。这些定向结果已包含在全套中，不累计相加。
- [自动取数独立复核](docs/reviews/2026-10-11-automatic-market-data-review.md)：全部 public 测试 455 项通过，其中独立对抗测试 173 项通过；已包含于全套，不累计相加。真实离线入库和新网络失败如上单列。
- [同伴 A 验收](docs/qualification/peer-relative-research.md)：8 个预定真实来源案例，160 个端点中 158 个存在、2 个缺失；两个缺失端点按预期关闭比较，精确有理数对账通过。50 股/200,000 行合成内存输入的单次纯函数约 0.847 s，不代表接口或稳定性能。
- [筛选实现与来源验收](docs/qualification/stock-filters.md)：60 个固定配置、260 次 ASGI 请求、600 次“配置×成员”判定及全部条件/引用核对通过；重复、重开和成员/条件顺序变化不改响应。每成员每次只计数、加载、原件检查与规范化一次。50 成员五种合同重异常响应为 297,975 B，较旧响应增量 252,964 B，体积门槛通过；以下保留第四批原资源记录，不能当作后续批次新测值：六配置中位耗时、新增解释层（最多 5.68 ms）和字节门槛通过；首轮 29/30 个耗时对通过，复测 15/15 通过，首次失败保留。10×20,000/N20 的独立进程峰值 RSS 差两次为 +23.77/+43.49 MiB，超过 +16 MiB 门槛；资源仅部分通过，稳定 p95 未验。
- 第二批[性能复验](docs/qualification/research-performance.md#内部紧凑读取复验当前实现)：39 次正式 ASGI 请求通过，完整/紧凑读取结果、来源原件和身份一致，主矩阵响应与旧基准逐字节相等。200,000 行集合中，10×20,000 的中位耗时由 15.298 s 降至 11.988 s，50×4,000 由 14.719 s 降至 12.888 s；各三次测量，仍有十余秒等待，未含真实网络或浏览器。

上述结果来自本地冻结版本验证，仓库尚未配置 GitHub CI。它们覆盖首版研究、内部紧凑读取和集合逐源准备、分钟 A、同伴 A、一步误差诊断、事件连接与固定双股映射纯函数、筛选只读 API、有界取数及格式、HTTP 边界和 Linux 通用修复；跳过项不能计为通过，前端单测及构建也不代替真实浏览器操作。

尚未完成：筛选真实浏览器交互及窄屏验收、同伴 A 的 API/UI、筛选 RSS/逐对时延稳定资格与 p95、仓库内采集命令的真实网络成功链路、真实浏览器操作、研究接口的实际 socket/网络 HTTP、并发等待/尾延迟与峰值内存、Windows 原生回归、用户真实导出的逐字段对账，以及严格样本外预测增量。034没有新增API/UI，≤8 MiB诊断内存预算仍未验证，当前负结果不支持直接扩展经验范围界面。036保持固定单配对回顾审计，无API/UI；当前120股入库不扩成036多股算法或用户效果验证。035也保持纯函数，ER条件方向不支持；其前向来源条件尚未建立，未启动035前向采集或监控。本次日线扩样仅准备当前取得的历史版本，不补成前向证据。[浏览器验收](docs/qualification/research-browser.md)已获用户授权，但同环境 Chromium 在创建页面前遭本地 socket 权限拒绝，支持的提权重试仍失败；页面未加载、无界面截图，须在具备相应权限的受支持环境补验。第二批紧凑读取保留条件已通过；第五批逐源准备按后验分阶段工程决定保留，原整体条件仍未通过，交互响应目标仍未验收。数据单位、复权、日历、成员历史和历史可得性未知时继续标示限制。首版双股和集合仅允许同一市场，沪/深/京归入同一 A 股市场；跨市场同步规则另行研究。

“计算正确”“真实来源兼容”“有预测或交易价值”分别验收。本轮研究按来源记录做历史描述；因果算法不使用未来柱，也不能证明当前拿到的历史版本在当时已经可得。事件后续价格变化不等于成交收益，双股偏离不等于协整或套利，所选样本广度不等于全市场或历史行业指数。

## 文档

- [当前路线](docs/ROADMAP.md)：近期交付、后续研究和未完成条件
- [总体方案](docs/MASTER_PLAN.md) / [架构](docs/ARCHITECTURE.md)：长期范围和现行约定
- [2026-10-11 实施方案](docs/plans/2026-10-11-research-workflows.md) / [算法定义与文献](docs/research/026-causal-signals-and-evaluation.md) / [竞品工作流研究](docs/research/027-competitor-workflows.md)
- [首版实现独立复核](docs/qualification/research-implementation-review.md) / [紧凑读取复核](docs/reviews/2026-10-11-compact-research-reads-review.md) / [性能复验](docs/qualification/research-performance.md)
- [自动取数方案](docs/plans/2026-10-11-automatic-market-data.md) / [来源研究](docs/research/029-automated-ashare-data.md) / [格式与来源验收](docs/qualification/public-market-formats.md) / [新命令真实验收](docs/qualification/public-acquisition.md) / [独立复核](docs/reviews/2026-10-11-automatic-market-data-review.md)
- [120股日线扩样资格](docs/qualification/expanded-daily-data.md)：原组加深与新组扩展、采集/入库分层及来源限制；不升级30股算法验收
- [分钟候选及 A 纯函数](docs/research/028-intraday-research-candidates.md) / [分钟独立复核](docs/reviews/2026-10-11-intraday-candidate-review.md)：B/C 仍为研究候选，A 尚无 HTTP/UI
- [同伴 A 定义](docs/research/030-peer-relative-research.md) / [同伴验收](docs/qualification/peer-relative-research.md) / [筛选定义](docs/research/032-explainable-stock-filters.md) / [筛选实现复核](docs/reviews/2026-10-11-explainable-filters-review.md) / [筛选验收](docs/qualification/stock-filters.md)
- [多股筛选界面验收](docs/qualification/research-filter-ui.md) / [界面独立复核](docs/reviews/2026-10-11-research-ui-review.md)：模型、静态组件及构建通过，真实浏览器未验
- [033逐源准备研究](docs/research/033-research-memory-cost.md) / [实施方案](docs/plans/2026-10-11-research-memory.md) / [独立审查](docs/reviews/2026-10-11-research-memory-review.md) / [完整验收](docs/qualification/research-memory.md)：相对旧版本改善成立，筛选内存门槛仍开放
- [034误差诊断研究](docs/research/034-causal-signal-diagnostics.md) / [实施方案](docs/plans/2026-10-11-forecast-diagnostics.md) / [独立审查](docs/reviews/2026-10-11-forecast-diagnostics-review.md) / [验收](docs/qualification/forecast-diagnostics.md)：限定纯函数、同槽基线与负结果，无新 API/UI
- [035事件连接研究](docs/research/035-swing-event-information.md) / [实施方案](docs/plans/2026-10-11-swing-event-information.md) / [独立审查](docs/reviews/2026-10-11-swing-event-review.md) / [验收](docs/qualification/swing-event-information.md)：保留完整事件、失败与遗漏，停止扩展本次ER条件
- [036固定双股研究](docs/research/036-pair-relationship-stability.md) / [实施方案](docs/plans/2026-10-11-pair-stability.md) / [独立审查](docs/reviews/2026-10-11-pair-stability-review.md) / [验收](docs/qualification/pair-stability.md)：60/20固定映射与双基线，同期来源描述，无稳定或预测认证
- [TradingView 高级能力与分期路线](docs/research/031-tradingview-advanced-roadmap.md)：长期目标与后续候选，具体新增范围须单独研究复核
- [国内能力矩阵](docs/research/006-domestic-capabilities.md) / [国际能力矩阵](docs/research/007-international-capabilities.md)：广覆盖调研；具体版本与同任务实测仍需补齐
- 历史记录：[早期架构决策](docs/REVIEW_DECISIONS.md)、[数据格式约定](docs/contracts/INITIAL_DATA_CONTRACT.md)、[存储验收](docs/qualification/evidence-core.md)、[图形验收](docs/qualification/workbench.md)、[HTTP 约定](docs/contracts/WORKBENCH_HTTP.md)。旧计数、性能和平台结论只适用于各报告注明的版本与日期
