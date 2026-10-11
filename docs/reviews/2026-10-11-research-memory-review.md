# 033 股票研究内存：独立反方设计审查

日期：2026-10-11 UTC。审查对象：[033 研究](../research/033-research-memory-cost.md)、实际 Store/HTTP/集合/筛选实现及第四片冻结性能证据。审查者只写本文，不改产品或测试、不提交，不执行新的 200k 剖析。

## 1. 当前决定

**最终实现/保留决定：以新增的分阶段工程决定保留 B 的已验证共享驻留与时延改进，并准备发布；原032筛选增量RSS仍为 failed/open，原预注册整体保留条件仍记未达。** 这是在完整结果已知后的明确取舍，详见 §10，不是改变门槛或重新授予全面资源通过。代码与测试继续冻结，发布须另核验提交/版本。

**最终设计决定：接受修订后的033与完整实施计划，允许按候选 B 的窄范围开始测试先行的编码；A 不作前置。** R1–R3 已逐项关闭，见 §7。这是编码前设计批准，不是实现、资源或全部平台验收通过；新的正式大规模资源运行仍须按计划另确认运行窗口。

首次决定为暂缓编码，要求补齐局部异常接缝、共享拆分和预注册测量。以下保留初始质疑、反例及关闭依据。

B 的目标与真实瓶颈匹配：每源完整读取、验证和规范化后，只跨源保留完整 header、全前缀 coverage 与实际 N+1 窗口，消除全部 M 份展开历史的同时驻留。现有计算和解释足以消费这些小产物，没有理由另建来源框架、缓存或算法引擎。

A 可独立正确实现，但其收益仅涉及当前一源的 Python 原始 tuple/JSON 缓冲；调用者仍保留全部展开 queries，整体仍为 O(ΣTᵢ)。DuckDB 原生执行/排序内存也没有随 fetchmany 自动变为 O(batch) 的保证。当前没有证据要求为 A 单独启动一轮正式大矩阵，再重复承担 B 的等价验收。先实现并衡量 B；只有单源峰值仍有实际代价时，才另审 A 或作固定批量的消融对照。

A 还有独立故障顺序边界：旧 `for ... in cursor.fetchall()` 在解第一行 JSON 前先完成全部 fetch；fetchmany 会交错取批和解码。用假 cursor 构造“首批坏 JSON、后批 fetch 抛 OSError”，旧路径先得到 OSError，分批路径先得到 JSONDecodeError。审查者已运行此轻探针。它不否定正常可信持久输入上的结果等价，却阻止笼统承诺任意驱动/解码复合故障顺序全同。将来实施 A 须明确该保证边界；本轮 B 保持 `_research_query` 原样即可避免这项额外风险。

B 的主要风险为错误出现的阶段被提前，不是窗口不足以表达现有结果。该风险可在 HTTP 局部用现有错误边界解决，维护成本无需上升为通用 deferred-exception 框架。以下 R1–R3 是编码前必须落到正文/计划的具体条件。

## 2. 已核证据与不能归因的部分

已全量阅读 AGENTS.md、033、032、筛选资格与独立审查、紧凑读取方案与独立审查、研究性能报告；逐行核对 `research_api.py`、`store.py` 相关读取/查询边界、`universe_research.py`、`research_series.py`、`stock_filters.py`、`pair_research.py` 的身份逻辑、`numeric.py`、owner 错误处理，以及对应预算、投影、筛选错误/调用次数测试。

只读核对仓库外正式 `results.json`、`repeat-results.json`、固定 manifest、benchmark 与阶段诊断脚本、全部四份 memory-phase 记录。两份正式结果 SHA256 分别为 `8e083dce062ad4a10707bbc8a505625d06f1313b98c4d3263695a390f1e56ed3`、`b5e2a832e85f407167852d5085b914adcd137b953b1046c3e77b7baea7e0024f`，与 033 一致。

- N20 的 10×20,000 首轮 universe/filter VmHWM 为 2,202,591,232 / 2,227,519,488 B；复测为 2,217,873,408 / 2,263,478,272 B。+23.77 / +43.49 MiB 均违反原 +16 MiB 条件，保持失败。
- 四次诊断在 `_load` 后已经约 2,053–2,132 MiB；该批运行解释层没有继续抬高高水位。它们支持调查共享加载，但不能确定首次超差的唯一成因。
- 现有局部 tracemalloc 在全 queries/evaluator 已构造后才开始，约 152–658 KB 只能描述随后解释层。它不能为完整请求的 RSS 门槛补发通过。
- 首轮单对延迟失败和稳定 p95 未验继续独立保留；N252 复测负 RSS 差不能消除首轮失败，更不能当作新算法节省的净内存。

