# 日线研究内部精简读取方案

日期：2026-10-11。状态：**已通过独立编码前审查，有限实现与差分复验通过，性能保留门槛仍待实测。** [独立设计与实现审查](../reviews/2026-10-11-compact-research-reads-review.md) 保留质疑、修订与逐项决定；通过功能复验不代表已经加速或达到交互 SLA。

依据：[研究工作流最终决定](2026-10-11-research-workflows.md)、[研究定义 026](../research/026-causal-signals-and-evaluation.md)、[编码前反方审查](../reviews/2026-10-11-research-workflows-review.md) 与 [合成性能实测](../qualification/research-performance.md)。本次属于保持数学和公开接口语义的读取优化，不增加分析功能。

## 1. 已有证据与目标

现有 200,000 源行、W252 合成集合实测：

| 输入 | 完整查询读取中位 | 公式中位 | ASGI 中位 |
|---|---:|---:|---:|
| 10×20,000 | 10.171 秒 | 4.150 秒 | 15.298 秒 |
| 50×4,000 | 10.327 秒 | 4.232 秒 | 14.719 秒 |

同规模逐请求原件校验仅约 4.842 / 6.529 毫秒，预算计数约 22.155 / 92.394 毫秒。完整读取已包含原件校验，不把这些独立阶段的中位数相加。以上来源为三次正式顺序实测，不能当作尾延迟、冷启动或交互 SLA。

单独 cProfile 诊断使用 2×20,000 行：插桩后的完整查询共 3.022 秒，其中 JSON loads 累计 1.129 秒（80,006 次）、decimal_text 0.581 秒（240,012 次）、DuckDB fetchall 0.398 秒、exact_sum 0.185 秒、质量统计 0.121 秒。这些累计时间可能互相包含，且插桩改变运行成本，只用于定位，不能当作预期可省时间。同一诊断中集合规范化的 160,000 次 decimal_value 累计 0.882 秒，包含字符串重新解析与范围检查。正式基准、脚本及源码哈希已冻结；本方案未重跑或修改该基准。

目标：研究请求只物化它实际消费的数据，去掉可证明无用的输出构建，保留精确源值、所有来源资格信息与完整前缀。先测量这个小改动的收益；不预先承诺某个加速倍数或流畅度。

## 2. 本轮允许与不涉及的范围

候选修改仅限：

1. `EvidenceStore` 新增内部方法 `_research_query(snapshot_id, cutoff=None)`。
2. `research_api._load` 完成现有全部预算预检后，改为调用该内部方法。
3. 增加直接投影等价、研究响应等价、原件校验和公开查询/导出回归测试；扩展性能验证的独立诊断项。

`query`、`export_json`、`export_parquet`、旧 HTTP 图形/明细接口的参数和返回内容维持完整语义。首选不改 `query` 的实现；若为避免身份构建重复而提取极小纯 helper，必须保持逐字节序列化等价，不能顺带改造其余读取流程。

本轮不做：数据库 schema/版本迁移、新依赖、进程并行、队列、跨请求缓存、递推状态缓存、tokens/checks 缓存或裁剪、SQL JSON 提取、新公开投影参数、最后 W+1 行裁剪、改变浮点公式或归一化逻辑。JSON 解析仍是可能保留的主要成本；若本次收益不足，另行设计和审查，不能默默扩大优化范围。

## 3. 内部读取合同

### 3.1 调用边界、锁和失败次序

- 仅由既有 owner 线程内的研究加载步骤调用。沿用同一个 Store 与 `_mutex`，不创建第二个连接，不改变写入者和事务约定。
- 方法只接收版本与截止，隐含 `mode="retrospective"`，不接受源序号、字段列表、起点、尾部行数或跳过验证选项。研究预算仍为每系列 20,000、总 200,000、最多 50 个不同版本；`_load` 在任何投影物化前对全部输入完成 `query_row_count` 预检。
- `_research_query` 为内部读取原语，调用者必须先完成上述预算准入；不能将其暴露为无预算 HTTP 接口。已有规范化层的单系列与集合预算检查继续保留。
- 校验 snapshot_id、查找相同 snapshot/batch/raw 关联后，**每次实际读取都调用 `_verify_raw(sha, byte_length)`**。再解码元数据、校验 cutoff、计数与查询。空选集、重复请求、曾成功读取、已被标记负样本都不能跳过原件校验。
- 不新增提前的周期拒绝：保留 `_load` 当前加载后统一判定 `period == "1d"` 的流程，避免在多输入混合错误时改变错误先后。路由原有日期、参数、权限和错误映射保持不变。
- 预算计数本身只作准入，不授予原件完整性资格。超预算请求仍可在原件校验前被拒绝；通过预算后任何原件缺失/长度变化/同长度篡改均按现有错误整体失败，不返回部分集合结果。

