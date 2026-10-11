# 日线研究内部精简读取：独立设计审查

日期：2026-10-11，03:42 UTC。审查基础：本地提交 `c137ba1`。对象：`docs/plans/2026-10-11-compact-research-reads.md` 最终候选稿，含新增 §3.4。审查者读取当前 Store、研究加载器、全部日线研究消费者、数据类型/导入结构和合成性能报告，只写本评审，未修改产品代码。

## 决定

**接受修订后的合同，允许本切片编码。** 允许范围为新增内部 `_research_query`、研究加载调用点、必要的轻量持久 JSON 结构验证、等价/边界测试和独立性能测量。公开查询与导出、数学与源资格规则、存储 schema、方法版本、预算及逐请求原件校验保持不变。

这是编码前设计批准，不是实现验收、加速结果或真实来源/Windows 合格声明。实现必须满足下列等价门槛才可保留。发现差异不能通过放宽误差、改变方法身份或减少来源检查绕过。

## 1. 质疑：完整来源 query_id 能否标识一个精简对象

原 `query_id` 是 `_identity(selection)`，不是整个查询响应的内容哈希。selection 含六个原始字段，并无质量汇总、总和或载荷表示方式。若把 `fields` 改成四项却继续复用旧 ID，会产生来源选择的虚假声明；若将精简对象冒充完整公开响应，会丢失原有字段合同。

最终方案明确区分这两层，故可接受：

- selection 逐项、逐字节沿用同一个公开完整来源查询，包括完整 `VALUE_FIELDS`、截止、None 序号范围及持久 manifest 的 versions
- `read_projection="daily_ohlc_input_v1"` 只说明内部物化子集，不参加来源 query_id
- 研究方法仍引用同一来源选择；最终 envelope、analysis_id、method_id 和完整研究 JSON 内容必须相同
- 精简映射不进入公开 JSONResponse、缓存文件、任何导出或旧查询接口，不补伪造的空 quality/totals

这种解释依赖封闭的内部调用点；将来新增消费者不能仅因对象带 query_id 就假定它具有完整查询字段。新消费者需要扩充合同和差异测试。

## 2. 质疑：删除 quality/totals 是否会取消原来的失败

初稿仅省略聚合仍有一个真实风险：当前 `_quality` 直接索引检查字段，而研究资格逻辑使用 `.get`。如果跳过前者，损坏的持久检查可能被静默当成无失败记录。

### 实际独立复现

在临时 Store 正常导入合成 BaoStock 日线，保持原件字节及哈希不变，只把一行的 checks_json 改成合法 JSON：

```json
[{"name":"source_code"}]
```

- 现有完整 `store.query` 抛 `KeyError('outcome')`，经既有 HTTP 边界应成为脱敏 internal_error
- 用先前完整查询构造同样缺键的候选投影，直接调用当前 `signal_report`，该行 `reason=None`、`breakout=True`，并得到一个 valid 事件标签

这里使用临时合成数据库；不是实际客户库损坏报告，也未修改产品。该实验足以说明“只保留 JSON 语法解析”不够。

**修订已关闭此阻断项。** §3.4 要求行 tokens 为 dict、行及批次 checks 为 list、各项含字符串 name 与合法 outcome；缺键/错误容器/非法值明确失败，经既有边界脱敏，不做质量计数。完整 JSON 继续解码。

事实边界：未知 outcome 字符串，例如 `bogus`，当前 Counter 会创建新计数键，并不必然触发旧查询失败。因此对未知 outcome 的拒绝属于损坏输入的保守硬化，不能称它与旧路径的该项行为严格一致。正常 decoder/import 只产生三种合法 outcome；该硬化不改变获准定义域。

省略 totals 在已批准预算与存储类型内有可验证依据：每系列至多 20,000 行，DECIMAL(38,18) 合计约需最多 43 位有效数字，BIGINT 合计更小，均远低于 exact_sum 的固定 128 位精度。因此应通过合法边界值证明省略不会遮住正常源输入的数值错误，无需为“完全相同异常”继续执行无用合计。

