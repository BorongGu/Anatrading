# 032 可解释股票筛选：独立反方审查

日期：2026-10-11。审查对象：[032](../research/032-explainable-stock-filters.md) 的首次冻结稿及作者回应后的修订稿，代码基线 `97d483f7ab2d0eb5e43ba81eb5c24b6e0be08272`。作者并行进行的 030 工作不计入本次已验收能力。

## 1. 决定

**设计阶段最终决定：允许按修订后的 032 开始最小纯函数与只读 API 编码。** R1–R3 已由作者逐项回应、修改正文并经本 reviewer 复核关闭，详见 §7。后续实现已进入独立测试与联合验收，实际通过、修复及未完成项见 §8；设计批准本身不授予全部验收资格。

**当前实现审查最终决定：纯函数/只读 API 功能与已定真实来源兼容阶段通过；资源验收仍有未达项，不授予全面资源通过。** 详见 §8.6 和[实现验收](../qualification/stock-filters.md)。

首次决定为暂缓编码。三字段、最多两组 AND→OR、最多六个原子和只读 API 的方案可以保留；无需增加通用规则语言、Store 验证层、数据表或资格框架。以下保留首次发现与修改要求，便于核对关闭依据。

已明确认可的决定：

- 新增范围确有小增量：对用户选定的导入版本，用既有动量、波动、收盘路径回撤作有限条件并组合 OR。旧 `daily_screen` 已有逐条件解释、精确阈值和全池分母，旧 `universe` 已有三数值和排序；这些不能重新算作新功能。
- 采用标准 Strong Kleene。共同来源门槛通过时，完整成立支路足以使 `T OR U = T`，可以入选，且 `evidence_complete=false`、未知原因同时保留。增加无关 OR 支路不能降低原先已有充分证据的入选资格。
- `F AND U = F` 可以排除该支路，但不得删除 U；`F OR U = U` 为待核查。共同来源门槛未通过时，依赖它的原子全部 U，不能靠 OR 绕过。
- M/DD 用源 Decimal→Fraction 的精确值比较；V 对实际 float64 估计的二进制值严格比较精确十进制阈值。允许披露临界平台差异，无需默认引入 epsilon 或另一套数值安全带。
- 原件核验、完整前缀紧凑读取、身份判断和预算复用现有可信 Store 边界；同请求加载、归一化和窗口计算各一次。不得为每个条件重查，也不得先调用旧 universe 路由再调用新路由。
- 当前来源价格回顾有有效研究用途。未知调整、历史可得性和交易日历必须保留；不能据此宣称经济收益、alpha 或预测增量。

## 2. R1：来源摘要不得丢失 applicability

**编码前阻断，局部修订。** 032 §4.2 只列语义字段的 `value/status/reason`，现有 `formats._source_semantics` 还有直接影响解释的 `applicability`。本次实际检查 BaoStock 日线合同得到：

```text
price_unit.value = CNY
price_unit.status = known
price_unit.reason = documented_meaning_only
price_unit.applicability = unverified
```

只保留前三项会让来源适用性限制从新摘要消失。常驻“单位/来源仍未知”的泛化文案不能替代原字段的精确信息，尤其前端很容易把 `known` 渲染成此样本已核实。

最小修正：六个既定语义字段同时保留 `applicability` 的存在性与原值，并沿用 absent/null 区别；若引用 `source_semantics.scope`，也原样标明作用域。证据数组仍用现有 contract ID 和字段路径回查，不复制全文，不扩大元数据白名单。将实际投影内容绑定 `source_metadata_id`；不能把 absent 默认成 verified。

必要反例：

1. BaoStock 的 `known + applicability=unverified` 必须完整可见；真实腾讯的 unknown 保持 unknown。
2. applicability 缺失、显式 null、unverified 为不同摘要，身份相应绑定；规则成立均不升级来源适用性。
3. `requested_adjustment=none` 与实际已核复权保持分离，不把请求值填进源语义的 verified 状态。

## 3. R2：source_gate 的成员条件必须封闭

**编码前阻断，限于一个小定义。** §5.2 的“源日期完整性等共同资格”尚未列完 `等` 的内容。实现者可以把缺截止、短历史、价格坏槽、未知复权都塞入 gate，得到不同 gate 分母，即使最终选择状态碰巧相同。

建议 v1 直接冻结为：