独立查阅 [DuckDB Python API](https://duckdb.org/docs/current/clients/python/reference/#duckdb.DuckDBPyConnection.fetchmany) 的 fetchall/fetchmany 说明及 [Python 3.14 tracemalloc](https://docs.python.org/3.14/library/tracemalloc.html) 的启动、current/peak、自身开销说明。前者只规定结果批次读取；后者不追溯启动前已分配的块。本文关于对象存活和可达性的判断另以实际代码和轻探针为依据。

## 3. R1：把异常兼容收敛到既有 HTTP 边界

**初稿编码前阻断。** 033 §6.2 将 Store/OSError/duckdb/Decode/Acquire 等 exception-family 重建留给实现者；它虽然指出了正确风险，却仍可能诱发一套与工作台重复的错误白名单和构造注册器。这样做的复杂度没有必要。

### 3.1 真实准备定义域

`_research_query` 成功返回可信持久输入后，提前执行的 `_at_cutoff`、`daily_bars`、`daily_coverage` 没有 I/O、Store、decoder 或 acquisition 调用。

- `daily_bars` 的显式请求异常只有 period、20k 行数、ordinal window、cutoff。HTTP 的预算、完整 selection 与严格 D 已约束后三项；period 仍须保留原先全部读取后的统一屏障。
- OHLC 的 `decimal_value` 抛出的 NumericError 已在 `_bar` 中转为既有坏槽 reason。缺值、坏价、重复、不可定位、隔离、源冲突属于正常失败证据，不是请求异常。
- 正常 Store 行有明确 dict/list 结构、bounded Decimal 和字符串/NULL label；不应为了任意 Python 对象构造额外通用校验。
- 纯函数仍接受现有合成输入并走原异常路径；HTTP prepared 合同不要反过来修改它的输入定义域。

因此，“真实可达业务错误”和“故障注入下的 HTTP 映射兼容”须分别写明。保留后者不要求保留或重建原异常对象。

### 3.2 具体反例：两枚举或全部 RuntimeError 不够

审查者对现有 `daily_bars` 做 3 行合成故障注入，再经过实际 route 计算边界与 `_safe_store_call`，得到：

| 准备处注入异常 | universe 原 HTTP 结果 | filter 原 HTTP 结果 |
|---|---|---|
| `ValueError('secret')` | 400 `invalid_research_input` | 500 `internal_error` |
| `NumericError('invalid_decimal')` | 400 `invalid_research_input` | 400 `invalid_decimal` |
| `StoreError('raw_object_corrupt')` | 409 `raw_object_corrupt` | 409 `raw_object_corrupt` |
| `OSError('secret')` | 500 `storage_io_error` | 500 `storage_io_error` |
| `RuntimeError('secret')` | 500 `internal_error` | 500 `internal_error` |

这些注入不证明真实 normalizer 会产生对应 I/O 异常；它们证明现有边界顺序和最终安全结果不能用“所有未知均 500”替代。读取中的坏 tokens/checks 仍在计算 ValueError try 外，必须直接由 owner 处理为 500。

### 3.3 可接受的最小接缝

建议只在 HTTP 单来源准备 helper 中捕获提前计算错误，立即经**该路由现有计算 ValueError 边界，再经现有 owner 映射**，最终只保存小型 `(phase, code, status)`。之后在旧阶段新建对应 RequestError。它记录的是已净化的最终 HTTP 结果，不记录 exception class，不做任意异常重建，不储存可执行回放。

最小依赖接线可以是注册研究路由时传入现有 `_safe_store_call`，两路计算 ValueError 处理提取为各自固定小 helper；不复制 `_STORE_CODES`，不把 HTTP 类型下沉到纯公式模块。该单处 workbench 接线必须在实施范围明列，现有 owner 码表与映射规则本身不改。

必须满足：

1. count/read 完全在该捕获边界外；首次 read 失败立即停止，不能为了收集错误再读后续源。
2. 普通准备失败只是暂存待裁决的整体失败，不能返回 unknown、跳过成员或成功响应；后源 raw 失败仍须优先于前源准备错误。
3. 值记录不含原 exception、args、traceback、cause/context、原文、输入行、query、闭包或 generator。禁止把 `exc.with_traceback(None)` 当充分释放保证。
4. BaseException 类的取消/中断不得捕获延期；资源耗尽不要求继续读取以模拟业务多错顺序，必须保持终止/整体失败，不能触发成功降级。
5. 保留旧纯入口的异常类型及顺序；此记录仅存在于内部 HTTP 路径。

审查者以同样的两层现有边界做 inline 弱引用探针：NumericError 的两路结果与上表相同；仅保存 code/status 返回后，本地 row 引用立即消失，无强制 GC。该探针证明局部接缝可行，不是未来产品实现已验收。

## 4. R2：把共享拆分与全体屏障写成可执行计划

**初稿需要补齐，不接受边写代码边决定顺序。** 033 已识别关键顺序，完整 plan 还须明确哪些函数保留、哪些代码只搬一次，以及失败记录在何处消费。

### 4.1 冻结执行次序

1. 路由的权限、参数、规则预算/规范化按旧入口完成；HTTP ids 按旧规则排序。
2. `counts=[...]` 按 ids 执行到成功完成或遇到第一个计数异常；所有计数成功后才判每源/总预算。不能边 count 边按预算早退。
3. 每源完整 `_research_query`，其中 raw、header JSON、cutoff、全 batch NULL count、SQL/行 JSON、selection/query_id、batch_checks 顺序原样。只有读成功的该源才进入单源准备。
4. 单源 helper 提取 header，先做 cutoff 选择并保存 `len(rows)+len(unlocated)`，再 full daily_bars/coverage，保留 D 存在时的末 N+1 窗口。此处不做 identity、metric、ranking、filter source/atom。
5. 所有 read 成功后才统一 period；再按各旧入口先验参数规则，完成全部 identity，之后依次 market mismatch、duplicate symbol、duplicate snapshot。
6. 先按成员序检查全部 cutoff-selection 失败，再判 selected total。normalize/coverage 失败必须留到对应成员原位置。
7. 每成员先消费自己的 normalize/coverage 失败，再算该成员 metric。成员 1 的公式错误必须先于成员 2 的 normalization 错误。
8. 全成员完成后统一排序/广度；filter 完成全部 `_source` 后才共享合同、构造全部 `_member`、计数和身份。不把 source/atom 工作混入逐源准备。

这里“全部”不要求在该阶段已有错误后继续搜索更多错误。读取不能超越首次 read 失败；纯函数的输入顺序、filter 在排序前的 prior-cutoff 检查也不能改。

### 4.2 最小共享实现边界

可接受的提取仅为：既有单成员窗口准备；既有逐成员 metrics 与最后集合排序/广度；既有 filter 的后半段结果组装。公开 pure wrapper 继续先原前置/全部 `_at_cutoff`/总量，再按成员惰性准备与计算，保留旧错误时序。HTTP 完成小型 prepared 列表和屏障后进入同一 metrics/汇总代码。不要各复制一套 universe 或 filter 算法。

纯路径的惰性 iterator 可以持有原 pure 输入，符合既有调用者合同；HTTP iterator 只能遍历已无历史行的小型 prepared，不得捕获原 queries。不要为了共用一个输入类型，给 header 填假的空 rows/unlocated 再冒充完整 query。

header 应明确保存完整非历史部分：`snapshot_id`、`batch_id`、`query_id`、`selection`、`manifest`、`metadata`、`batch_checks`、`counts`、内部 projection 标记。保留 absent/null/未知原值；`batch_id` 虽未被当前公式消费，初稿称完整 header 时应一并列入。元数据可能很大，复杂度必须保留 ΣHᵢ，不能宣称绝对常数空间。

window 的 bar 只含 date、ordinal、OHLC Decimal、reason；共享标量不会反向保活 row。coverage 在 full bars/full prefix 上生成一次后保留；缺 D 时窗口为空，旧 universe.end_date=D 与 filter 实际 start/end=null 均保持。

### 4.3 必须先锁住的具体反例

| 反例 | 预期及其阻止的简化 |
|---|---|
| 前 count=20,001，后 count 抛 snapshot_not_found | 404 snapshot_not_found；阻止逐源预算早退。已用 spy 复现全部 count 先发生 |
| 前源 period/identity/normalize 错，后源 raw corrupt 或坏行 JSON | 后源 read 错优先；不能提前报前源研究错误 |
| 前两股不同市场，第三股身份缺失 | research_identity_unavailable；已用小输入复现，阻止遇第二股即判跨市场 |
| 前股 normalization 错，后股 cutoff-selection 错 | 后股 selection 阶段错先发生；不能统一仅保第一个“准备错误” |
| 第1股 metric 抛错，第2股 normalize 抛错 | 第1股 metric 先发生；现有 spy 仅观察到 normalize1→metric1，未到 normalize2 |
| 同一 prepare 注入上表 ValueError/NumericError，以及读取中的坏 tokens/checks | 分别保持两路状态/安全码；所有原文脱敏，无部分成功 |
| window 外坏槽；NULL token 日期≤D、>D、不可读；非NULL无效日期 | 完整 coverage、batch-unlocated、坏槽及原 ordinal 全同，禁止窗口反推来源完整性 |
| 缺 D、重复 D、窗口中坏价 | 不回退/补槽；空实际窗口身份/端点与旧 golden 全同 |
| 原件首次/重复/空前缀同长篡改、删除、截短 | 每次都拒绝；恢复后全结果与身份相同 |
| 单源正常/selection失败/normalize失败后进入下一源 | 之前完整 rows/unlocated/tokens/checks 已不可达；失败描述无间接引用 |

旧 public query/export 与全部 golden 不动，尤其 query_id、analysis_id、base_analysis_id、source/contract/window/rule 身份、Decimal/Fraction、低 Decimal context、同显示值精确比较、metadata absent/null/applicability。现有 spy 必须迁到真实共享边界；不能绕开旧 spy 后把“0 次”误记作“一次计算”。

## 5. R3：资源测量必须冻结可判断的对照

033 的方向正确，实施计划仍应在运行前确定次数、进程/seed/次序及保留判据。当前不授权或执行新的大矩阵；不能等看完数字后再定义“可复现”。

建议采用以下最小方案，不强制四臂试验：

- 首轮只比较冻结旧实现与 B；输入生成 seed 继续固定 320261011，冻结合成 Store/raw/metadata manifest、实际行数、D/N、六原子规则与全部源码/脚本 hash。数据 seed 与 PYTHONHASHSEED 分别记录。
- 保留 10×5,000、10×20,000、50×4,000，N20/N252，有效/缺D/重复/未定位混合输入。两种上限形状才能区分总行数与最大单源成本。先做小输入 correctness/lifetime，再申请正式资源运行。
- RSS 使用 exec 启动的新进程，禁止继承一个已加载大夹具父进程的峰值。预先选定至少三组匹配的 PYTHONHASHSEED（例如 0、1、320261011），旧/B 和 universe/filter 各自在独立进程运行；固定交替次序，保留每次失败、值和环境，不挑最好 seed 或最好 run。
- 正式 VmHWM 沿用生命周期口径；另记 import/start、Store open、预算后、每源读取后、准备释放后、全组计算后、JSON/请求后、Store close 的 VmRSS/VmHWM/RssAnon。阶段点看不到函数内部所有瞬时峰值，不能把最后一源释放后的 RSS 叫请求峰值；需要时另用外部采样诊断。
- fixture 创建、对照完整 query、golden/oracle 和不变性验证放正式子进程计量之外。尤其不能让测试 harness 保存 baseline 全 queries，再测 B 并误判 B 无收益。
- 时延交错的 O/B 不能同时打开同一 Store 目录，现有 `_DirectoryLock` 会拒绝第二个 owner；也不能在一个解释器里热换同名产品模块冒充源码独立。采用各自源码进程与相同冻结 Store 的独立目录副本，串行执行、计时在各进程的完整 ASGI 请求内；正式 RSS 仍用另一批全新单次进程。副本的原件/逻辑查询指纹必须一致，没有 running attempt 触发启动恢复差异。
- Python 存活量另开插桩进程，在准备前启 tracemalloc；报告 current、peak 与 tracer 自身开销，单源前后沿同样阶段采样。它不等于 DuckDB/native 或 RSS，插桩 RSS 不与非插桩基线混比。
- 弱引用/可达性测试先于 RSS：下一源开始时上一源的完整行对象不可达；正常与延期错误均覆盖；持有 bar 数≤M(N+1)。测试只保弱引用，不能用强引用 monitor 自己制造驻留。不得用每源 `gc.collect()`、malloc trim 或缓存跳过 raw 来改善产品数字。
- 同一请求完整 ASGI 另做原定预热一次加五对交错时延；新旧 B 对照与 B 内 filter/universe 差额分开。原 032 的≤16MiB、逐对及中位≤1.15×baseline+20ms、解释层≤20ms、增量≤256KiB/总≤512KiB 原门槛一项不删。
- B 的资源保留条件应在正式跑前冻结，例如两种上限形状、两个 N、两路在全部预注册独立对照中峰值均低于旧实现，并给最小/中位节省与完整ASGI退化检查；出现交叠或反例时记“结构下降已证，RSS改善未建立”，不要加跑到通过。可另选有理由的判据，但必须先定再测。

没有依据预承诺最终某个 MB、倍数或响应 SLA。即使 B 使共享驻留显著降低，也需单独核对 filter 的增量资格；所有旧失败留在原记录。稳定 p95、Windows、实际 socket/并发、浏览器及预测/交易收益仍是独立未验事项。

## 6. 本次实际完成与未跑

实际通过：静态完整阅读与代码追踪；两份正式结果 hash/原始数值和四份阶段记录核对；3 行合成的五类异常两路映射、预算优先级、全 identity 屏障、metric-before-later-normalize 反例；局部 code/status 映射的立即弱引用释放探针；假 cursor 对 A 的复合读取故障顺序反例。业务探针均直接运行旧源码，未实现 B；cursor 反例仅比较两种循环的执行顺序。

未跑：新 200k、候选 A/B 性能、全 Python/前端回归、真实行情重算、Windows、浏览器、socket/并发/尾延迟、预测或收益验证。本次没有“跳过项算通过”。第四片 2200 passed/49 skipped 与真实60配置是既有冻结结果，本审查未重新取得这些资格。

审查基线本地 HEAD 为 `41190aa91d3af52c4a75e772fb2579ab4fc044c1`；七份核心源码 SHA256 与 033 所列六份及 owner 相符，owner 为 `00360e8d4241cff4352c3966ef79e00f0521c0da4fa16f0bd76653c5ef8c922b`。首次受审033 SHA256 为 `9c4b5a04d48b05e00eff45a4e88e551b3e2c347d9bd7be1190aac3b8e23db592`。

## 7. 作者回应与最终复核

2026-10-11 06:44 UTC，已完整读取并核对作者修订的[实施计划](../plans/2026-10-11-research-memory.md)与033，不以沟通中的摘要代替正文复核。

| 项目 | 修订及复核决定 |
|---|---|
| R1 | 计划 §4 删除 exception-family 重建，明确当前真实准备定义域、两路固定 guard→现成 `_safe_store_call`→只取 code/status。read/count 保持在捕获外，纯模块不知 HTTP，workbench 只在注册点传函数，不嵌套 owner 调度、不复制码表。universe guard 仍只包报告计算，envelope/身份在外；filter guard 仍包含报告组装/身份。故障矩阵与轻探针一致。关闭。 |
| R2 | 计划 §2–§5 明确完整 header（含 batch_id）、selection/normalization 两类延后错误、全部 identity/selection 屏障和逐成员 normalize→metrics；pure 保持逐成员惰性准备，HTTP 才预备小记录，共享同一指标/汇总/filter组装。先锁旧 golden/反例/对象生命周期，再接入并全量回归。关闭。 |
| R3 | 计划 §6 冻结 old/B 两臂、六配置、每路预热+五次交错时延、0/1/320261011 三个 hashseed 共72个新进程 RSS。时延用两个固定源码长期child及独立匹配Store副本，唯一写入者不绕过；正式RSS另exec且每进程单次请求。阶段RSS/tracemalloc单列，基线/O/B模块hash与输入/原件指纹核验，三组峰值方向及完整ASGI门槛明确，032旧门槛与失败不改。关闭。 |

MemoryError 仍可能被既有安全边界映射500；本次不承诺灾难资源耗尽时继续读取完成业务多错裁决，也不为它另建识别框架。已经保存的任何错误最终必须使请求失败；BaseException 中断/取消仍不捕获延期。此边界清楚，不授予资源耗尽恢复资格。

本次批准绑定的正文 SHA256：

- 033：`281c7c9065c00361c50a9ab4e02359e641bdb851646443f711f2d163036af5d9`
- 实施计划：`1c1e2fef4e1a55675970b2cf7da833464783dbacb6d1fcb47e4a146c6fa67529`

之后只更新状态/本决定链接不改变批准范围；修改错误、输入、来源或性能门槛须重新复核。代码允许范围为计划列明的research_api、universe_research、stock_filters及workbench单处接线和必要测试；Store/SQL/fetchall/normalizer/numeric、公有接口/导出、单股双股、预算和原件校验不动。

正式实现需再独立审查，取得最终全量回归和预注册资源证据后才能宣称可保留且资源改善。未满足方向性或旧032增量门槛时，记录未达并停止/回退；禁止以重复到通过、改阈值或删来源获得资格。当前未发现剩余编码前设计阻断，仍未写一行产品实现、未跑新200k、未提交。

## 8. 独立实现审查（06:52–06:58 UTC）

**当前功能、来源边界及对象生命周期审查通过，无剩余已知实现阻断。** 可以进行最终冻结全仓回归；资源保留决定仍等待计划中的正式对照，不能把对象释放成立写成 RSS 已改善。reviewer 仅新增 `tests/test_research_memory_adversarial.py` 并追加本文，未改作者产品/测试、未提交。

### 8.1 实际改动与静态复核

- `research_api` 新单源作用域 `_prepare_source`、安全结果捕获、集合预算/读取/裁决入口；两个计算 guard 沿用旧映射。每个源先完整 read，准备错误仅存 code/status，selection 与 normalization 分开；所有源读取/period/身份完成后才按旧阶段消费错误。
- `universe_research` 只提取成员前置、窗口准备和指标/汇总循环，纯入口惰性逐成员准备；HTTP 使用同一计算内核。取 target/window 的关系保持；原指标、精确排名及广度语句没有重写。
- `stock_filters` 分离既有输入前置和组装；所有 source 仍在全部集合指标后，所有 source 又先于任何 filter member。来源元数据、合同共享、Fraction/binary64 条件与所有身份构造原样。
- `workbench` 只在注册点传入现成 `_safe_store_call`。独立与冻结提交 `41190aa` 对照：Store、research_series、numeric、pair_research **逐字节相同**；`_RequestError`、`_safe_store_call`、`_StoreThread` 的 AST **完全相同**。
- 旧 `test_stock_filters_adversarial.py` 仅将一次共享计算 spy 移到 `_evaluate_members`、计算故障注入移到 `_assemble_filter`；逐码、安全400/500、脱敏、调用次数等原断言没有删掉。新 HTTP 路径确实触发这些共享边界。

作者自查补充 `zip(..., strict=True)`，防止内部 prepared/成员长度不一致时静默少成员返回成功。作者已有先失败后通过的反例，本次联合复验包含该项。正常 pure/HTTP 的长度由旧列表及新逐源记录保证，严格检查未改变合法输入结果。

### 8.2 独立新增的实证

专属文件共 **51项通过，4.42秒，0失败/0跳过**。这些 pytest 项内还包含明确循环矩阵，不能把循环数与51相加宣传为独立测试数。

1. **96份冻结旧完整 JSON 对照。** reviewer 从 `41190aa` 直接读取旧 universe、stock_filters、research_api 源码，绑定旧 evaluator生成16份四成员混合输入×N2/5/252×两路的 JSONResponse 字节摘要。旧参考没有调用新 prepare/evaluate helper。冻结后新 HTTP内部计算与这些摘要完全一致；低全局 Decimal precision=2 下重跑，同输入不被修改，所有 counts 先于 reads。
   - 覆盖缺D、重复、窗口外缺OHLC、行身份冲突、无效非NULL日期、NULL token的截止内/未来/不可读日期、隔离和批次负样本。
   - 保留 manifest/metadata、absent/null/unverified applicability、来源/规则/窗口及全部 analysis 身份；窗口不足、数值、原因、计数都包含在完整 JSON 中。
2. **20种异常保活反例。** 两路×selection/coverage×Acquire/Decode/Numeric/普通ValueError/RuntimeError。异常有显式 cause，原异常 args 持有完整 query，AcquireError.raw 特意持有 rows；跟踪 query、rows/unlocated list、行 dict、tokens/checks/values 容器的弱引用。每次下一源 read 前及函数返回后均立即不可达，未调用 GC、未删失败，也没有原文泄露。
3. **真实 Store 生命周期。** 对正常导入数据的实际 `_research_query` 结果只包弱引用容器，不替代读库；两路各连续两次请求。上一源全历史在下一源 read 前释放；每次恰三次read/raw，重复请求仍验证原件。另跟踪完整 daily_bars 返回的每个 bar，准备后存活数量恰等于实际窗口总数且≤M(N+1)，删除 prepared 后全部释放。
4. **1824个安全映射组合。** 75个现有 owner 白名单码加一个未知码×四种现有代码异常（Store/Numeric/Decode/Acquire）×read/selection/coverage×两路。结果与独立状态公式和原 route ValueError规则逐项相同；读取异常不被误送计算400，universe与filter未知/代码型ValueError差别保持。
5. **阶段顺序与失败整体性。** identity先于selection、period先于identity、market mismatch先于duplicate symbol；全部filter source投影先于任何member；两路envelope ValueError保持原500边界。真实临时Store中前源身份缺失、后源tokens JSON损坏，仍先报后源安全500，且不读取失败源之后的成员。BaseException在selection/normalize/coverage均立即外抛，不延后读下一源。
6. **原件重复与空前缀保护。** 同一个已打开owner先请求成功，再对中间来源做同长篡改、截短、删除；正常D及空前缀D、两路均409对应原错误。恢复原件后整响应字节等于最初成功结果。没有缓存“已验证”状态。

首次运行独立文件为43通过/1失败：reviewer替换 `FROZEN2` 占位符时误同时替换了 `FROZEN252` 的前缀，导致一个不合法预期hash。按已经从旧源码生成并留在运行输出中的252哈希修正后通过；该失败属于测试编辑错误，实际产品输出从首次就等于旧源码哈希，未据新产品刷新参考。随后增加7项生命周期/真实损坏/中断病例，得到上述最终51项。

### 8.3 相关联合复验与冻结

独立实际执行：

```text
.venv/bin/python -m pytest -q \
  tests/test_research_memory.py tests/test_research_memory_adversarial.py \
  tests/test_stock_filters.py tests/test_stock_filters_api.py \
  tests/test_stock_filters_adversarial.py tests/test_universe_research.py \
  tests/test_research_series.py tests/test_research_api.py \
  tests/test_research_projection.py tests/test_research_adversarial.py \
  tests/test_store_query.py tests/test_store_failures.py \
  tests/test_workbench_boundaries.py
405 passed in 36.41s
```

此次 **0失败、0跳过**；405已含作者50项与独立51项，不能重复相加。包括先前关键多错反例、预算、全identity/selection屏障、成员1公式先于成员2normalize、完整源资格及public query/export保护。`git diff --check`通过。

受审最终 SHA256：

| 文件 | SHA256 |
|---|---|
| research_api.py | `71c25a3469a970f68a714406128d230ebcd0886eece44757ee2733e150bf1fc5` |
| universe_research.py | `383dd8d68a7f897ae3fee5483eeae7fe3f45a2ba06cb0600f10374f248ade248` |
| stock_filters.py | `e162e8c5e48c748d68d5a6e3246aef95219a79f156283929ce7702c597463384` |
| workbench.py | `0bc596c11dc23ab36592e9faad28d002b10c54c254fd4a063a3496e843a52077` |
| tests/test_research_memory_adversarial.py | `fbc2fd7bbfda216ff9fd5d1a19934b844e14537195db3824498ef415fe684b9a` |

最终全仓回归由作者在测试全部冻结后另行执行；本次405项不替代全仓。正式RSS/时延对照、真实来源新版本重算、Windows、浏览器、实际socket/并发、稳定p95和预测/收益均未在本次运行。旧第四片RSS未达及其它限制保持原样。后续如产品修改，须重验受影响行为并更新受审hash；当前通过仅绑定上表源码。

## 9. 正式资源 harness 静态复核（07:06–07:08 UTC）

**未发现测量设计阻断，允许在父任务已批准的独占窗口内执行预注册对照。** 这次只读核查仓库外 `benchmark.py`（655行）、`diagnostic.py`（124行）、README与冻结源码manifest；未启动请求、重测试或大配置，未改harness。

核对与计划 §6 一致：

- O为`41190aa`的独立git archive；B-final-01工作树快照的四产品文件逐字节等于 §8受审版本，不能仅凭相同HEAD声称代码相同。子进程拒绝预导入产品，并核查实际模块均来自选定源码路径。
- 每配置独立且初始持久内容相同的O/B Store目录；复制时持有原目录锁，打开前只读检查running attempt、WAL/incomplete restore。长期child各自固定一个版本/root，父串行发请求；原件与完整/截止公开query前后单独检查。
- 每路一次预热与固定五轮顺序正确。`perf_counter_ns`仅包完整ASGI client请求，响应序列化在内；IPC、日志、hash/oracle和磁盘结果写入在外。不删除异常值或声称稳定p95。
- 两个warm worker关闭后，三个固定seed×四路×六配置确为72个新解释器exec，每进程一次请求。正式RSS读取Store关闭后的生命周期VmHWM；不复用warm历史高水位，不携带完整对照夹具，不启tracemalloc。
- 独立oracle执行比完整响应字节；正式样本再核对hash/长度/status。解释层在另一进程预计算共享结果后实测B的输入前置及assemble，不把mock当新HTTP覆盖。阶段/trace诊断单独运行，明确无法证明对象可达性或替代正式VmHWM。
- summary保留全部旧/B时延、三组RSS方向、B filter/universe的16MiB及逐对/中位时延、20ms解释层、256/512KiB响应门槛。任何结果文件保留原值，最终qualification不由harness自动授予；失败写独立记录，不覆盖旧失败。

脚本语法解析通过；受审SHA256：benchmark=`2401167af02be64f99cdb42eea4d8e7f6ff99da7c4c9940886dc9a12cb2de014`，diagnostic=`d4d0f44dbf192645c25511702ad0993feb61bc601c08f9fc80b3610ac41b08c3`。首次阅读时README仍有早期“未授权/未冻结/B未验”状态；07:08复核已更新授权/小B及最终正确性状态，旧清单另留，脚本hash不变。正式资源结果尚未到达，本节不给性能通过结论。

## 10. 正式资源独立重算与新增分阶段保留决定（08:00–08:05 UTC）

### 10.1 原预注册资格结论：整体保留条件未通过

reviewer已直接读取正式 `manifest.json`、全部 `raw-values.jsonl` 和 `results.json`，自行重算门槛，没有调用harness的`summarize`生成结论，也没有重跑请求或额外大诊断。

- 六配置及其顺序、每配置四路一次预热和固定五轮时延次序全部符合manifest/计划。实际120个正式时延、24次预热、72个单次exec RSS齐全；72个RSS PID互异，hashseed按0/1/320261011，均未启tracemalloc。
- 每个已记录产品模块来自正确O/B目录且SHA匹配源快照；冻结脚本和全部旧输入/既有失败证据hash未变。O/B初始Store持久字节一致；前后raw、公开完整与截止query、成员/行数、attempt状态指纹一致。
- 直接读取24份独立oracle JSON文件，旧/B完整字节相同；全部正式与预热样本的hash、字节数、状态都等于对应oracle。因此本次比较包括全部query/analysis/source/window等响应身份，没有只比较三项浮点指标。
- 36个旧/B同seed峰值对全部降低；两种200k形状24对降低 **68.211993%–83.895098%**。新B的上限矩阵峰值约323–655MiB，旧O约1955–2162MiB。小矩阵也逐项下降。该结论只适用于这组冻结输入、环境和方法，不能外推绝对内存上限。
- 60个旧/B时延对、12组旧/B中位、30个B内部filter/universe时延对及六组中位全部达到冻结门槛。全部解释层最大值≤5.748ms，响应增量及总量均在256/512KiB内。200k中位仍约9.4–9.8秒，不称即时交互或稳定尾延迟。
- 唯一未达项是原032的同seed、独立进程F−U生命周期VmHWM≤16MiB；18对有4对未达，覆盖三个配置。独立整数重算与作者每一项门槛布尔值完全一致。

| 配置 | hashseed | F−U精确字节 | MiB | 原门槛结果 |
|---|---:|---:|---:|---|
| 10×5,000 / N20 | 1 | 19,120,128 | 18.234375 | 未达 |
| 10×20,000 / N20 | 320261011 | 121,065,472 | 115.45703125 | 未达 |
| 10×20,000 / N252 | 0 | 23,203,840 | 22.12890625 | 未达 |
| 10×20,000 / N252 | 320261011 | 86,839,296 | 82.81640625 | 未达 |

**依照原冻结计划，不存在“整体保留条件通过”的结论。** 其余14个增量对通过、若干负差、所有旧/B绝对峰值大幅下降、已证明的对象释放，以及小型解释层成本，均不能抵消这四项失败。未修改16MiB、删除样本、挑seed或复跑求绿。独立进程差额不足以唯一归因于解释算法，也不足以唯一归因于allocator/数据库；本次没有补造因果结论。

独立只读重算记录保存在仓库外 `anatrading-memory-research-2026-10-11/independent-resource-audit.json`。其作用是复核已有结果，不是一轮新资源试验。

### 10.2 最终正确性证据核对

在本次作保留建议前，reviewer另只读核对最终Python日志及其证据hash：**2301 passed / 49 skipped / 1 warning，90.33秒，退出0**；109个源码/测试文件当前字节逐项匹配冻结清单。Node/TypeScript/Vite证据返回码均0，前端54文件无变化。真实矩阵结果文件hash与正确性manifest相同，记录60配置、240次filter+20次universe、0网络采集及0规则调整、status=passed。该核对承接作者/真实验证执行者的记录，不声称reviewer再次运行全仓或私有行情。

完整测试、真实兼容和正式资源绑定同一 §8 产品hash。49个skip、Windows、真实浏览器/socket/并发、稳定p95和预测/收益仍保留各自未验状态。

### 10.3 独立建议：新增受限保留决定，不重判原资格

reviewer的实质建议是 **retain-with-explicit-open-gate**：保留这一共享来源生命周期改进，同时将筛选增量RSS继续标为failed/open。该建议是看完完整结果后的工程取舍，明确超出原计划“全部门槛满足才保留”的自动推进条件；它不能倒填成预注册成功。

依据是面向当前使用的具体收益与风险：

1. 在功能、来源、全部身份和失败顺序不变的前提下，36个直接旧/B峰值比较都降低，并且全部中位时延更快。两种上限形状、两个N、两路、三个固定seed共同支持该收益；并未仅选最有利配置。
2. 旧已发布版本本来就有16MiB增量未达，原资格文件完整保留。回退B会恢复本轮实测明显更高的整体驻留，也不会让旧筛选的该项资格自动成立。对现有本地单owner研究请求，舍弃已验证收益没有已知安全或结果正确性收益。
3. 未达项的实际风险仍要接受：不同进程F/U峰值差曾达到115.46MiB；B并没有“筛选仅增加≤16MiB”的保证。约323–655MiB只是本次上限矩阵观察范围，单行JSON/header可变，不能据此承诺任意输入或低内存机器不发生内存压力。9–10秒请求仍可能占用owner并形成等待。
4. 没有发现可复现的来源/数值/错误/释放回归需要在发布前修复；现有证据也不足以给出一个确定的“修某算法即可关门槛”方案。无依据改代码、加入GC/缓存或不断复测会增加风险，不能为了报绿这样做。

因此，新增决定只承认“功能与来源兼容通过；本固定矩阵共享内存和时延改善成立；筛选增量资源仍未达”。保持原预算、原件每请求校验、完整前缀和所有测试；不得对用户宣称全资源通过、绝对内存上限、跨平台/尾延迟或预测收益资格。

### 10.4 父任务明确采纳与后续边界

2026-10-11 08:03 UTC，父任务明确采纳上述新增分阶段保留建议，决定 **保留并准备发布B的已验证共享驻留/时延改进；032筛选增量RSS仍failed/open，原整体保留条件仍记录未达**。依据为全部36对绝对峰值下降、旧版已有相同增量资格缺口及兼容性证据；这是后验工程取舍，不更改预注册门槛或原始结果。

据此解除本片文档中的“最终保留待决”。本审查允许按该受限资格保留，不自动宣布已发布；提交、分支、PR/合并及发布版本仍由父任务另核验。源码/测试必须保持上述冻结状态直到发布验证，真实源/派生数据不能入库。

当前不追加一轮正式矩阵或大型剖析。如果以后需要关闭16MiB门槛，先另定有界定位任务，例如固定已经失败的10×20,000/N20/seed320261011，分别观察两路在单源读取、准备返回、集合完成和组装前后的阶段高水位，区分峰值发生位置；诊断自身可能影响分配，不能拿它替代正式资格。只有取得具体可验证的原因及最小改动后，再预注册必要对照。不得无限重跑寻找通过值，也不得将这项开放问题升级为新缓存/并行/通用框架项目。

本阶段正式文件SHA256：manifest=`1730557cc52a964f2fa15653440846526d47c393ba954cc5f16ce3f3c7aa4c86`；raw-values=`fa7bd6e18a698643ee1f38ea1232e31919801bf7dc3cd9cae6440d8da1cfea4f`；results=`06ba74cc7ba99aabdcd69cf2f1eb18fb240fd3fda7b62a117a02707f306b9f97`。本次最终核对没有产品改动、没有新资源运行、没有提交或发布。