任意数据库篡改的完整检测原本不由原件哈希保证。接受文档将严格等价限定为正常 decoder/import 形成的持久结构（包括源值 NULL、检查 fail 与已隔离来源），并对已知损坏结构另做失败安全。不接受把本次已识别的缺键失败直接排除后放任通过。

## 3. 质疑：读取顺序、预算与原件校验会否变弱

接受以下冻结顺序：

1. 路由权限/参数仍由原边界处理
2. 对全部成员完成现有计数准入，未物化任一系列；超限可继续早于原件校验拒绝
3. 每次实际读取沿用 snapshot/batch/raw 关联与同一 mutex，先 `_verify_raw`，再解码元数据/验证截止/查询
4. 保留 `_load` 当前加载后统一周期判断，避免单股无截止的分钟来源原件损坏被新增提前 period 拒绝掩盖
5. 任一成员失败整体失败，不返回部分排名或改变广度分母

预算预检的原测试只拦截 `query`，切换到新方法后会有假绿灯风险。方案已明确要求同时拦截精简方法，并验证“全部 counts 先于首个物化”。这应是实现的必跑门槛。

不允许原件校验缓存、已验证标记、空结果跳过验证、复用前次请求上下文或以性能为由降低 200k/20k/50 的检查强度。

## 4. 质疑：可用字段与精确数值是否真的足够

逐消费者核对，当前 `research_series`、单股/事件、双股和集合只需：原 ordinal/label、OHLC、完整 tokens/checks、全部来源 metadata、隔离 batch_checks、counts、截止及来源身份。locator/source_label/数量金额汇总不被当前研究公式消费。

直接传 DuckDB Decimal 是可接受的表示优化：`daily_bars` 仍调用原 decimal_value，不改资格判断；后续 Decimal 阈值、Fraction 变化与原输出格式化继续使用相同精确值。通过浮点或低全局 Decimal context 的算术构造替代直接读取均不在许可范围。

尤其不能进一步裁掉：

- 未定位行与其可读或不可读 token 日期，即便 token 日期晚于截止
- 全批次未定位数量、重复槽和原序号
- token code/adjustflag 与元数据对照
- 行级来源冲突 fail、元数据 quarantine 和批次 known_negative_sample fail
- “仅量额异常”原检查；这些仍保留证据，同时继续允许合格价格研究

保留全部 JSON 会留下已知成本，但本轮应先测这条可审计小路径。tokens/checks 摘要化、缓存、SQL JSON 提取、最后 W+1 行裁剪或重写归一化都需新审查。

## 5. 实现验收门槛

完整接受方案 §5 的测试矩阵，重点要求：

- 独立投影 oracle 从原完整 query 构造，不能两路共享被测物化代码；Decimal 还须格式化回旧精确文本逐字符核对
- 比较全部研究结果与完整 HTTP 响应，而非只比末行或浮点近似；ID、原因、分区、计数、左右角色与排名一并对照
- 正常/NULL/坏价/重复/未定位/身份冲突/复权冲突/隔离/仅量额异常均有实际导入路径；截止和字段边界以独立参考核对
- 原件首次、重复、空截止、同长篡改、截短、删除及集合局部损坏均失败安全，恢复后结果相同
- 专项复现缺 outcome/name、错误容器、坏 JSON；拒绝不能泄露存储文本或路径
- 完整 query、JSON 导出字节/hash、Parquet schema/精确值/元数据与已有独立参考保持原状
- 研究请求确实不调用公开 query、quality、exact_sum 或 SELECT *，预算拒绝路径确实不调用任一物化方法
- 全部受影响回归通过，最终改动后重跑；Windows 原生与真实数据未跑保持明确未验

## 6. 性能结果怎样才支持保留修改

旧 200k 集合基准表明完整读取约 10.2 秒、原件校验仅数毫秒；保留完整性检查是合理决定。cProfile 项互相重叠，不能把 decimal_text、exact_sum、quality 等时间相加承诺某个百分比。