### 3.2 SQL 行集合与顺序

投影 SQL 只读取：

`ordinal, label, tokens_json, checks_json, source_open, source_high, source_low, source_close`。

条件严格保留 `batch_id=?`；有 cutoff 时追加 `(label IS NULL OR label<=?)`。排序严格为 `ORDER BY label NULLS LAST, ordinal`。不在 SQL 中判断日期合法性、OHLC 资格、重复、证券或复权资格，不删除任何异常。

- 从原版本起点一直保留到 cutoff，不因为集合只计算末窗而截断完整来源覆盖。
- `label IS NULL` 的记录无论 token 中日期早晚均保留在 `unlocated`。现有 `daily_bars` 再按 token 日期决定是否形成截止内的无效日期槽，`daily_coverage` 仍披露全部未定位行。
- `label` 非 NULL 的选中记录进入 `rows`；NULL 记录进入 `unlocated`。每一组内源序号顺序与完整查询相同。
- `batch_unlocated_rows` 单独对**整个 batch**计数，不受 cutoff 影响；不能以选中行统计替代。`batch_rows` 来自相同持久元数据。
- 原序号保留原整数，不能重新编号、压缩重复日期或修改异常行位置。

### 3.3 返回的内部映射

保留以下完整查询字段及语义：

- `snapshot_id`、`batch_id`、`manifest`、`metadata`、`batch_checks`；manifest、metadata 和 batch_checks 完整解码，不能只保留当前算法常用键。
- `selection` 与 `query_id`，见下一节的来源身份定义。
- `counts` 的四个键：`selected_rows`、`unlocated_rows`、`batch_rows`、`batch_unlocated_rows`。
- `rows`、`unlocated` 中每行含 `ordinal`、`label`、完整 `tokens`、完整 `checks`，以及 `values`。`values` 只包含 `open/high/low/close` 四键，缺值为 None。
- 一个明确内部标记 `read_projection="daily_ohlc_input_v1"`，表明该映射仅适用于研究输入，不能用作公开完整查询或导出文件。

OHLC 直接保留 DuckDB 读取的 Decimal。SQL 不 cast 为 FLOAT/DOUBLE，不先经过 float，不做四舍五入，也不做算术修补。`daily_bars` 继续调用既有 `decimal_value`，保留精确范围和非有限检查；只省掉 Store 的 decimal_text 和紧随其后的字符串解析。研究公开结果继续由既有格式化位置输出精确价格文本，统计估计边界不变。

内部映射不包含 `quality`、`unlocated_quality`、`totals`。行级不物化 `locator`、`source_label`、amount/volume、`volume_shares`、`amount_cny`。这些信息仍在数据库、原件与完整查询中。缺省字段不能填伪造的空汇总或 0；任何后续研究若需要它们，须先扩充此合同与测试。

完整 tokens/checks 必须留下：

- `source_date/date` 用于可定位的异常槽；不能只看规范化 label。
- `code/adjustflag` 与元数据直接比较，可在没有缓存 fail check 时仍发现明确冲突。
- `source_code`、`source_adjustflag`、`source_adjustment` 的失败检查保留；与价格无关的 volume/amount 检查也完整保留，但仍不因此阻断价格计算。
- 批次 `known_negative_sample=fail` 和元数据 `quarantined=True` 各自仍足以阻断研究资格；不能相互代替或只保留其中一个。

### 3.4 等价定义域与损坏失败安全

严格结果/错误等价的定义域为通过现有 decoder/import 正常持久化的存储，包含正常保存的 fail 检查、NULL 源字段和已拒绝资格的来源。省略 totals 在这个定义域不会移除正常的合计数值失败：每系列至多 20,000 行，DECIMAL(38,18) 的精确合计最多约 43 位有效数字，低于 exact_sum 的 128 位精度；BIGINT 合计也在该界内。

原件哈希从来没有提供数据库任意手工篡改的完整性保证。不过精简读取仍必须失败安全，不能因为不调用 `_quality` 而把它原来拒绝的坏 checks 结构当作干净数据。保留 JSON 语法解析失败；对行级 tokens 检查为 dict，对行级/批次 checks 检查为 list 且每项为含字符串 name、有效 outcome（pass/fail/not_evaluated）的 dict。缺必需键、错误容器、非法 outcome 明确抛错，通过既有边界映射为脱敏 internal_error，不伪造空检查或获得资格。该小型结构验证不生成质量计数；允许本轮实现，成本计入性能实测。

更广的数据库篡改检测、重新解码一致性审计和数据库修复不在本轮；不声称全部任意损坏的错误顺序或错误类别完全等价。公开完整 query 行为仍保持原样，针对这些特意破坏的夹具只要求精简研究拒绝，而不以拒绝码的新区别升级方法身份。