- `source_gate=pass` 当且仅当此次共享 `daily_coverage.coverage_known=true`；否则 unknown，原因 `date_set_integrity_unknown`。它只回答源日期可定位性，不认证来源、交易日历或经济可比性。
- 证券顶层冲突、Store 读取/原件失败沿用整请求失败；不可降为某个 OR 分支的普通未知。
- 缺截止、短历史、重复/坏 OHLC、窗口内来源身份/调整冲突、隔离源，沿用共享事实的现有原因，使所有依赖该窗口价格的 M/V/DD 原子 U。它们不再独立改变这个日期 gate。
- `_volatility` 的已知数值失败仅影响 V；若 M/DD 可用，合法 OR 支路仍能入选。未知调整、known_at 等只保留已定限制，不暗加新总门槛。

作者可选择另一份同样封闭的小表，但不能保留开放的“等共同资格”。无需改名现有 source_gate，也无需为每种失败另造 gate 状态。

必要反例：

| 场景 | 必须保留的区别 |
|---|---|
| M=0.12、DD=−0.03、V 数值失败，使用 032 示例规则 | gate pass；组 U/T；整体 T；selected；partial=true |
| 同例 M=0.08 | 组 U/F；整体 U；undetermined |
| 已知某 AND 原子 F、另一原子 U，所有 OR 组均 F | excluded，同时 partial=true |
| 有三条正常日期/价格和一条完全无日期行 | 旧 universe 仍可能显示 M=V=DD=0；新原子全 U、gate unknown、undetermined，旧数值不改 |
| 只有窗口内明确坏价或身份冲突，没有未定位行 | 日期 gate pass；相关事实 U；undetermined；不可把 pass 显示为“来源通过验证” |
| hash 不符、读取失败或未归类程序异常 | 整请求失败，无部分成功筛选响应 |

三态必须显式比较枚举值。把字符串 `true/false/unknown` 直接交给 Python `all/any` 会全部按非空字符串为真；先物化只解决短路漏证据，不自行解决三值归约。

## 4. R3：“全部失败”承诺须匹配现有归一化能力

**编码前阻断，允许收窄承诺。** §5.3/§7.2/§8 要求汇总全部原因、同次遍历收集全部失败，而 `daily_bars` 每个日期组只输出一个 `reason`。重复日期及不可定位 label 会早返回；`_source_conflict` 也只返回首个冲突。仅提取 universe 私有 evaluator 无法恢复被这些规则掩盖的同槽原因。

本次构造同一日期槽同时具有证券代码冲突、调整标记冲突和缺 high，`daily_bars` 只返回 `source_identity_conflict`。这不影响该槽的既有不可用判定，却直接否定“遍历 bars 即已列出全部底层失败”的承诺。

建议首片采取更小的承诺：

1. 汇总窗口中**每一个坏日期槽已有的 primary reason**，不沿用 universe 全窗口只挑第一个原因的做法；保留每类坏槽数、至多 8 个见证、omitted_count。
2. 原始行/batch checks 保留在来源查询中，通过既有 source/query/ordinal 引用回查；新报告明确声明原因清单是已归一化坏槽原因，不保证穷尽同槽所有底层失败。
3. 日期 gate、字段数值失败独立加入解释，不能被首个窗口原因盖掉。原子/组顺序变化不改变这些证据和计数。
4. 不为补全每一个次要原因复制 `_bar` 的价格/身份规则，不引入第二次来源校验或 Store 查询。若作者坚持全部同槽原因，须先另列共享归一化的最小兼容改法及测例；不能边写筛选边重建验证器。

必要负例：一个窗口里分别出现重复日期、坏价和身份冲突时，三个坏槽都可追溯；同一槽的三重错误保留既有 primary，并能回查源记录；缺截止时窗口为空不伪称“没有来源异常”；全局未定位行的 gate 原因仍保留。

## 5. 不扩大范围的实施注意

以下不单独阻断设计，但应进入测试或正文小修：

1. 阈值只支持 18 位小数，032 §9.2 的 `1e-19/2e-19` 示例适合数值/排名，不能单独验证两值跨可接受阈值。使用下面实际手算的同显示值反例：

   | 事实 | 精确来源构造 | float 显示值 | 阈值 | 真值 |
   |---|---|---|---|---|
   | M | 10499999999999999999 / 10000000000000000000 − 1 | 0.05 | ≥0.05 | F |
   | M | 10500000000000000001 / 10000000000000000000 − 1 | 0.05 | ≥0.05 | T |
   | DD | 8999999999999999999 / 10000000000000000000 − 1 | −0.1 | ≥−0.1 | F |
   | DD | 9000000000000000001 / 10000000000000000000 − 1 | −0.1 | ≥−0.1 | T |

   每个源值均在现有 DECIMAL(38,18) 范围。将中间价设为适当正值即可构成 N=2；DD 的首价作为运行峰值。同时覆盖低 Decimal context，禁止 UI 百分比经过 JS Number 转换。