接受先保持现有正式记录，再用同生成器、同规模、同窗口、同字段指纹测三次的新结果。新旧读取应在尽量相同环境和输入下比较，记录每次时间、源码及脚本哈希、缓存/GC/并发限制；仅与过去某次时间差不能证明因果加速。

两种 200k 集合都需可复现读取改善，且 ASGI 无可复现退化。完整研究结果、原件与公开查询指纹必须一致；成本转移到归一化、JSON 或浏览器不能当作整体改善。若收益不明确或任一等价门槛失败，按方案停止/回退，不能扩展到未批准优化。

本审查未运行优化后性能、未运行全仓回归，也未验证浏览器、峰值内存、并发尾延迟、Windows、真实文件或预测增量。待实现验收记录完成前，这些结论保持开放。

## 7. 03:47 UTC 实现后独立复验

实现已落地，独立复审结论：**本切片的已检查正确性、来源资格与公开边界通过；未发现剩余实现阻断项。是否保留优化还需通过 §6 的新性能测量门槛。** 此次没有把设计批准或测试成功写成性能改善。

实际产品改动只有：

- Store 新增 `_research_checks` 和 `_research_query`
- 研究 `_load` 的物化调用由 `query` 改成 `_research_query`
- 相关新增测试及预算 spy 更新

通过 `git show c137ba1:src/anatrading/store.py` 与当前文件解析 AST 对照，`query`、`export_json`、`export_parquet`、`query_row_count`、`_identity`、`_json`、`_verify_raw` 的 AST 完全相同；源码 diff 也未改旧函数实现。新增读取保留原件验证次序、全量 tokens/checks、SQL NULL 语义、来源选择、四项 counts 与原 Decimal 字段。内部 projection 标记未泄露到研究 HTTP 结果。

### 独立测试与结果

审查者只追加 `tests/test_research_adversarial.py`，与实现者的 `tests/test_research_projection.py` 分离。独立新增：

- 正常导入的混合异常/乱序/重复/NULL/超截止 token/量额异常及极值；六个截止、四种 horizon、低 Decimal 精度的完整投影与全部方法结果/身份差分
- 重复精简读取前后，公共 JSON 字节/hash 与 Parquet 数据、schema、metadata、hash 全同
- 七种损坏 checks 的 HTTP 拒绝/脱敏；原总预算测试同时禁止两种物化路径

独立对抗文件共 18 项：**18 通过，2.55 秒**。

随后独立执行相关集合：

```text
.venv/bin/python -m pytest -q \
  tests/test_research_projection.py tests/test_research_adversarial.py \
  tests/test_research_series.py tests/test_signal_research.py \
  tests/test_event_study.py tests/test_pair_research.py \
  tests/test_universe_research.py tests/test_research_api.py \
  tests/test_store_query.py tests/test_store_platform.py \
  tests/test_store.py tests/test_store_failures.py tests/test_workbench_boundaries.py
300 passed in 21.51s
```

该次 **0 失败、0 跳过**。包括实际空截止仍校验原件、首次/重复/同长篡改/截短/缺失原件、分钟输入且原件坏的错误优先级、单系列 20,001/总计 200,001 的准入顺序、完整 HTTP 响应字节与 ID 等价、检查缺键和未知 outcome 的失败安全。`git diff --check` 通过。

本次复验源码 SHA256：

- `src/anatrading/store.py`：`15b7008d754fb0ca96055a10ca07e6ea480f5d596e0bdd85d3520a324b269ba8`
- `src/anatrading/research_api.py`：`fe058c601ddda3399bedf3d7d4f1a62effa118d888ddc222656050e473fa9a66`

审查者未编辑产品、未提交或推送。新性能、最终全仓测试、浏览器性能、峰值内存/队列尾延迟、Windows 原生和真实文件由各自验收记录补齐；本次 300 项局部通过不替代它们。产品再改动后应对受影响行为重跑。
