# 033 股票研究的内存成本与逐源准备候选

日期：2026-10-11 UTC。状态：**静态研究及小输入探针完成，候选B已获[独立编码前批准](../reviews/2026-10-11-research-memory-review.md#7-作者回应与最终复核)；实现与独立实现审查已完成，正式矩阵共享内存/时延通过，原筛选RSS增量及整体保留条件未达；08:03 UTC经独立后验审查与主方决定分阶段保留B并准备发布，失败项保持开放，见[本片验收](../qualification/research-memory.md)。实施范围见[内存优化计划](../plans/2026-10-11-research-memory.md)。** 本文与已冻结的第四片交付分开，不替代其验收，不授权新一轮 200k 长时剖析。

依据：[032 研究合同](032-explainable-stock-filters.md)、[筛选验收](../qualification/stock-filters.md)、[筛选独立审查](../reviews/2026-10-11-explainable-filters-review.md)、[紧凑读取方案](../plans/2026-10-11-compact-research-reads.md)、[紧凑读取审查](../reviews/2026-10-11-compact-research-reads-review.md)和[既有研究性能](../qualification/research-performance.md)。目标是以更短的对象存活期降低相同研究请求的内存成本；公式、资格、完整来源前缀及公开身份均不改变。

## 1. 当前证据及不能推出的结论

本次只读复核已有合成性能 JSON、阶段诊断脚本及资格文档，没有重新执行正式矩阵。

| 已有观察 | 结果及解释边界 |
|---|---|
| 10×20,000、N20 首轮 | universe 中位 13.494 秒，filter 13.684 秒；独立进程 VmHWM 为 2,202,591,232 / 2,227,519,488 B，差 +23.77 MiB |
| 同配置一次完整复测 | 中位 13.618 / 13.964 秒；VmHWM 为 2,217,873,408 / 2,263,478,272 B，差 +43.49 MiB，再次超过既定 16 MiB |
| 10×20,000、N252 | RSS 差首轮 +68.20 MiB，复测 −66.88 MiB，现有高水位差不稳定 |
| 新增条件/解释层 | 在输入及共享 evaluator 已完成后才启动的 tracemalloc，10成员峰值约 152 KB；50成员约 658 KB；不覆盖此前全来源读取或归一化 |
| 另四次阶段诊断 | `_load` 返回时已约 2,053–2,132 MiB RSS，共享 evaluator 增加高水位约 26 MiB；该四次 filter 解释层未再提高高水位 |
| 功能与真实兼容 | 既有最终全仓 2,200 passed / 49 skipped；60 个冻结真实配置通过。均为第四片已有结果，本研究没有重新获得这些资格 |

2.20 GB 是十进制字节数量级，约 2,101 MiB；不要混写 GB、GiB、MiB。200k 是名义上限组，本次既有混合夹具的实际行数略少，10×20,000 为 199,997 行。

上述结果支持优先调查共享加载的活对象及高水位。它们**没有确定首次 RSS 超限的唯一原因**，不能直接把差额算成新算法净占用，也不能把负差当成释放收益。152 KB 的局部测量不能抵消 +43.49 MiB 的正式失败；原首次单对时延未达和稳定 p95 未验同样保留。

## 2. 实际阅读的官方资料

- [DuckDB 1.5 Python API：fetchall / fetchmany](https://duckdb.org/docs/current/clients/python/reference/#duckdb.DuckDBPyConnection.fetchmany)：fetchall 返回全部结果，fetchmany 返回后续一批。该 API 描述没有承诺整个 SQL 执行器只使用一批内存。实际依赖锁定为 DuckDB 1.5.6，本次另用其安装版本做小输入核对。
- [DuckDB Python DB API：结果读取及连接](https://duckdb.org/docs/current/clients/python/dbapi)：分步读取应耗尽结果，连接/查询的生命周期必须保留；不能在未耗尽的同一执行句柄上穿插其它 SQL。
- [Python 3.14 tracemalloc](https://docs.python.org/3.14/library/tracemalloc.html)：只记录开始追踪后纳入追踪的分配，current 与 peak 不同；追踪本身有额外成本，不能代表未追踪的原生分配或完整进程 RSS。
- [Python 3.14 赋值语义](https://docs.python.org/3.14/reference/simple_stmts.html#assignment-statements)：先求右侧再重新绑定左侧；因此 `bars = daily_bars(q)` 求新 bars 时，旧 bars 仍可存活。
- [Python 3.14 traceback](https://docs.python.org/3.14/library/traceback.html)：保存真实 exception/traceback 会保留相关对象引用；无 frame 引用的摘要适合延后诊断。本文不建议在热路径保存 locals 或原始异常参数。

这些资料用于内存与执行顺序分析；本片不引入新的金融公式或预测假设。

## 3. 当前对象存活图与成本模型

设成员数 M、每源完整所选前缀行数 Tᵢ（含未定位行）、总行数 T、最大源 Tₘₐₓ、窗口 N+1、每源保留的元数据大小 Hᵢ。当前 M≤50、Tᵢ≤20,000、T≤200,000、N≤252，均保持。

| 位置 | 当前持有内容 | 可确认的影响 |
|---|---|---|
| `research_api._load` 64–72 | `queries` 保留 M 份完整紧凑 query | 所有 tokens/checks 的展开树、行 dict、OHLC Decimal 在后续计算中一起存活 |
| `store._research_query` 474–484 | `fetchall()` 的完整 Python tuple 列表及编码 JSON 字符串，同时追加展开后的 selected/unlocated | 同一来源的原始读取表示和展开表示在循环期间重叠；之前的来源也仍由 queries 引用 |
| `universe_research._at_cutoff` 34–42 与 evaluator 63 | 每源新 rows 列表，引用原来的 row dict | 是额外引用数组及 query 浅拷贝，不能误称又深拷贝了全部 JSON |
| `research_series.daily_bars` 119–134 | rows tuple、按日期分组的 dict/list、排序日期、全源 bar dict | 一个来源内仍有 O(Tᵢ) 临时结构及 O(Tᵢ log Tᵢ) 排序；bars 的 Decimal 由既有精确规范化生成 |
| `daily_coverage` 141–151 | 又一次 rows tuple 和全源计数扫描 | 只用于当前来源，输出是小型 coverage；完整扫描仍是资格依据 |
| evaluator 68、105–108 | 当前完整 bars，下一次赋值前可能仍持有上一源 bars；evidence 跨源只留窗口及见证 | 032 确实只新增 O(M(N+1)) 的窗口证据，没有跨股保存全部历史 bars |
| `filter_report` 281、283–291 | 排序后的 query 引用、来源摘要、已有 universe/evidence、条件结果 | sorted/by_snapshot 主要增加引用和小对象，不能把全部加载内存归因于条件逻辑 |

用固定行负载作行数复杂度比较：当前 Python 活对象为 O(T + Tₘₐₓ + M(N+1) + ΣHᵢ)。实际主项常为展开 tokens/checks 的 T；不从静态代码推导其精确字节占比。若单行 JSON 大小变化，必须计入相应字节项，不能将 O(行数) 当成固定内存保证。

两处短期重叠也须正视：`q = load(next)` 会在右侧返回前保留旧 q；`batch = fetchmany(B)` 同样可能暂有旧、新两批。用单来源函数作用域或明确结束引用消除前者；后者接受有界约 2B 的瞬时规模，或在取下一批前解除旧批引用。只加 `del bars` 无法消除 queries 的全组 T 主项。

## 4. 候选 A：仅分批取出单源 SQL 结果

最小修改候选：`_research_query` 内把 fetchall 循环改为固定 B 的 fetchmany，保持相同 SQL、相同逐行解码、相同返回映射。建议审查时先冻结 B=1,024 作单个候选；B=1、非整除及边界批次作正确性测试，不能事后遍历大量 B 只挑最好结果。

应保留：mutex/owner、snapshot 与 raw 关联、每次 `_verify_raw`、元数据解码与 cutoff 校验、全 batch 未定位计数、逐行 tokens/checks 验证，以及**所有行之后才验证 batch_checks**的原顺序。不可提前 batch_checks 来改变多错优先级。

读取必须在方法内耗尽到空批次后返回；不能把 cursor/generator 泄露出 mutex，不在未耗尽时做其它 SQL。当前 `self.db.execute(...)` 返回同一连接对象，小探针已验证；禁止对这个所谓 cursor 调用 close 而关闭 Store。中途解码失败后的连接可继续请求、关闭/重开，须专项验证。

另有必须单独审查的故障边界：旧fetchall先完整取完结果再解第一行JSON；fetchmany会交错取批与解码。“早批坏JSON、后批驱动fetch失败”时，前者先报fetch错误，后者可能先报JSON错误。正常可信持久输入等价不自动包含这种复合故障；将来A须明确保证定义域或补设计，不能笼统承诺全部读取故障次序相同。当前B不改_research_query，避开此额外风险。详见[独立审查](../reviews/2026-10-11-research-memory-review.md)。

收益上界：去掉当前来源完整 tuple 列表和编码 JSON 全量重叠，Python 原始行缓冲约从 O(Tᵢ) 变成 O(B)。返回 rows 仍完整，调用者仍保留全部 M 份，所以整体继续 O(T)。SQL `ORDER BY` 与 DuckDB 原生结果缓冲也不因此获得 O(B) 保证。此候选便于独立审查及归因，但不足以宣称解决未来大集合扩展。

## 5. 候选 B：逐源准备，整体裁决

**推荐研究方向是 B；A 可作为独立、可回退的后续小片或消融对照。** B 先保持当前完整 `_research_query`，通过缩短调用方活对象寿命去掉跨成员全量持有。不要在同一实现中顺便重写 normalizer、tokens/checks、日期排序、SQL 资格或 public query。

### 5.1 推荐的窄范围结构

范围限 `/api/research/universe` 与 `/api/research/universe-filter`。单股与双股仍用现有 `_load`，它们的完整历史输出和配对语义不适合照搬末窗准备。公开 `universe_report(queries,...)`、`filter_report(queries,...)` 继续接受完整输入、保留其顺序及失败合同。内部可提取极小共享的“窗口成员计算”和“集合汇总/解释组装”函数，避免复制公式。

经过全部预算后，在一个 owner 请求内依请求规范顺序：

1. 完整调用一次 `_research_query`，原件核验及全行 JSON 验证完成后才进入纯准备函数。读取失败立即终止，绝不转成某成员 unknown。
2. 独立保存 header：snapshot_id、batch_id、query_id、selection、manifest、metadata、batch_checks、counts 与内部投影标记。保留完整 header 已解码内容，不做第二套字段压缩、不改变 absent/null。它不含 rows/unlocated，也不能冒充完整 query。
3. 仍按 `_at_cutoff` 选行，记录精确选择行数；一次调用既有 daily_bars，再用其完整 bars 调 daily_coverage。按现有 cutoff-present 规则取实际末 N+1 窗口；缺 D 时窗口为空。此时**先不计算指标、排名、来源摘要或条件**。
4. 单来源函数返回明确的私有 prepared 记录：header、selected_count、coverage、window，或下面约定的延期失败记录。完整 query、rows、grouped、全 bars 离开作用域，之后才读取下一来源。不得把闭包、生成器 frame、原异常或调试 locals 放进 prepared。
5. 全部来源读取成功后，按 §6 的原有逻辑阶段做 period、纯函数前置、全体身份、跨成员、selected total 检查。逐成员依原顺序重放准备错误或计算指标；最后统一排名/广度，再一次构造 filter 来源合同、原子、组与 counts。任何错误整体失败，成功结果一次性返回。

末窗 bar 是既有 normalizer 的普通小 dict，含 date、ordinal、精确 OHLC、reason，没有原 row/tokens/checks 反向引用。现有 source rejection 依赖 metadata/batch_checks，filter 的 `_source` 依赖 header，故无需保留历史展开 rows。旧 coverage 必须在释放前算完整；不能以后在短窗口上重算。

### 5.2 目标及仍存在的成本

固定行负载下，Python 活数据目标为 **O(Tₘₐₓ + M(N+1) + ΣHᵢ)**。Tₘₐₓ 中包括单源完整 rows、fetchall 原始表示、分组、bars 等常数倍副本；与 A 叠加可减少其中原始 tuple 临时项。此目标是可达性/引用生命周期合同，尚未证明实际 RSS 达标。

原件仍每请求每源检查；所有 tokens/checks 仍解析；每源完整前缀仍规范化一次，时间上界仍含 ΣTᵢ log Tᵢ。B 不保证把约14秒变成某个秒数，RSS 也可能受分配器保留、DuckDB 缓冲影响。保持现行预算；未来扩大历史或成员规模，须另看 CPU、owner 排队、取消及响应体验证据。

## 6. 必须保留的错误优先级

### 6.1 当前 HTTP 顺序的精确定义

1. 路由参数/权限/规则预算及规范化，snapshot 语法、数量、重复、D/N；集合 ids 按 snapshot_id 排序。
2. `counts=[query_row_count(...) for sid in ids]` 按该顺序完成；某个 count 抛错立即结束。**全部 count 成功以后**才判每源/总预算。前源 20,001 行、后源 snapshot 不存在时，旧结果为后者的 snapshot_not_found，不得改成提前 budget 拒绝。
3. 依 ids 顺序完整 `_research_query`。对每源依次：查关联 → raw 校验 → manifest/metadata JSON → cutoff → batch NULL count → SQL/fetch/逐行 tokens/checks → selection/query_id → batch_checks。任意失败优先于后续阶段。
4. 所有来源读取成功后 `_load` 才统一 period 检查。注意 count 本身已有 metadata/cutoff 验证；带日截止的分钟源可能在 count 阶段先报 invalid_label_cutoff，不能泛称所有 period 问题都在 raw 之后。
5. universe 计算入口先 lookback、截止、集合类型/数量；filter 先规则、截止、集合、逐 query 的 prior-cutoff 检查及 snapshot 排序，再进相同 evaluator。
6. **全部** symbol_identity 先依输入顺序完成，之后依次 market mismatch → duplicate symbol → duplicate snapshot。不能读到前两股市场不同就立刻拒绝，遮住第三股的身份不可用。
7. 全体 `_at_cutoff` 完成 → selected total limit → 逐成员 daily_bars、coverage、窗口及指标计算。daily_bars 自身顺序为 period → 单源行数 → ordinal 窗口 → cutoff → 日期组/资格；坏槽返回 reason，不代表抛出请求异常。
8. 集合排序/广度完成后，filter 才做所有 `_source`、共享合同、所有 `_member`、身份与序列化。不能一读完某股就执行 filter 原子以越过其它成员计算失败。

`universe_report` 纯函数不自行排序输入；`filter_report` 的 prior-cutoff 检查还发生在其排序前。HTTP 已有规范顺序不等于能改变纯函数传入顺序的多错规则。保留纯函数入口可显著缩小 B 的兼容负担。

### 6.2 为什么需要延期准备错误

准备会把 `_at_cutoff`、daily_bars/coverage 的工作提前到读取间隙，因此对应异常只能记录，在旧逻辑阶段裁决。读取/count 异常完全不延期。两种准备阶段要分开：所有 cutoff 选择错误高于 selected-total 和任何成员 normalize；normalize/coverage 错误按成员序，在该成员原计算位置才抛。

尤其不能把“所有 normalize 错误”在指标前统一抛出：成员1的指标异常原本早于成员2的 normalize 异常。推荐只提前准备，不提前指标，并依序做“本成员延期错误 → 本成员指标”。

延期只保留该次请求经**现有路由及 owner 映射**得到的 `(code,status)`，加原逻辑阶段与成员位置；不保留 exception、traceback、args、原文、rows 或 `sys.exc_info()`，不重建任意异常类型。最小接缝及完整调用顺序见[计划 §4](../plans/2026-10-11-research-memory.md#4-错误映射接缝与延期边界)。

真实可达性核对：可信 Store 成功返回后，prepare 只调用纯日期/价格归一化，没有 I/O、Store、解码器或采集调用。daily_bars 的显式 ValueError 只有 period、行数、ordinal 窗口、cutoff 四项；HTTP 的参数、完整读取与预算已保证后三项，period 仍在全部读取后的旧屏障裁决。`decimal_value` 的 NumericError 在 `_bar` 中转为坏槽 reason，daily_coverage 没有显式业务异常。没有找到合法持久输入能使 StoreError/DecodeError/AcquireError/OSError/duckdb.Error 从此调用图正常逃出。

仍保留程序故障的既有响应边界：universe 未知计算 ValueError 是 `invalid_research_input`/400，filter 为 `internal_error`/500；故障注入的 NumericError 还可能由 owner 按其 code 映射。直接记录“未知500”会改变这些已有行为。因此使用现成安全包装器预映射，比构建 exception-family 序列化器更小，也不把这些注入情况宣传为合法行情自然产生的异常。

count/read 完全不捕获延期；其坏 tokens/checks ValueError 仍在计算 try 外并由 owner 映射500。准备错误即使已知，也须继续原本应做的后续 source read，直到首个 read 失败或全体读取完成。重放只抛新建的既有请求错误，不变成普通 unknown 或部分成功。KeyboardInterrupt/SystemExit/取消等 BaseException 不捕获；资源耗尽不承诺继续读取以模拟业务多错排序。

若这一小接缝仍要求复制大段HTTP码表、创建错误registry或扩展normalizer，应停止并补更小设计；不能用“流式”名称豁免。

## 7. 身份、精确数与来源边界

- query_id 继续是原**公开完整来源选择**的 `_identity(selection)`；fields 仍为 VALUE_FIELDS，versions、retrospective、D、空 ordinal bounds 完全相同。prepared/window 是内部表示，不能塞入 selection 或换 method_id 掩盖差异。
- universe 的 envelope inputs、parameters.model、analysis_id；filter 的 rule_id、base_analysis_id、source_metadata_id、source/contract/window id 均要求逐字节一致。canonical rule、成员顺序、来源合同去重及 absent/null/applicability 全部保持。
- OHLC 仍 DuckDB Decimal → 同一 decimal_value → Fraction/既有 float64 边界；不走 Arrow/NumPy 浮点中转，不从公开显示数重建精确值。不改低 Decimal precision、极近值排序、V 实际 binary64 阈值比较。
- 源选择仍 `(label IS NULL OR label<=D)` 和 `ORDER BY label NULLS LAST,ordinal`。完整所选前缀及所有未定位行先处理，再释放。不能用 LIMIT N+1、按源 ordinal 截尾或只读有价格的行。
- NULL 标签的 token 日期在 D 后仍须保留来源未定位计数；可解析且≤D者可形成坏日期槽，完全不可读者影响 coverage。全 batch 未定位计数仍独立保留。
- 重复日期保留坏槽、ordinal=null；缺 D 不找上一交易日替代。坏窗口不回填更早好价；早期坏槽仍影响完整 coverage。quarantined 与 batch known_negative_sample 各自保留；行级 source_code/adjustflag 冲突规则及仅量额异常的价格资格不改。
- 每次来源读取只一次 `_verify_raw`，重复请求、空选集也执行；不先“批量验证后放心复用”，不两遍读取补偿释放，不缓存“已验证”状态。合法原件与数据库任意篡改的保证边界沿用紧凑读取 §3.4。

## 8. 编码前反例与独立 oracle

以冻结第四片完整输出为基线；只允许结构性变化的内部 helper 使用新测试钩子，禁止批量刷新 golden 或删除异常断言。至少先锁定以下用例：

| 类别 | 必要反例/验收 |
|---|---|
| 准入 | 规则无效零计数/读取；51成员、重复快照；20,001/200,001零物化；前源超限+后count失败，保原错误 |
| 跨阶段多错 | 前股 period/身份错+后股 raw corrupt 或坏 JSON；前股 raw错+后股raw错仍按ids；全部预算先于任何来源物化 |
| 全身份屏障 | 前两股市场不符+第三股身份缺失；同时 market mismatch/重复symbol/重复snapshot，保顺序；反转HTTP输入不改变规范结果 |
| 准备/计算多错 | 前股 normalize错+后股身份错；前股公式异常+后股normalize错；后股 `_at_cutoff` 错优先于前股normalize；错误不得成为部分成功 |
| 映射/脱敏 | 同一未知 ValueError 在 universe/filter 保400/500差别；read坏tokens/checks仍500；RuntimeError/TypeError/AssertionError整体500，响应不含原文；代码型异常保原映射 |
| 来源及日期 | 乱序、重复跨批边界、空前缀、全NULL、无效非NULL标签；token日期≤D、>D、不可读；窗口外坏槽；batch-unlocated与selected-unlocated不同 |
| 价格/解释 | 18位小数/20位整数、低全局Decimal precision、极近价格同显示值、仅V失败的T OR U；坏槽各primary reason、每类8见证与omitted、缺D空窗口 |
| 版本/身份 | 同请求重复、关闭重开、原子/组/成员逆序；完整输入与API prepared输出字节一致；已知未来追加/修改与未知日期追加分开验 |
| 完整性 | 首次/重复/空选集下原件同长篡改、截短、删除均拒绝；恢复后完全相同；一源失败不删成员继续 |
| 生命周期 | 每源恰一次read/raw/bars，无第二次query；进入下一源时上一源rows已不可达；prepared无traceback/闭包/全历史bars；异常后可重用Store |
| 公开边界 | public query、JSON/Parquet导出、全部精确字段、source ordinal/count/query_id不变；内部prepared与projection绝不直接输出 |

独立 oracle 分三层：旧公开完整 query 对内部投影；冻结旧 universe/filter 对全部输出及 ID；既有独立 Fraction、波动参考与三值参考继续验证数学。新旧共用准备函数的双跑只能验证组装，不能单独证明准备等价。

现测试已 spy `filters._universe_evaluation`、`filters.filter_report`、`universe_research.daily_bars`。若后续最小重构改变入口，应明确迁移探针到实际共享计算边界并保留“每请求一次evaluator、每源一次bars/读取/raw”和安全错误矩阵。不能因新路径绕开旧 spy 而宣称它仍覆盖了该请求。

## 9. 后续性能验收方案与停止条件

当前授权只含研究和轻量小输入，本节是后续获准后的预注册候选，**未执行**。

1. 冻结输入 manifest、最终源码/测试/脚本 hash、Python/DuckDB/OS及环境变量。先通过小规模全结果/错误/原件等价和引用存活断言，再获准跑正式大配置。不在第四片冻结树里试验产品。
2. 首片只比较冻结旧实现与B，使用同一200k夹具、同机与相同预热条件；不强制先做A或四臂试验。A未来获单独批准时再作对应消融。不能把其它时间/机器的耗时差作为因果证据。具体新进程次数、hash seeds、执行次序与保留条件在实施计划 §6 预注册。
3. 保留现有 10×5,000、10×20,000、50×4,000，N20/252、同六原子规则与混合异常。分别测 universe/filter；至少按原方法每路预热一次和交错5对完整ASGI，不把探针计时当正式延迟。既有失败记录永久保留。
4. RSS：每变体独立新进程，无tracemalloc，记录启动/Store打开/每源读完/准备后/成员汇总/序列化/请求结束/Store关闭的 VmRSS、VmHWM（能取时也记RssAnon）。正式VmHWM保生命周期口径；更细采样是诊断，不能替换旧门槛。固定一组 PYTHONHASHSEED 做可复验诊断，再按预注册不同进程条件复验；不要只挑某个hash seed。
5. Python 分配另起进程，在请求准备前启动 tracemalloc，记录全路径峰值、各阶段current以及追踪器自身成本。RSS与tracemalloc分别报告；不要把后者的插桩RSS与非插桩基线混比。`gc.collect()`只在测量外对称使用，不在产品每源强制GC营造数字。
6. 新增结构门槛：原始展开历史行不能跨成员存活；持有窗口bar总数≤M(N+1)，失败描述不引用输入；沿固定Tᵢ增加M时，已完成成员的Python存活历史行数不随ΣTᵢ增长。这个结构证据比仅凭两次RSS差更能验证B的设计。
7. 新优化保留门槛：全部输出/错误/身份/来源及完整回归通过；两种200k形状均可复现降低请求峰值，完整ASGI没有可复现退化。具体前后字节与时间、样本范围全部报告；本次无依据预承诺“降到某MB”或“快若干倍”。如要额外绝对目标，必须在正式跑前由独立审查冻结。
8. 032原有门槛继续单独核对：filter与同实现universe的RSS差≤16MiB；中位和每一配对时间≤baseline×1.15+20ms；新增解释层≤20ms；增量JSON≤256KiB、整体≤512KiB。共享加载变小不会自动关闭filter的增量资格。原30次稳定p95项目仍须其自己的充分样本，5对不能替代。

任何语义/错误次序/身份/原件保护回归即停止；重复测到通过、扩大16MiB、裁剪来源或只保成功成员均不可接受。A收益不明确可不保留；B若只降Python存活量而RSS未可复现改善，应如实记为结构改进、资源资格未完，不顺带开缓存/schema/并行项目。

## 10. 本次实际完成与审查问题

实际完成：静态核对上述6个核心模块、资格/评审/紧凑读取文档，复核已有结果JSON及阶段脚本；用锁定DuckDB 1.5.6跑7行fetchmany精确Decimal/NULL顺序/耗尽探针（批长3/3/1/0），用3×40行验证selected浅引用及只留18个N5窗口bar；两源spy核对预算、period/身份与后源raw失败优先级；弱引用探针确认保存异常traceback会留住本地rows、仅保存代码描述可释放。

最初独立探针的SQL别名写成保留字，解析失败；修正探针后上列项目全部通过。这是仓库外小脚本错误，无产品修改。探针不构成性能、候选A/B正确性或正式全仓测试通过。

本次未跑：新的200k、正式性能对照、全仓Python/前端、真实行情矩阵、Windows、浏览器、socket/并发/尾延迟、预测或交易增量；无新增跳过项冒充通过。未写产品/test、未提交/推送/发布，不改第四片的任何冻结结果。

编码前独立审查所核对的问题（已批准的最终决定见评审§7）：

1. A能否在不改变正常持久输入定义域、原件/JSON/batch_checks错误次序及连接生命周期的前提下独立落地？是否值得先做？
2. B的私有prepared边界是否足以保全header、coverage、窗口和全部来源身份，且没有伪装成截尾query？
3. §6的延期错误是否为最小必要复杂度；现有映射接缝与两个路由的响应是否完整，无traceback/原文保留？
4. 共享窗口计算拆分能否保持原公式、逐成员异常顺序及纯函数入口，避免新旧两套算法？
5. §9的结构/性能证据是否足够作保留决定；具体实现前还需冻结哪些指标？

## 11. 可追溯基线

研究时产品SHA256（与第四片资格所列三份相符）：

| 文件 | SHA256 |
|---|---|
| research_api.py | abb6dc06f3bdf0f7130729aa19a1709917a48fdcaa28673951bec2c1bc19e854 |
| universe_research.py | e91146b63d9f1d30b7ba42206426f5d8e1f7a92328a0f1bcc9c5bbf6d05d3e6a |
| stock_filters.py | 345b54b8683ffaf487b277931f46a550dcbe2d559fba313a423d5542d94dc571 |
| store.py | 15b7008d754fb0ca96055a10ca07e6ea480f5d596e0bdd85d3520a324b269ba8 |
| research_series.py | c4f3f49e4a17d757e7cd5d5dd9bb2d2cb96d1c257276c1f8fa875ddac5e136e9 |
| pair_research.py | a08cc8e64918639b44ec17e6a92e697d935c2229753560a3d44ea207c1ff85ba |

仓库外现有性能证据：`anatrading-filter-performance-2026-10-11/`。`results.json` SHA256=`8e083dce062ad4a10707bbc8a505625d06f1313b98c4d3263695a390f1e56ed3`，`repeat-results.json`=`b5e2a832e85f407167852d5085b914adcd137b953b1046c3e77b7baea7e0024f`。本次只读这两份及4份memory-phase记录，没有覆盖它们。

小探针与源码/测试前后摘要放在仓库外 `anatrading-memory-research-2026-10-11/`，不包含真实行情。第四片资格里的真实来源证据未复制进仓库。本节记录初始静态研究时点：当时只新增本文，具体实施计划另列、候选B获编码前批准，实现及资源验收尚未开始。后续结果与决定见下节。


## 12. 后续实测与分阶段保留（08:03 UTC）

冻结B完成独立实现审查、最终2301 passed/49 skipped、Node128/TS/build及同一60真实配置/260 ASGI复验，身份和原来源不变。一次完整预注册资源运行保留全部120计时、24预热及72新进程RSS：36旧/B绝对峰值均降低；两种名义200k形状的24对降低68.21%–83.90%，全部60旧/B时延对及12中位通过。结构改善得到本次矩阵资源证据支持。

原032的16MiB筛选增量门槛仍有4/18对失败，最大+115.457MiB；**原预注册整体保留条件继续failed**。不能用上述绝对节省或局部解释层分配抵消该失败，也不能确定差额由新增算法或数据库/allocator单独造成。具体全部数值、字节及限制见[本片资格](../qualification/research-memory.md)。

[独立最终审查](../reviews/2026-10-11-research-memory-review.md)建议分阶段保留，主方于 **2026-10-11 08:03 UTC**明确接受并决定保留B、准备发布：已验证的共享内存/时延收益予以保留，筛选增量RSS列为failed/open。回退会恢复观察到的较高驻留，且旧版16MiB同样未达；功能、来源、身份与原件完整性没有交换出去。

这是后验工程取舍，不是资源全绿或对原阈值/预注册结论的改写。正式运行后没有改源/测试、加缓存、追加矩阵或大诊断，未授予稳定p95、Windows、浏览器、并发或预测资格。以后处理开放项必须另行研究/审查并保留本轮全部失败。