2. V 用 `0.5` 及左右 nextafter 做严格比较是合适边界；与 60 位 Decimal 参考的误差容差仅验证估计，不决定入选。M/DD 精确数与 V 近似数的标签和单位必须不同。
3. `unsupported_filter_version` 暂无可触发的版本输入字段：v1 形状只收 any_of/all_of/field/op/threshold，未知 key 已拒绝。删除此未使用错误码或明确实际入口即可，不为它增加可选版本参数，更不需细分新的错误树。
4. `CN_A` 来自现有交易所映射，`symbol_identity` 本身未验证资产品类、币种或永久证券 ID。新界面不得把该字符串升级为“已核 A 股股票”；维持 source_claim/declared，首片不建证券主数据服务。
5. 价格事实/窗口见证每成员一份、原子引用共享事实即可。精确比例与原价受既有数值域约束，不再增加整份来源 schema 验证器。输入可信来源边界为现有 Store；合成纯函数 fixture 不充当真实来源认证。
6. 时间复杂度与加载次数预算合理。200k 行性能、512KiB 响应和 16MiB 增量内存属于待测工程门槛；不应通过截掉原因或取消原件核验取得达标。旧 API 字节级兼容须先锁 golden 再提取 evaluator。

## 6. 设计阶段实际核查与当时未运行范围

已读根 AGENTS.md、032、相关旧研究/评审约定，以及 daily_screen、universe_research、research_series、research_api、pair_research、numeric、Store、来源语义构建代码与集合界面。读取已有离线真实验收报告只用于核对 032 对历史证据的描述，未重新打开/计算私人行情或把其结果记作新功能通过。

实际运行：

```text
.venv/bin/python -m pytest -q tests/test_daily_screen.py tests/test_universe_research.py tests/test_research_projection.py tests/test_research_adversarial.py tests/test_research_api.py
114 passed, 1 skipped in 9.32s
```

跳过项为 `test_daily_screen.py` 的仓库外真实日线文件未提供。该 focused suite 验证既有行为，不能替代全 Python 回归或 032 实现验收。

另用本地只读合成探针确认：BaoStock applicability 字段、同槽多错误只保留首因、日期未知而旧 universe 仍有数值、市场映射未认证品类，以及上述四个精确阈值反例。未新增产品测试文件。

未运行：032 新功能/新 API、全量回归、真实来源新规则矩阵、性能、前端构建与浏览器、Windows、Pine 对照、用户复核任务、预测/收益研究。本审查不重复声称已经在线核查外部文献。只新增本 review；未改产品代码，未提交。

## 7. 作者回应与最终决定

作者已在 032 §11.1 逐项答复。2026-10-11 05:15 UTC 复核正文后，R1–R3 全部关闭：

| 项目 | 实际修订及复核结果 |
|---|---|
| R1 | §4.2 保留六个语义字段各自 applicability 的存在性/值及 source_semantics.scope，全部投影绑定身份；F16 明列 BaoStock known/CNY 的未验证适用性、absent/null/unverified。通过。 |
| R2 | §5.2 将 gate 封闭为共享 coverage_known 的日期定位判断；普通事实失败、字段数值失败、未知经济资格与整请求失败均分层。§5.1 明确枚举比较。通过。 |
| R3 | §5.3、§7.2、§8 收窄为各坏日期槽已有 primary reason，加日期 gate 和字段失败；同槽其余原始 checks 回查，不再承诺穷尽，也不复制 normalizer。F07 相应收窄。通过。 |

四个合法精确阈值反例、未使用版本错误码的删除、market 未认证品类的说明也已采纳。复核时研究文件 SHA-256 为 `d4afbeb1f12d496bae743700226a27730463ce8de8ef611712510eeb46af5fdc`；首次冻结稿为 `fe2ac9fe616e7edf110a09372cc9bb736b6a496831dfe81b3f89c61e248e36e5`。后续仅修改状态说明不改变本批准范围，若修改条件/来源政策则应重新复核。