已直接复核的区别：旧 `_quality` 对缺 name/outcome 的 check 抛 KeyError，必须保留这种失败安全；其 Counter 会接纳未知 outcome 并产生一个额外计数键，因此新内部路径拒绝未知 outcome 属于损坏输入硬化，不能称为该损坏场景的旧行为等价。

## 4. 来源身份与公开响应等价

`query_id` 已是查询选择身份，不是完整响应内容的哈希。本次内部投影继续指向同一个**公开完整来源查询**：

1. `selection` 必须与 `query(snapshot_id, cutoff=cutoff)` 完全相同：snapshot_id、mode=retrospective、cutoff、ordinal_start=None、ordinal_end=None、`fields=list(VALUE_FIELDS)`、manifest 中相同 versions。
2. selection 中的 fields 描述该来源查询的字段选择；内部行载荷仅为它的 OHLC 投影。由 `read_projection` 显式区分内部载荷，禁止将 selection.fields 改成 OHLC 后仍复用旧 query_id。
3. `query_id = _identity(selection)`，沿用现有 Unicode、键排序、紧凑 JSON、Decimal 和非有限拒绝规则。read_projection 不加入这个来源身份。
4. 研究响应的 inputs 仍含相同有序 snapshot_id/query_id。方法、参数、模型参数与算法均不改变，因此 `analysis_id`、method_id、完整研究结果与相同请求的 JSON 内容应保持一致；不为纯内部表示变更升级方法版本。
5. 双股左右角色仍有序；集合仍按现有规则规范排序。改 cutoff/参数/成员/左右方向的身份失效规则不变。
6. 内部投影绝不直接 JSONResponse、持久化或导出。尤其 Decimal 行值不能通过通用 JSON 编码转成近似数。公开 query/export 仍走完整方法，不能接受内部映射作为替代结果。

如果无法达到结果与身份等价，停止这次优化并报告差异；不能用换 method_id、改误差容限或改变 cutoff 解释隐藏语义变化。

## 5. 编码前测试合同

先写异常与等价用例，测试参考只从原 `query` 或独立已有参考构造，不能让新旧路径共用被测投影实现。

### A. 内部投影参考

对完整查询构造独立预期：保留上述顶层字段、四类 counts、原行顺序、ordinal/label、完整 tokens/checks，将四项精确字符串转换为 Decimal，其余字段明确不在内部载荷中。与新读取比较，同时用 decimal_text 核对所有非空 OHLC 与旧文本逐字符相同。

覆盖：无 cutoff、截止前空选集、截止恰在日期、截止晚于所有日期；乱序源行、重复标签、部分和全部未定位；token 日期在截止后/截止内/不可读；极短和空研究日期组。覆盖日线格式，分钟输入保持既有路由拒绝。

数值包括 18 位小数、20 位整数加小数、近等值突破阈值、零/负值、字段缺值、非法输入被解码为 NULL、最大合法量与大金额。后两项虽不投影，完整查询及导出必须保持原值。使用低全局 Decimal precision 重跑参考等价与研究结果，禁止上下文舍入渗入。

### B. 资格与全部结果

- 实际正常导入夹具：来源 code 冲突、adjustflag 冲突、一致但不支持的 adjustment、已标记负样本，以及仅量/金额异常。
- 没有 fail check 但 token 与 metadata 冲突的独立输入；只保留批次负样本检查而清除 quarantined，以及反向情形。
- 比较 daily_bars、daily_coverage、signal_report、pair_report、universe_report 的完整结果；包括 reset、事件成熟/purge、坏路径、覆盖数量、配对遗漏、分母、并列排序、所有不可计算原因。
- 单股/双股 W20、W252；事件 horizon 1/5/10/20 与显式 test_start；集合缺截止、重复证券、不同市场、未知身份与查询顺序变化。用固定请求的旧完整查询驱动 `_calculate` 得到独立基线，再比 ASGI 完整 envelope、ID、严格有限 JSON 和响应字节。
- 原有逐前缀/修改未来不影响此前信号测试继续通过；完整算法不因这次投影而更换或降级。

### C. 原件、预算与公开边界