05:17 UTC 最后核对：作者进一步收窄重复日期见证为 `date + ordinal=null + duplicate_date + query` 追溯，实际重复记录数从原查询核查，`coverage.duplicate_groups` 不变；原因发生数明确按坏日期槽计数。此更小方案获准，避免为精确重复行数新增扫描或改 normalizer。连同最终状态说明，032 冻结 SHA-256 为 `e60e99c1c195c2dc97d06459898c4b044679f4cec7b2a275f1617e775128bf1a`。

**批准的下一步**：先写异常输入、独立数值/三值参考及旧响应 golden，再实施单次共享事实提取、最小筛选纯函数与只读 API。新代码需独立实现审查，完成受影响回归、调用次数/预算和性能验证后才能称相应实现通过。

具体产品改动限于 `universe_research.py` 的私有 exact/证据辅助、`stock_filters.py` 和 `research_api.py` 新只读路由及必要测试。至少需要下列实现门槛：

- 提取辅助前锁定旧 `universe_report` 与完整旧 API 响应/analysis_id golden；提取后逐字节保持，不能刷新 expected 掩盖差异。
- 新旧错误 safe 集合逐码核对，未知程序错误使整请求失败；重复 query key、未知 query key、JSON 重复 key/非标准常量/错误层级、2,048 字节规则预算均有明确拒绝测试。
- 无效规则在 Store 计数/加载前拒绝；行数超限在 `_research_query`/公式前拒绝。用调用探针证实每请求 M 次计数、M 次加载/原件核验、M 次归一化，基线和筛选共用一次 evaluator；原子数增加不得造成二次加载或归一化。
- 全部原子记录、OR/AND 全组合、分母守恒、精确边界、来源 gate、applicability 和源 query 身份须有独立 oracle/负例；测试 oracle 不调用生产 evaluator。

本阶段不要求先做 UI。浏览器可用性不阻断纯函数和进程内只读 API 验证，也不因此取得 UI 已验收资格。

**继续独立待验**：离线真实新规则矩阵、UI/浏览器、Windows、Pine、用户任务价值和预测/经济收益。不得把本设计批准或既有 114 项测试转述为这些阶段完成。不批准新增通用 DSL、来源校验框架、跨请求缓存或原始数据/私人派生文件入库提交。

## 8. 独立实现审查（05:22 UTC 起）

审查范围为 `stock_filters.py`、`universe_research.py` 私有辅助和 `research_api.py` 新路由。reviewer 只新增 `tests/test_stock_filters_adversarial.py` 并更新本 review，产品修改仍由作者完成。

### 8.1 独立证据

- 从固定基线 `97d483f7` 直接读取旧 universe 源码，80 个随机含坏槽/重复/未定位/缺截止的矩阵与重构后结果逐字节一致；另将独立 24 矩阵合成输出 hash 固化到新对抗测试，未调用作者的 golden 生成方法。
- 45 个随机有效来源矩阵，直接从原价格字符串构造 Fraction 动量及独立全前缀峰值枚举回撤，并使用 60 位 Decimal ln/平方和核对 V。全部原子/支路/最终选择及见证均与独立参考对账。V 真值另严格比较报告实际 float64 的二进制值，不拿高精度估计容差改变真值。
- 日期未知、批次未定位、隔离源、行调整/身份冲突不能通过充分 OR 支路放行；可靠窗口之外坏价及 quantity/amount 错误不误封窗口价格；非有限/相互矛盾内部 fact 使整请求失败。
- HTTP 独立覆盖所有重复 query key、缺必填、重复 JSON key（含转义后的相同 key）、非标准常量、深嵌套、UTF-8 字节预算以及 2,048/2,049 精确边界。
- 11 个成员分别为十份 20,000 行及一份 1 行，总 200,001、无单成员超限，在来源加载/归一化前拒绝，避免只测到 per-series 限制。
- 对全部现有 safe-error 与新规则错误枚举逐个注入确认安全 400；未归类 ValueError/RuntimeError/TypeError/AssertionError 均为不泄露内容的受控 500，无部分结果。先请求成功再同尺寸改坏临时合成原件，下一请求仍 409 raw_object_corrupt；外部 Origin/Host 被拒。
- 调用探针确认六条件请求只做一次 evaluator、每成员一次计数、紧凑读取、原件核验和 daily_bars；共享原子的分母只计一次。

以上第一轮 19 项对抗全部通过；合并作者新测试和受影响旧 focused 为 **201 passed, 1 skipped in 12.38s**。该唯一 skip 仍为旧 daily_screen 仓库外私有日线缺失。

### 8.2 I1：缺截止时新实际窗口末端被填成请求日期