- 同一来源首次和重复读取均验证原件；成功后同长度篡改、截短、删除原件，必须失败。包含空截止选集；恢复后重复结果完全相同。集合任一原件损坏整体失败，不能静默丢成员。
- 单独构造存储 JSON 语法错误、checks 缺 name/outcome、错误容器或非法 outcome，确认研究拒绝且错误不泄露原始内容；这些损坏测试与正常 decoder 保存的 fail/NULL 样本区分。分钟来源同时损坏原件时，保留先报原件失败的既有次序。
- Spy 断言研究通过预算后不调用公开 `query`、`_quality`、`exact_sum`，不 SELECT *，不读取 source_volume/source_amount/无用展示列；完整 tokens_json/checks_json 仍被读取。
- Spy 断言所有成员预算计数先于第一条投影物化；20001、总量200001、51成员拒绝时完整/精简方法均不可调用。更新已有仅监视 `query` 的限额测试，避免切换路径后出现假通过。
- 公共 `query` 与 `tests/test_store_query.py` 的独立全批次参考完全相同，含 ordinal 巨大整数/空范围、NULL、quality、totals 与旧 query_id。
- JSON 导出字节、query_id、哈希与既有完整查询序列化一致；Parquet 读回 schema、行、精确字段、元数据与 query_id 相同。保持锁/owner 生命周期、只读边界和错误脱敏回归。

## 6. 性能验收与停止条件

正式基准原记录保持冻结，新增运行使用不同文件名并记录源码/脚本哈希。先跑小型全结果等价，再跑与现有同种子同参数的 5k/20k 单股/双股和两种 200k 集合。

分开报告：公开完整查询、内部精简读取、原件验证、预算计数、研究公式、序列化和完整 ASGI。直接算法输入从完整查询与投影各跑一次等价检查；在 ASGI 计时前释放夹具并 GC，沿用既有口径。正式请求重复三次，保留每次时间，不把剖析器数据当性能验收。

继续核验结果哈希、query_id/analysis_id、响应字节、原件长度/哈希与重新读取的完整查询指纹，不能用精简输入哈希替代全部原始字段检查。单独记录合成异常密集夹具的功能与耗时，避免只测干净样本。

保留优化的条件：所有等价/资格/原件/公开接口测试通过，受影响全仓回归通过；在两种上限集合均有可复现的读取改善，且 ASGI 未出现可复现退化。报告具体实测改变量和噪声限制，不预设未经证据的秒数目标。若结果不同、公开查询有变化或收益不明确，停止/回退本切片，记录剩余瓶颈并请求新的独立审查。

同源浏览器、峰值内存、并发排队、原生 Windows、真实软件文件和样本外预测仍是各自独立验收。此项读取优化不关闭任何尚未实际验证的项目。

## 7. 独立审查应重点反驳的风险

1. 内部 OHLC 载荷沿用完整来源 query_id 是否足够明确；调用点是否可能误把它当完整查询/导出。
2. SQL NULL 与 token 日期的双层语义是否完整；是否保留全批次未定位计数和负样本/复权/身份失败。
3. Decimal 输入与旧精确文本的规范化是否逐值等价，是否可能改变极近价格比较、输出文本或参数身份。
4. 新读取是否意外改变错误次序、预算预检、空集合原件验证或 owner 生命周期。
5. 保留完整 JSON 解析后收益是否足以抵偿一条小型独立读取路径的维护成本；测量是否被多余夹具、并发或 GC 混淆。
6. 是否有当前消费者偷偷依赖已省字段；将来的消费者能否因测试和显式内部标记尽早发现合同缺口。

## 8. 实施状态（03:55 UTC）

独立审查接受最终 §3.4 后才开始编码。实际产品改动为 `store.py` 新增轻量检查结构验证与 `_research_query`（共 60 行），`research_api._load` 改一处调用；公开完整查询、JSON/Parquet 导出、query_row_count、序列化/身份与原件校验实现未改。没有公式改动。

- 新投影参考测试先运行，按预期因方法尚不存在而失败，随后实现。
- 主要实现方针对 Store/SQL/研究/API/投影运行 114 项测试全部通过，12.72 秒；含三个 HTTP 研究接口与原完整查询路径的逐字节响应比较。
- 独立审查者另行运行 300 项相关回归全部通过，21.51 秒，无跳过；其 18 项对抗测试通过，且 AST 对照确认指定公开方法和完整性方法没有改变。
- 初次全仓回归为 1,357 通过、49 跳过、5 失败，58.71 秒；失败来自同时编写中的分钟采样对抗测试的 `estimate_scope` 预期。后续 1,445 通过的运行期间该模块仍在修正跨平台时区依赖，两次均不作为最终工作区资格。
- 所有源码与测试显式冻结后，最终完整 Python 回归 **1,446 通过、49 跳过、0 失败，55.34 秒**，有一条既有 Starlette/httpx 弃用警告。运行时间为 03:54:25–03:55:21 UTC；全体 src/tests Python 文件运行前后 SHA256 一致，变动文件为零。详细日志和哈希证据在仓库外运行记录中保存。
- 研究 Store/API 自 03:45 UTC 实现后未再变化；独立性能测量仍待完成。优化后性能结果尚未到齐，保留/回退决定仍受 §6 条件约束。
- `git diff --check` 通过。真实行情、Windows、同源浏览器、预测与交易增量未因本优化获得新资格。