**实现验收阻断，局部修复即可。** 2026-10-11 05:29 UTC 新增反例稳定失败：来源仅有 01-01/01-02，要求 D=01-03 时，新 `window.actual_groups=0` 且 first/last 都 null，却 `window.end_date=01-03`。后者由旧 universe 的请求端字段继承，不能充当新合同承诺的实际窗口端点。

要求只修新窗口投影：窗口为空时 start_date/end_date 均 null，cutoff 保留请求 D；旧 universe.end_date 与旧 golden 保持原样。失败测试为 `test_missing_cutoff_has_no_fabricated_actual_window_endpoint`。已通知作者；修复及最终复验结果在下节追加。上述 201 通过不含本条随后新增的失败反例。

另发现正文曾要求错误附字段路径，实际沿用现有仅 `{error: code}` 的受控 HTTP 形状。建议作者收窄正文承诺，避免为可选诊断新增通用错误框架；此项不影响安全拒绝与真值。

### 8.3 I1 关闭与有界响应投影复核（05:46 UTC）

**I1 已修复并通过独立反例。** 新窗口首尾取实际 bars；空窗口 start_date/end_date 为 null，cutoff 保持 D。旧 universe 输出与 golden 没有改动。安全错误码的正文也已对齐现有 `{error: code}`。

作者资源试验暴露初版 50 成员响应增量超出 256KiB。审查要求保留硬门槛，并增加混合合同、多个坏槽类别、每类 8 见证/omitted、日期 gate 和原价极值病例，不能靠删失败或只验全有效样本取得通过。经过两轮可读、无损的局部投影精简，批准如下最终形状：

- `result.source_contracts[]` 只共享本响应中完全相同的固定投影；每个 `sources[].contract_ref` 可解引用。按完整投影内容 hash，不按来源声明的 source_contract_id 盲合并；每源 metadata/identity/raw/query 仍单独保留。
- `result.conditions[]` 每条唯一规则原子只记录一次 field/op/threshold。aN 为 rule-local；成员原子保留 id/truth/fact_ref/reason_refs，comparison_type 从该 fact 取得，窗口从成员 window_ref 取得。组 gN 同样 rule-local。
- reason rN 为 member-local；每个见证为 `[date, ordinal]`，以固定 `result.reason_example_fields` 解码。计数、至多 8 见证及 omitted_count 全部保留。
- rule/analysis/source/window 身份仍为完整哈希；source_metadata_id 绑定 sources 与共享合同表的完整内容。局部短 ID 不能脱离对应 rule_id 或成员上下文单独缓存/解释。

reviewer 新增三项独立复核：按共享投影完整重建原 source.id；同 source_contract_id 下 absent/null/unverified applicability 不误合并，只有完全同投影才共享；所有 a/g/r/contract/window 引用可解、字段及语义可还原，31 个坏槽保留 8 见证和 23 omitted。每源 metadata 的 null/原值变化改变 metadata/analysis 身份，且不改原 universe 的 base_analysis_id。

最终独立文件 **23 passed in 1.94s**，无失败/跳过。文件 SHA-256：`3bbcb437b5e557cae7ba38b1c1fb6d17b8c4df7da83a3ec4bcefa54742708238`；受审 `stock_filters.py`：`345b54b8683ffaf487b277931f46a550dcbe2d559fba313a423d5542d94dc571`。此时无剩余实现审查阻断；已通知作者测试冻结，可执行全量联合回归。

作者报告的最终可信 Store 资源病例含 BaoStock 调整 1/2/3、TDX native、Tencent legacy 五种合同：50 成员重坏槽新响应 297,975B、旧 envelope 45,011B、增量 252,964B；全有效原价极值新 241,646B、旧 43,842B、增量 197,804B。两例符合 256KiB 增量/512KiB 总量硬门槛。以上是作者试验结果，本 reviewer 本轮直接运行的是功能/引用对抗测试；资源证据由作者随验收文件保存。

短资源观察可使用一次预热加五次交错成对采样，报告实际中位、范围和样本数；它不建立原先 30 次样本的稳定 p95 资格。不得将短观察达标改写为所有性能门槛已完成。最终全量回归、离线真实矩阵及其源码 hash 由联合验收记录承接。

### 8.4 冻结后的联合回归及真实矩阵证据核对

05:50 UTC 已只读核对联合 `pytest-full.log` 与前后源文件摘要：**2200 passed, 49 skipped, 1 warning in 84.56s**；进程退出码 0，107 个 src/tests Python 文件前后 hash 完全一致，当前筛选源码 hash 与 §8.3 相同。49 项跳过不计通过；该 warning 是既有 Starlette/httpx TestClient 弃用提示，本片不顺手改依赖。

同样核对仓库外最终真实报告：固定 60 配置、240 次筛选 API 加 20 次旧集合 API、600 个配置×成员判定全部通过，非预期失败 0。该报告用最终 345b54…c571 源码重跑，已将早期响应存入 superseded 记录而不混计；真实缺截止窗口也明确断言 start/end=null。完整共享目录和身份另经展开核对，旧混合集合 API 响应与先前保存字节相同。两类报告各自有边界，真实来源重复配置不能称为 600 个独立市场样本。

这部分是对其他验收执行者留下的日志、版本摘要与报告的独立只读核对，未再次运行私人行情矩阵；不复制真实成员行情或派生响应到仓库。正式六配置资源观察尚在进行，待最终 COMPLETE 后追加结论；目前不宣称其已完成。

### 8.5 正式六配置资源观察首轮核对（06:07 UTC）

已直接读取正式 results.json 和 COMPLETE 日志：六配置各五对齐全，前后源码 hash 与受审版一致。六个配置的中位时间、新解释层时间、增量/总响应字节均通过本轮观察门槛；逐对耗时 29/30 通过，RSS 4/6 通过。未达项完整保留：

| 配置 | 未达项目 | 实际情况 |
|---|---|---|
| 10×5,000，N=252 | 第三对请求耗时 | 超出该对 `1.15×baseline+20ms`，虽该配置中位通过，不能隐藏这一对 |
| 10×20,000，N=20 | 独立进程峰值 RSS 差 | +23.7734MiB，超过 +16MiB |
| 10×20,000，N=252 | 独立进程峰值 RSS 差 | +68.1953MiB，超过 +16MiB |

未将原因推断为机器噪声或产品泄漏。按主任务授权，对上述三个配置各进行一次完整五对复测，原始六配置结果不覆盖；复测与必要诊断结束后再给资源最终状态。功能/API 与真实来源兼容的通过仍独立成立，**当前不能称全部资源门槛通过**。

### 8.6 最终决定与未达项保留（06:18 UTC）

已只读核对三个失败配置的完整复测原始结果、REPLICATION COMPLETE 日志及四次阶段内存诊断，源码仍冻结，采样已停止：

- 复测 15/15 个耗时对通过；首轮单对时间未达仍保留。其超限约 2.05ms，不据此改阈值或称首次通过。
- 10×20,000/N20 的 RSS 差由首轮 +23.7734MiB 变为复测 **+43.4922MiB**，两次均超过 +16MiB。该项明确未通过。
- N252 的 RSS 差由 +68.1953MiB 变为 −66.8789MiB；后一次负差不取消前一次失败，也不证明新算法降低了内存。
- 四次额外阶段诊断记录 Python、PYTHONHASHSEED、after_load/after_evaluator/after_request 的 VmRSS/VmHWM。该批 filter_report 的新解释层没有进一步抬高各自进程 VmHWM；较大的内存已在来源加载阶段出现。它们只给出额外定位证据，不能抵消 RSS 门槛未达，也不能确定此前差异的因果来源。

**功能/API 实现审查通过。** I1 已修复；规则、数值、三值逻辑、共同日期 gate、来源资格、身份、引用、预算拒绝和读取次数没有剩余已知功能阻断。23 项独立对抗通过，包含在最终 2200 通过/49 跳过中；最终真实 60 配置通过，双方均绑定同一受审源码。允许以这一明确阶段继续界面联调。

**资源阶段部分通过。** 正式首轮及一次有界复测的中位时间、纯新增解释层、响应字节等观测已保留，但 RSS 门槛未通过，首轮存在一对时间未达，30 次稳定 p95 未验。不得将此版本描述为全部性能验收通过、全面跨平台完成或具备预测/收益增量。后续资源诊断/优化应保留冻结输入、原件核验、全成员证据和既有数值合同，另行记录范围及重新验收，不能通过删来源检查或放宽门槛修饰结果。

完整实现/观察状态以[stock-filters 实现验收](../qualification/stock-filters.md)承接。reviewer 最终仅改本 review 与 `tests/test_stock_filters_adversarial.py`，未改作者产品代码、未提交。最终受审产品和专属测试 SHA 与 §8.3/§8.4 一致；文档状态改动不影响该冻结。
