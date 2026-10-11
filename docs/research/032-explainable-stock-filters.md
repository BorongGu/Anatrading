# 032 · 同截止、有限条件的可解释股票筛选

日期与官方资料访问：2026-10-11。状态：**最小纯函数与只读 API 已实现；最终联合 Python 回归及冻结真实矩阵通过，合成资源观察单列。** 实际范围与未完成项目见[实现验收](../qualification/stock-filters.md)。 最终决定见[独立审查](../reviews/2026-10-11-explainable-filters-review.md)。承接 [031 A](031-tradingview-advanced-roadmap.md)、[026 §7](026-causal-signals-and-evaluation.md) 和 [019](019-current-pool-daily-screen.md)。不依赖尚未验收的 030。

## 1. 结论：有一项小增量，避免重建筛选器

建议下一片只解决：**对已选 2–50 份同市场日线版本，在同一截止 D、同一来源步数 N 下，给现有动量、波动、收盘路径回撤设置有限条件，逐股解释入选、排除和暂不可判定。** 三项数值及排序继续来自现有集合计算。条件最多两组，组内 AND、组间 OR；不引入新趋势指标、综合评分、指标插件、表达式字符串执行器或参数寻优。

新增价值有三点：已有集合结果可直接回答明确条件；两种有限条件组合可以并列；所有成员和条件都保留，用户能够从结果复核证据、失败和分母。尚无证据证明它改善选股预测或交易收益。若试点显示用户只需现有排序或现有四项 AND，停止扩展 OR/UI，保留本研究的无增量结论。

### 1.1 已有能力精查

核读 HEAD `97d483f7ab2d0eb5e43ba81eb5c24b6e0be08272` 的以下文件；研究期间并行工作不计作已验收功能。

| 位置 | 已有能力 | 本片不重复的部分及真正缺口 |
|---|---|---|
| [daily_screen.py](../../src/anatrading/daily_screen.py)、[019](019-current-pool-daily-screen.md)、[测试](../../tests/test_daily_screen.py) | 对指定采集 run 的当前来源池，通道位置、方向、源数量比、路径效率四项 AND；逐条件 true/false/null；量比/效率用 Fraction 精确比较；保留全 pool、缺缓存、失败、未处理分母 | 逐条件解释、精确阈值和覆盖守恒已经存在。当前筛选依赖已记录的 native cache/run 证据，字段和成员入口均与集合研究不同；没有所选导入版本的动量/波动/回撤条件和 OR |
| [universe_research.py](../../src/anatrading/universe_research.py)、[测试](../../tests/test_universe_research.py) | 同截止的三项数值、实际窗口、独立有效分母、精确动量排名、来源身份及覆盖 | 数值已经存在，不重新实现；公开动量/回撤输出为 float，计算过程中已有精确 Fraction，新增精确条件不能从 float 倒推 |
| [research_api.py](../../src/anatrading/research_api.py)、[Store](../../src/anatrading/store.py) | 先计预算、原件逐请求核验、内部完整前缀紧凑投影、完整公开 query_id、确定性 analysis_id | 复用一次加载，不增加逐条件查询、跨请求通用缓存或截尾读法 |
| [CrossResearch.tsx](../../web/src/CrossResearch.tsx)、[DailyScreen.tsx](../../web/src/DailyScreen.tsx) | 集合页按动量展示；其“筛选已导入日线”只是代码/名称搜索；另有四项日线条件页 | 不把名称搜索当数值条件；只在集合结果旁增有限条件及证据视图，无第二套集合选择器 |
| [research_series.py](../../src/anatrading/research_series.py)、[pair_research.py](../../src/anatrading/pair_research.py) | 严格日期组、坏/重复槽、身份声明与冲突处理 | `coverage_known` 只描述源日期可定位性，不能翻译为交易日历完整 |

旧 `daily_screen` 的 AND 资格要求所有启用项可评价；它还允许无条件记录。本片必须显式处理 OR 的已知充分条件，不能机械复制该总资格门槛。旧页面、既有接口、方法身份和无条件行为不变。

## 2. 实际阅读的外部依据与竞品基线

以下为文档核查，未登录 TradingView、未运行 Pine、未实测套餐。本文阈值、逻辑资格、预算和实现选择属于本项目设计。

| 资料与阅读范围 | 直接支持的事实及本片用途 |
|---|---|
| [TradingView Pine Screener 官方要求](https://www.tradingview.com/support/solutions/43000742436-tradingview-pine-screener-key-features-and-requirements/)，Selecting an indicator、Setting up filtration、Requirements | 可用自选池/指数与自定义 Pine 指标，以 plot/alert 条件筛选。一个指标能有多个输出；默认加入前十个 plot 和两个 alert 条件。每屏一个指标、末 500 柱、指数来源至多 4,000 符号、至多 40 个独立 request 调用。支持日线，输入/来源/周期/条件变化后需要重扫。不能据此声称竞品仅有单条件或缺少自定义筛选 |
| [TradingView ROC](https://www.tradingview.com/support/solutions/43000502343-rate-of-change-roc/)，Definition、Calculation | 官方公式 `100 × (C_t-C_(t-N))/C_(t-N)`。本片动量为其比例值，即 ROC/100；来源记录日期窗口不自动等于一致日历窗口 |
| [NIST Measures of Scale](https://www.itl.nist.gov/div898/handbook/eda/section3/eda356.htm)，Definitions of Variability 1–2 | 样本方差使用 N−1，标准差取平方根。用于核对现有波动的 ddof=1；对数价格差作为输入、不年化属于本项目口径 |
| [Pine v6 Type system](https://www.tradingview.com/pine-script-docs/language/type-system/)，float、bool、na | v6 bool 只有真/假，不能为 na；浮点比较另有九位小数规则。对照脚本必须另编码缺失状态，不能直接把 bool 的 false 当“已知不满足”；精确阈值也不直接拿 Pine bool 当最终数值裁判 |
| [Pine v6 Operators](https://www.tradingview.com/pine-script-docs/language/operators/)，Comparison、Logical；[v6 migration](https://www.tradingview.com/pine-script-docs/migration-guides/to-pine-version-6/)，Lazy evaluation | Pine 有 AND/OR；v6 会短路。官方提醒依赖历史的函数应先逐柱求值再组合。本片同样先算事实与全部启用条件，之后组合，不能因先遇到真/假就略去失败 |

访问限制：Pine `ta.stdev` 动态参考页本次未取得函数正文，因此不将其默认分母、缺失处理写作已复核事实；波动对照按下节公式显式实现。收盘路径最大回撤沿用 026 的已实现定义，不冒充 TradingView 策略权益回撤。

### 2.1 可复做的 Pine 对照任务

若以后具备账户和合法同源输入，使用一个脚本输出 M、V、DD、各自可用状态、总体状态；固定 1D、N、价格尺度和截止，最多需要六个数值 plot。脚本先检查固定 N+1 槽，再显式循环计算本节公式；不使用忽略 na 后补满 N 根的实现。三态可用整数 `1/0/-1` 表达，并独立输出原因/可用性，避免 v6 bool 吞掉未知。公式组合与本片相同，不能挑一个功能较弱的竞品默认脚本作为唯一基线。

无法在 Pine Screener 重现同一冻结历史截止、源日期组或来源资格时，记录该任务未完成可比输入，不判竞品失败。500 柱可覆盖本片最大 253 个价格槽，但不会自动解决历史版本或缺失槽差异。禁止为竞品试验上传个人受限行情。此对照目前**未跑**。

## 3. 固定范围与参数合同

### 3.1 唯一规则形状

只接收 `any_of` 数组，长度 1–2；每个元素只含 `all_of`，长度 1–3。原子只含 `field`、`op`、`threshold`，组内同一 field 至多一次。总原子出现次数最多 6，跨组相同原子只计算一次。无递归组、NOT、函数、字段间运算、脚本、正则、动态属性、排序条件、行业/同行条件、未来标签或外部数据请求。

| field | 唯一 op | 阈值闭区间 | 业务显示及单位 |
|---|---|---|---|
| `momentum` | `gte` | [−1, 10] | N 来源区间收盘价变化至少多少；比例，0.05 表示 5% |
| `volatility` | `lte` | [0, 1] | N 来源区间 log 变化的样本标准差至多多少；0.02 是 0.02 log 单位/来源区间，不是年化 2% |
| `max_drawdown` | `gte` | [−1, 0] | N+1 个 close 的最大回撤不低于某个负值；−0.10 表示路径跌幅不超过 10% |

这些阈值上限是 v1 输入边界，不是有效价格变化的上限，也没有经济最优性。实际 M 或 V 超出阈值范围仍按原值比较，绝不截平。需要反向操作、价格水平、双边区间或其他范围时另提具体研究问题；本片不扩展成 DSL。

阈值必须是十进制字符串，以正则 `-?(0|[1-9][0-9]?)(\.[0-9]{1,18})?` 做 fullmatch，总长最多 22 字符；再用现有 `decimal_value` 和字段范围核验。拒绝数字型 JSON、bool、NaN、Infinity、指数格式、空白、百分号和超精度；以 `decimal_text` 规范尾零与负零。UI 如使用百分比输入，必须精确字符串变换到比例并回显实际阈值，不经 JS 浮点乘除转换精确条件。

共同参数：`cutoff=D` 必填严格 ISO 日期；`lookback=N` 是严格 int 2–252，缺省 20；所有原子共享 D/N，不能局部覆写。成员 2–50、同一规范市场、每证券只一版本。规则至少一原子，不接受空组和无条件匹配。

规则例子仅用于演示，无最优阈值含义：

```json
{
  "any_of": [
    {"all_of": [
      {"field": "momentum", "op": "gte", "threshold": "0.05"},
      {"field": "volatility", "op": "lte", "threshold": "0.02"}
    ]},
    {"all_of": [
      {"field": "momentum", "op": "gte", "threshold": "0.10"},
      {"field": "max_drawdown", "op": "gte", "threshold": "-0.08"}
    ]}
  ]
}
```

它表示两条明确备选标准，不声称前者或后者更优。参数每次变更生成新 rule_id/analysis_id，保留研究记录中的全部尝试及失败；当前单截止实现不建设数据库试验管理平台，也不宣称已自动保存全部历史尝试。

### 3.2 精确公式与比较边界

按成员 i 选定的窗口记作 `d_0 < ... < d_N=D`，对应正收盘价 `C_0,...,C_N`。三个字段共用完全相同窗口：

1. 动量 `M=C_N/C_0−1`。用源 Decimal 转 Fraction；比较 `M >= Fraction(threshold)`，不经过显示 float。
2. `r_j=ln(C_j)−ln(C_(j−1))`，`r_bar=sum(r_j)/N`，`V=sqrt(sum((r_j−r_bar)^2)/(N−1))`，j=1..N。复用 `_volatility` 的 float64、`math.fsum`、ddof=1 及有限性检查。无 sqrt(252)，无无条件 Winsorize、平滑或填价。V 为近似数。
3. `P_j=max(C_0,...,C_j)`，`DD=min_j(C_j/P_j−1)`，j=0..N。运行峰值从本窗口首价开始；Fraction 精确比较 `DD >= Fraction(threshold)`。范围 (−1,0]，平坦/单调上升路径为 0。峰后恢复仍保留早先回撤；不用 `C_N/max(C)−1` 替代。

V 的筛选合同是**对当前计算得到的有限 float64 估计比较**：将 V 用 `Fraction.from_float` 表示其二进制精确值，与精确阈值 Fraction 执行 `<=`。这只精确比较已算估计，不把 V 升级为精确数学标准差。响应同时给最短往返小数字符串和 `float_hex`，允许独立重建比较。显示舍入、测试容差和 Pine 的九位比较均不参与筛选真值；未设置偷偷放宽阈值的 epsilon。

不同数学库/平台可能在边界末位产生差异，因此不预先承诺跨平台临界真值一致。Windows/不同环境验收须专门检查相邻浮点阈值；出现差异时披露原估计和环境，阻止跨平台一致性声明。稳定范围与临界范围分别报告，不能用放宽测试容差掩盖条件反转。若独立审查认为必须数值安全带，它需要明确的新比较版本和 unknown 规则，不能临时加入。

有限性失败只关闭相应字段。未启用的 V 失败不影响纯 M 条件。已启用 V 失败成为其原子的 unknown，OR 如何处理见 §5。相同源价格乘正常数时 M/DD 精确不变，V 只要求数值容差内不变；不保证近阈值分类在任意 float 重标度后不变。

## 4. 数据窗口、来源与资格

### 4.1 先定位槽，再验证价格

- 只接受完整来源前缀的日线查询；不接受 ordinal_start/end、图窗初始化、客户端已筛掉坏行的结果。使用现有 `_load` 的查询与 `daily_bars`，不把缺日造为零收益。纯函数输入若声明 selection.cutoff<D，拒绝 `research_cutoff_mismatch`；None 或较晚 cutoff 可以按 D 收窄，来源全批未定位统计仍保留。HTTP 始终直接加载所请求的 D。
- 已知 D 之后的行先排除。窗口是 D 及此前恰 N 个来源日期组，坏组、重复组占位；它们不能被更早有效值替换。D 缺失即 `cutoff_missing`，不回退末日；不足 N+1 组为 `history_insufficient`。
- 所用槽的 OHLC 均需通过现有正值、有限、low≤open/close≤high 检查，即使公式只用 close。保持与 026 的数据资格一致。volume/amount 缺失不阻价格条件。
- 证券身份顶层冲突使整请求拒绝。窗口内源身份冲突、调整冲突、隔离样本、坏/重复价格使相关事实不可用；已知未来坏行不影响过去。
- 新筛选增加明确的**源日期定位门槛**：成员 `coverage.coverage_known=false` 时，所有价格原子 unknown，原因 `date_set_integrity_unknown`。原 universe 可能仍显示条件性数值，本片保留其原样并标“不可用于此次筛选”。全批不可定位行无法证明位于截止之后；不得因其他指标为真绕过此门槛。
- `coverage_known=true` 只证明所统计源标签可定位且无全批未定位行；不证明无缺交易日、无停牌、同步采集或闭合。不得据此提供“覆盖 100% 交易日”条件。已知历史范围之外的普通坏价，不使有限窗口自动失效；全批日期未知另作上述保守处理。

每股保存 `cutoff`、实际 `start_date/end_date`、`window_unit=source_date_groups`、期望/实际日期组数、有效价格数、有效相邻区间数。各股同为 N=20 时起点仍可不同；规则显示“20 来源区间”，不写“20 交易日/月收益”。历史成员、共同日历窗口条件和任意行业分类均未开放。

### 4.2 来源 metadata 不因筛选通过而升级

每股来源摘要来自这次已经加载的 query/manifest，不另查库：

- `snapshot_id`、完整公开 `query_id`、`manifest.raw_sha256`、`source_contract_id`、格式/解码版本；`symbol_identity` 原样保留 `source_claim`/`declared` 等资格。
- metadata 摘要白名单固定为 `period, source, source_code, source_venue, source_symbol, requested_symbol, requested_adjustment, capture_version, capture_mode, header_cardinality, transport_evidence, provenance_hash_verification, interpretation_status, source_claims_status`。不存在的字段用 `{present:false,value:null}`；存在时 `{present:true,value:原值}`，禁止造出 known/verified，也不把缺失与显式 null 混淆。
- 从 `manifest.contract.source_semantics.fields` 原样保留 price_unit、adjustment、label_definition、closed、known_at、first_published_at 各自 value/status/reason/**applicability**，各项均使用上述 present/value 结构区别 absent、显式 null 和原值；同样保留 source_semantics.scope 的存在性和值。证据数组不复制进每个原子，以 source_contract_id 和字段路径回查。保留 `metadata.interpretation_status/source_claims_status`。BaoStock 的 `price_unit=known/CNY` 必须连同 `reason=documented_meaning_only, applicability=unverified` 展示，不能把文档单位解释升级为本样本适用性已验证；实际投影全部进入 source_metadata_id。
- metadata 缺少标准化字段时保持 unknown/absent，不能推断 `requested_adjustment=none` 等于已核实未复权，不能把获取时间填作历史 known_at。

结果固定 `mode=retrospective`，`qualification=conditional_source_price_filter`；常驻限制至少为来源版本回顾、调整依据未知、历史可得性未知、日历及闭合未知、当前明确样本和非交易收益。M/V/DD 的真值仅在“窗口内来源价格尺度可比”条件下描述输入。未知复权/可得性本身保留限制，当前不一刀切关闭全部价格描述；明确冲突/失败按 §4.1 关闭。筛选入选与来源经济资格分开，不能显示“已验证买入信号”。

### 4.3 当前真实证据的可用范围

本次只阅读仓库外已有 `research-validation-2026-10-11/report.md`，未新抓数据、未重跑该报告。该报告已有 89 配置、286 次进程内请求、48 个合格集合窗口独立数值核对；这属于现有功能证据，不是 032 通过数。

可直接继承其固定 10 成员、N=20 和五个截止用于后续本片验证：2026-10-09；2025-09-05/09；2025-12-31/2026-01-05。两处缺截止须保留 1/10 不可判定，复牌后恢复有值；复牌窗口分别出现 2025-08-04 对 08-12、2025-11-21 对 12-04 的不同起点，必须逐股显示。真正应有多少入选，须由冻结规则的独立参考算出，不从已有报告补造。

当前 30 股与当前分组均为明确选择；复权、known_at、闭合和若干单位未认证。只支持 source-price retrospective 研究，不能给历史全市场、历史行业、总收益、选股胜率或预测增量资格。仓库只存合成测试和验收摘要，不提交真实价格、成员派生响应或私有报告原件。

## 5. 真/假/未知、选择与失败解释

### 5.1 标准三值逻辑与全量评价

原子结果为 `true | false | unknown`。未知表示计算/依赖证据不能决定该条件，原因必填；它不等于 false、0 或缺省通过。AND/OR 采用以下 Strong Kleene 表，不实现 NOT：

| A | B | A AND B | A OR B |
|---|---|---|---|
| T | T | T | T |
| T | F | F | T |
| T | U | U | T |
| F | T | F | T |
| F | F | F | F |
| F | U | F | U |
| U | T | U | T |
| U | F | F | U |
| U | U | U | U |

先计算三项共享事实，再对所有唯一启用原子求值，再求每组 AND 和最外层 OR。调用 Python `all/any` 前必须已经物化所有原子结果及其原因，且必须显式比较枚举值，不能将三个非空字符串直接按 Python 布尔值归约。不能让表达式短路导致未算条件、未记录失败或少查原件。重复原子引用同一已计算证据；组序、成员序不改变结论。

### 5.2 分开三层信息，明确选择政策

每股均输出：

1. `source_gate`：**当且仅当共享 `daily_coverage.coverage_known=true` 时为 pass，否则 unknown、原因 date_set_integrity_unknown**。此定义封闭，gate 只回答源日期可定位性；unknown 使所有价格原子 U。缺截止、短历史、重复/坏价、窗口身份/调整冲突、隔离源沿用共享事实 reason，使相关 M/V/DD 原子 U，均不另改日期 gate；`numerical_failure` 仅作用于失败字段。未知 adjustment/known_at 继续为限制；顶层身份冲突和 Store 读取/原件失败仍整请求拒绝。gate=pass 不能显示为“来源已验证”。已知底层原数值仍可查看，不充当被 gate 关闭的筛选证据。
2. `logical_truth`：上表组合的 T/F/U；`evidence_complete` 是所有启用原子均非 U 的独立布尔值。
3. `selection_state`：`selected` 当 source_gate=pass 且 logical_truth=T；`excluded` 当 source_gate=pass 且 logical_truth=F；其余为 `undetermined`。`partial_evidence` 在 evidence_complete=false 时为 true，始终可见。

**拟采用的 v1 决定：合法且证据完整的 OR 支路足以证明整体为真；另一支路的未知保留告警，不自动否决已证明的充分条件。** 每条成立支路必须所有原子均 T，不允许以未知证明成立。相似地，一个已知假条件可排除该 AND 支路，其他未知仍完整披露。

例如 §3 的规则：M=0.12、DD=−0.03、V=`numerical_failure`。第二组已知 T，第一组 U；总体 T，入选且 `partial_evidence=true`，解释为“满足第二组；第一组波动不可评价”。这不是把未知填真。若 M=0.08、DD=−0.03，则第二组 F、第一组 U，总体 U，待核查。若源日期不可定位，所有价格原子 U，不能借 OR 放行。

替代方案“所有启用原子已知才允许入选”会让前一例待核查，也会使增加一条不必要的 OR 支路降低已有确定入选率。它可以作为单独、显式的研究政策，但与用户给定 OR 的常见含义不同，本片不默认采用。**独立反方必须就此真实反例确认选择政策；若改选严格总资格，必须保留 logical_truth=T 与 selection_state=undetermined 两层，写明阻断原因，不能声称 T OR U=U 是标准三值 OR。**

逻辑成立只回答来源价格条件，与 `known_at/adjustment` 资格完全分开。未启用字段有问题留在基线诊断中，不影响 evidence_complete。任何无法归类的程序异常使整请求失败，不吞为可选择的未知分支。

### 5.3 解释和守恒

`result.conditions` 每规则只保存一次 `{id,field,op,threshold}` 条件目录。每股原子返回 `{id,truth,fact_ref,reason_refs}`，由 id 唯一解引用 field/op/规范阈值，由本成员 facts[fact_ref] 取得 comparison_type/原值，由本成员 window_ref 取得窗口。精确 fact 返回最简 numerator/denominator 字符串，估计 fact 返回 value/float_hex。真假解释按这些完整引用展示原值与比较方向，不能仅显示“条件不符”。

- selected：列出全部成立组，逐组可展开其全部 T 原子；partial_evidence 时并列所有未知组/原子与原因。
- excluded：每一 OR 组都至少一 F，列出每组全部 F 及仍有的 U；不能只挑一条看似有解释力的失败。
- undetermined：列出尚未被已知 F 排除的 U 组及其未知依赖，也保留其他组已知 F。共同来源门槛失败优先展示，但不删底层已有失败。
- `primary_reason` 仅供首行；完整 reasons 是稳定排序的去重集合，不因主原因优先级丢失另一个坏组。排序为日期门槛在前，再按 code、scope、field（null在前）；首项作 primary；各类样例沿已排序窗口顺序。对每类原因保留总发生数、至多 8 个源日期/ordinal 示例和显式 omitted_count。固定 `result.reason_example_fields=["date","ordinal"]`，每条 examples 为 `[date,ordinal]` 二元行；保留 null 及原始源序号。样例截断不截断原因类别或统计，不改变原本八条见证上限。

这里“完整”指全部启用条件、全部选中日期槽的现有归一化 reason、全局来源拒绝及各数值字段失败均未因筛选短路丢失。现有 `_bar` 在同一坏行中只给一个主 reason，本片不扩展成另一个原始行校验器；该行的原始 checks 通过 query/ordinal 回查。不能把这些归一化 reason 宣传成已经枚举原件中全部可能缺陷。

对 M 个成员强制：

```text
selected + excluded + undetermined = M
logical_true + logical_false + logical_unknown = M
evidence_complete + partial_evidence = M
每一唯一原子：true + false + unknown = M
每一组：true + false + unknown = M
source_gate_pass + source_gate_unknown = M
```

各组入选数可重叠，不能相加当最终入选数。原 universe 三项有效/缺失/无效/短历史分母原样并列；不因新资格门槛改写旧结果。展示入选/M、不可判定/M；如给入选/逻辑已确定数，必须明确第二分母且零分母为 null。入选、排除、待核查默认都可见，每股恰出现一次，集合内排名不因过滤而重排成“原第 1 名”。

## 6. 纯函数结果与确定性身份

### 6.1 最小结果形状

首片是纯函数与只读 API；名称以下述合同冻结，具体内部函数名可由实现选择。输出包含：

```text
method_id = selected-source-price-filter-v1
mode = retrospective
inputs[] = 规范顺序的 snapshot_id, query_id
parameters = cutoff, lookback, canonical_rule, policy_versions
rule_id, analysis_id, base_analysis_id
limitations[], qualification
result.universe = 原 universe_report 结果（不变）
result.sources[] = 每股 snapshot/query/raw/identity/metadata/id/contract_ref
result.source_contracts[] = 固定合同投影，按完整投影内容哈希去重
result.conditions[] = 每规则一次的 id/field/op/threshold 目录
result.reason_example_fields = [date,ordinal]
result.members[] =
  identity, snapshot_id, source_ref, window_ref,
  source_gate, logical_truth, selection_state, evidence_complete,
  facts, atoms, groups, reasons, proof_groups
result.counts = §5.3 守恒计数
```

`facts` 每字段只一份；`atoms` 最多 6 个，引用条件目录和本成员 facts/reasons；groups 最多 2 个，引用 atom_id。`member.window` 为每股唯一窗口对象，window_ref 为其 id；保留实际窗口首末日期（空窗口均为 null，cutoff 另保留请求 D）、源首末 ordinal/close 和回撤峰谷见证（价、日期、ordinal）。重复日期见证仅含该日期、ordinal=null、duplicate_date 及 query 追溯，不能伪造唯一 ordinal。原因发生数为坏日期槽数，coverage.duplicate_groups 原样保留；实际重复源记录数通过原查询核查，不改 normalizer 或另扫描。窗口全体成员用冻结 query+N+归一规则重建，无须在六个原子重复携带窗口。

`source_contracts` 只共享固定字段 `source_contract_id,format_id,contract_version,versions,semantics_scope,semantics` 的完整投影；其 id 为该投影（不含 id）的 `_identity`。绝不只按 source_contract_id 猜测两个摘要相同。sources.contract_ref 必须能唯一解引用，源特有 code/request/legacy flags 等 metadata 留在每源条目。sources.id 仍为**解引用后完整来源摘要**（不含 id/contract_ref）的身份；共享表只是无损表示。`source_metadata_id=_identity({sources,source_contracts})` 绑定完整共享表和全部实际源投影，引用目标不得缺失或多义。不引入通用压缩/反序列化或跨请求缓存框架。

`window_id` 哈希输入为 snapshot_id、公开 query_id、cutoff、lookback、`daily-source-date-groups-v1` 及实际 start/end。它标识可重建的选择，不宣称对未输出窗口字节做了单独认证。定位未知时仍有来源引用，window 起点可为 null。完整原价/检查通过原有公开 Store 查询查看；筛选响应不能冒充该完整查询的替代导出。

### 6.2 canonical_rule、身份与失效

1. 先规范整个 rule，再将其全部唯一原子按 `(field, op, canonical_threshold)` 排序，赋规则内 `a1..a6`；同组重复 field 拒绝。组内原子按上述三元组排序，组按其规范 JSON 内容排序后赋 `g1..g2`；完全重复组拒绝。跨组复用同一 aN，不自动吸收或化简逻辑。aN/gN 仅在该 rule_id 下有意义；每成员 reasons 按 §5.3 固定顺序赋 `r1..rN`，rN 仅在该成员/analysis 下有意义。全局 analysis/rule/window/source/contract 哈希不缩短。语法不同但数学等价的规则不保证同 rule_id。
2. 精确哈希合同为 `rule_id=_identity({canonical_rule, policy_versions})`，复用 Store 的规范 JSON SHA-256。`policy_versions={rule_schema:"bounded-price-filter-v1",window:"daily-source-date-groups-v1",logic:"strong-kleene-eager-v1",comparison:"fraction-and-binary64-v1",source_gate:"source-date-locatability-v1"}`。不含 UI 名称、输入次序、显示位数或运行时间；前端只校验服务端回显匹配，不自行重造规则真值或另猜一套哈希形状。
3. inputs 按 snapshot_id 排序；保留 `symbol_identity` 的市场与身份资格。`analysis_id=_identity({method_id, inputs, parameters, rule_id, source_metadata_id})`；source_metadata_id 绑定 §4.2 固定摘要的完整规范内容。所有默认值显式展开，policy_versions 至少包含公式窗口、三值逻辑、数值比较及来源门槛版本。
4. `base_analysis_id` 按现有 `selected-universe-research-v1`、同 inputs/参数精确重建，不调用原 HTTP 路由、不再加载一次。原接口结果与身份逐字节兼容。
5. 同来源版本、截止、参数和软件环境，重复、关闭重开、成员/组/原子顺序变化，整个确定性结果应一致。改变阈值、D/N、成员、来源版本、资格 metadata 或政策版本必须改变相应身份。时间戳和耗时放外部验收日志，不进确定性响应。
6. 追加或修改已知未来日期：同前缀的事实/条件/计数不变；若来源内容变了，snapshot/query/analysis 身份应变化，不能要求整响应跨快照字节相等。追加不可定位日期可能使来源门槛转 U，这是保守证据变化，必须与已知未来不变性分开验收。

前端只展示服务端真值，不复制 Fraction/float 筛选算法。参数、截止、成员改动立即使旧报告失效，沿用 Generation/AbortController；新响应必须匹配 rule_id、inputs 和 D/N，旧请求不能覆盖新状态。UI 连通与真实浏览器验收为后续独立门槛。

## 7. 错误、预算与失败处理

### 7.1 先验请求错误

拟新增只读 `GET /api/research/universe-filter`，白名单参数 `snapshot_ids,cutoff,lookback,rule`。`rule` 为 JSON 对象的编码值，无可执行字符串。复用现有本地 HTTP 身份/同源边界，未知或重复 URL 参数拒绝。解析 JSON 时拒绝重复 key、非标准常量、错误层级和额外字段；任何输入不能流入 eval/exec/模板执行。

预检顺序：URL/规则字节与结构预算 → snapshot 语法/数量/重复、D/N、阈值 → 每来源 `query_row_count` 和总预算 → 每来源一次 `_research_query`（含原件核验）→ 身份/周期校验和共享数值计算 → 条件。规则无效时零 Store 计数/加载；行数超限时零 `_research_query`/指标运算，禁止“先试算再拒绝”。

| 级别 | 稳定错误码及处理 |
|---|---|
| 新规则结构/字段 | `invalid_filter_rule`、`unsupported_filter_field`、`invalid_filter_operator`、`duplicate_filter_field`、`duplicate_filter_group`；整请求 400，不回退空规则 |
| 阈值 | `invalid_filter_threshold`；整请求 400，沿用现有 `{error: code}` 安全码响应，不回显原始长输入，不新增字段路径错误框架。规则版本由 v1 方法固定，不接受用户传入另一版本 |
| 规则预算 | `filter_rule_limit`；整请求 400，未计数/加载行情 |
| 既有参数/成员/预算 | 沿用既有 `invalid_request`、`invalid_snapshot_id`、`invalid_research_date`、`invalid_lookback`、`research_member_limit`、`duplicate_snapshot`、`research_row_limit` 等明确映射 |
| 既有身份/周期/前缀 | `unsupported_period`、`research_identity_unavailable`、`research_identity_conflict`、`research_market_unknown`、`research_market_mismatch`、`research_duplicate_symbol`、`research_cutoff_mismatch`；整请求拒绝，不能为了算剩余成员而删证券。纯函数 ordinal 窗口返回 `ordinal_window_not_supported`；HTTP 未开放该参数，直接 `invalid_request` |
| Store 不存在/原件不符等 | 保持现行 Store 错误与状态语义；整请求失败，不缓存旧值或将读取失败伪装为普通 false |
| 未列程序异常/事实内部不一致 | 失败整请求并保留受控诊断，不作 `except Exception: unknown`；禁止已部分处理的成员响应冒充完整成功 |

接口最终 safe-error 集合在实现评审时逐码核对现有 Store/HTTP 映射，不擅自改变旧错误状态。纯函数接收结构化 rule；HTTP 对长字符串/JSON 的防护不能只靠纯函数实现。

### 7.2 逐成员/逐事实未知

继承已存在的 `cutoff_missing`、`history_insufficient`、`duplicate_date`、`unlocated_label`、`missing_ohlc`、`invalid_price`、`invalid_ohlc`、`known_negative_source`、`source_identity_conflict`、`source_adjustment_conflict`、`source_adjustment_check_failed`、`numerical_failure`。本片增加 `date_set_integrity_unknown`。旧 universe 单一 reason 原样保留；辅助证据汇总窗口中每个坏日期槽已有的 primary reason，加上字段数值失败和日期 gate 原因，不只挑全窗第一项。对同槽被归一化早返回掩盖的其它失败不作穷尽承诺；通过源 query/ordinal/date 回查原始行/batch checks。缺截止时窗口为空只表示没有此次窗口，不宣称来源无异常。未知 adjustment/known_at 属资格限制，单列，不与这些计算失败混为一类。

可用于计算的 fact 有值却同时带计算失败 reason、无值且无 reason、非有限 float、精确值与显示估计严重不符均是内部合同错误；由测试/受控失败暴露，不能静默择一。共同门槛失败时，原子可以引用仍有值的底层诊断 fact 并附门槛原因，但必须标为不可用于判定，不能与上述计算失败混淆。输入记录虽可定位但有明确坏价，保持 bad slot，不转换成未记录日期。

### 7.3 冻结的预算

- 成员 2–50；每系列选择前缀含未定位行 ≤20,000，总计 ≤200,000；N≤252。与现有研究同预算，不扩大“全市场”范围。
- URL 参数解码后、JSON 解码前 `rule` 的 UTF-8 长度 ≤2,048 字节；组≤2、每组原子≤3、层级固定、总出现≤6；阈值≤22字符。重复字段/组须先检测，不能先消重再逃避预算。
- 每请求至多 M 次计数、M 次紧凑来源读取/原件核验、M 次 daily_bars 归一化；同窗口统计至多一次/成员。计数是既有预检，不把它伪称零额外 SQL。
- 条件评价 ≤6M 次，组合≤2M 次；响应条件部分 O(MK)，K≤6。禁止复制每个条件的 N+1 价格数组、每个成员完整前缀或任意 metadata 原文。
- 日期归一化沿用现有排序，按 `sum(T_i log T_i)` 上界报告；当 Store 输入已排好仍不虚称纯 O(T)。新增条件层为 O(MK)，可复用事实/证据的最大额外窗口处理 O(MN)，不增加 O(KT) 扫描。

不为这片建通用规则树、插件注册器、持久缓存、异步队列或多个新数据库表。保持单一写者和现有 owner 线程；这是只读计算，取消不产生一半保存的研究对象。

## 8. 最小实现边界与优雅性要求

实现候选是一个小型 `stock_filters.py` 纯模块（仅白名单规则校验/规范化、原子比较、三值组合、解释计数），以及现有集合计算极小内部辅助输出：

1. 从现有 universe 单次循环提取私有 evaluator，返回原 report 加内部 facts/窗口证据；`universe_report` 仍只返回原 report。复用当前已算 momentum Fraction、drawdown Fraction 和 volatility，别从公开 float 重建精确值。
2. 在同一次归一化/窗口遍历中收集每个坏槽已有的 primary reason 和回撤峰谷见证；不复制 `_bar` 去重做同槽全错误收集，不为每原子重新 `daily_bars` 或扫描查询。日期 gate 和字段数值失败独立保留；原始 checks 通过源引用回查。辅助信息只在新流程需要时构造；不往旧公开响应添加字段。
3. 新入口一次 `_load`，一次共享 evaluator，再纯筛选；以同一产物同时返回基线 universe 与条件结果。不得先请求 universe 再请求 filter 引发两套来源读取。前端改阈值可以发新研究请求，仍执行既定原件核验，首片不承诺跨请求零扫描。
4. 不修改 daily_screen/采集 run 格式，不把 native cache 和导入版来源强行统一；不依赖 030 的端点/行业/同行模型。无需移动其它算法到“通用因子引擎”。
5. 重构任何共享循环前先锁定旧公开输出与 analysis_id golden；现有源码/test 回归不能靠刷新全部快照消掉。测试新规则的独立参考不调用该 evaluator 或其条件辅助函数。

若辅助证据提取导致大规模改动 normalizer/Store，缩小本片并重新评审；不以筛选名义扩大为通用来源重写。本段仅定义未来实现选择，本次没有修改代码。

## 9. 简单基线、手算与反例矩阵

### 9.1 判断任务与基线

共同输入、截止、来源门槛、N 均冻结，先比复核任务，不比挑出的收益：

- B0：现有三项表和动量降序，用户手工找满足同一规则者。保留全部成员和未知；记录全部答案与复核时间。
- B1：只 `momentum >= 0`。它含零动量，不能与现有 `positive` 的严格 >0 混名；排序与筛选分别展示。
- B2：B1 加一个固定 `max_drawdown >= -0.10` 条件；只改变这一项，列出新增排除/未知成员及证据。再增加 V 的实验需另登记，不合并为一次“最优方案”。
- B3：使用 §3 两组示例，专测合法 OR 支路、未知及回撤负号的解释。参数为合成/操作试验配置，不能据真实回顾表现重新挑阈值。

入选数更少不构成改善。暂不接 event_study 标签、不增加历史批量扫描/回测路由；历史结果联动作为后续单独研究。今后若研究后续价格变化，必须另冻结 horizon、成熟规则、对照分母和全部尝试，当前两年 30 股不直接授予未见测试段资格。

### 9.2 独立可手算正例

1. N=2，close=[100,120,90]：M=−1/10、DD=−1/4，`V=abs(ln(1.2)−ln(0.75))/sqrt(2)≈0.332342753421947`。M≥−0.10、DD≥−0.25 都 T；V≤0.30 为 F。不能把当前与全窗最高差恰好相同的一例作为全部 MDD 证据。
2. N=5，close=[10,20,15,12,18,15]：M=1/2、DD=−2/5、V≈0.440956275158823；当前相对峰值只有 −1/4，必须仍返回 DD=−2/5。DD≥−0.30 为 F。
3. 全常数正 close：M=0、V=0、DD=0，有效零值；三个零阈值都 T。缺值不能复用该分支。
4. 精确边界：M 分别为 `10499999999999999999/10000000000000000000−1` 和 `10500000000000000001/10000000000000000000−1`，float 都显示 0.05，但与合法阈值 0.05 比较依次 F/T。DD 用峰值 `10000000000000000000`、谷值分别 `8999999999999999999`/`9000000000000000001`，float 都显示 −0.1，与 −0.1 比较依次 F/T。原值都在现有数值域；低 Decimal 全局精度不得改变结果。
5. V 直接估计比较单测用能精确表示的二进制值（如 0.5）与其左右 `nextafter`，精确十进制阈值 0.5：小于/等于 T，大于 F；不能给每个来源波动构造未声明的舍入容差。

上述数值最初作为编码前公式核对例子冻结；实现后的独立测试、真实来源和资源证据见[实现验收](../qualification/stock-filters.md)，不能把书写例子本身当作产品通过。

### 9.3 必须先写的负例与不变量

| 编号 | 输入/扰动 | 必须断言 |
|---|---|---|
| F01 | 两输入真值的 9 种组合，及 1–6 原子的全部 3^K 赋值 | 与独立真值参考逐组/总体一致，全部原子都有记录 |
| F02 | T OR U、F AND U，U 分别为数值失败和源日期门槛 | 前者合法支路可入选但 partial 常驻；后者可确定为 F 但未知不丢；共同门槛不被 OR 绕过 |
| F03 | T 支路后面放数值失败、F 原子后面放未知；互换顺序 | facts/原因/分母全同；监测全部启用原子已评价，无短路漏算 |
| F04 | D 缺失但前一日存在、只有 N 个槽、重复 D、坏窗口中间槽 | unknown 保留在 M 分母，原窗口不补齐、不回退 |
| F05 | 无日期行、错误 label 但有可读 source_date、全批未定位行 | 门槛与原因保持，不能由 token 恢复定位后删除不确定性 |
| F06 | 仅 M/DD 规则而 V 数值失败；与加入 V 后的 AND/OR 对照 | 仅启用依赖影响 evidence_complete；标准三值逻辑，非全行抹空 |
| F07 | OHLC 有效性错误、source_code/adjustflag 冲突、隔离批 | 具体失败在所有相关原子可追踪；不同坏槽/数值字段的失败同时存在不只留首项，同一槽原始检查仍可回查 |
| F08 | bool N、null、空组、未知 key、重复 JSON key/URL参数、嵌套组、7 原子、3 组、超长数、NaN/科学计数 | 预检拒绝且零来源加载；额外代码字符串只作非法输入，不执行 |
| F09 | 相同符号不同 snapshot、同 snapshot 重复、混市场/周期、身份不明 | 整请求对应错误；不删一股后给成功分母 |
| F10 | 单成员20,001行或总200,001行，含 NULL label | 在 `_research_query`/计算之前拒绝；不静默取最后 N+1 |
| F11 | 成员/原子/组顺序反转、阈值尾零/负零规范化、重复请求/重开 | 规范结果与身份相同；语义阈值/版本变化产生新身份 |
| F12 | 已知未来追加/坏价修改；另加不可定位日期 | 前者同前缀条件不变、版本身份合理变更；后者门槛变化按证据解释 |
| F13 | 窗口首日不同、已知缺日停复牌、同 N 不同日历跨度 | 实际端点原样保留，不称同步20交易日；不填日历 |
| F14 | 全部 U、全部 F、重复成立组、两组部分交叠 | 三类分母守恒，无空集合除零；OR 入选只计一次 |
| F15 | 同输出显示值但精确阈值两侧、MDD负号、V极端浮点/非有限 | 独立 Fraction/float 参考一致；未知和近似标识不丢 |
| F16 | 缺 metadata 与 legacy markers、仅 requested_adjustment=none；applicability 缺失/null/unverified | 源资格仍未知/原标记，BaoStock known/CNY 保留 applicability=unverified；三种存在性绑定不同摘要身份，任何 T 都不升级已复权/PIT/运输认证 |
| F17 | 先旧规则慢请求，后新规则快请求；修改截止、移除成员、取消再重试 | 旧结果不覆盖新选择；UI显示身份、条件、分母与当前请求一致 |
| F18 | 任意阈值筛选前后，对来源原件/Store查询/旧 universe 做对账 | 完整查询/源哈希不变；旧响应和 analysis_id 不变 |

独立数值参考从完整公开查询的源字符串直接用 Decimal/Fraction 构造，日期组选择另写简单参考；波动用 60 位 Decimal 的 ln 和手算平方和，容差预先为 `abs=2e-11, rel=2e-10`，与当前真实报告的主参考尺度一致。该容差只验数值估计；条件真值使用 §3.2 的表示值严格比较，二者不能混用。

## 10. 验收门槛与性能指标

### 10.1 计算、工程和来源验收分开

1. **逻辑与账目**：F01 全枚举以及全部错误/边界用例通过；逐成员/原子/组真值、原因和全部守恒等式 100% 与独立参考一致。任何遗漏成员、未知变零、无证据入选为阻断项。
2. **兼容**：旧 universe 的纯函数/API 身份及数值 golden 不变；现有 daily_screen 行为不变；全 Python 回归。产品未修改时不拿过去通过数作新增功能通过。
3. **实际来源**：对 §4.3 固定离线矩阵，用预先冻结 B1/B2/B3 规则逐股独立对账，再验证重开/排列/规则变化。原 48 个窗口检查继续作为数值对照，不偷换为 48 个新独立预测样本。若 private 数据未提供，明确未跑。
4. **界面**：前端测试、类型检查、构建与真实同源浏览器分别记录；展示入选/排除/待核查、partial 告警、来源实际端点和负号；F17 及窄屏访问通过。接口/纯函数可先交付，UI未验不阻其研究，但不宣布完整界面完成。
5. **跨平台**：Windows 原生不在本次证据内；通用测试在真实平台跑后才给对应资格，不能伪造平台或跳过失败。

### 10.2 预先冻结性能试验

合成固定种子、相同硬件/Python/依赖版本，分别 10×5,000、10×20,000、50×4,000 行；N=20 和 252；含有效、末日缺失、重复及未定位病例。最后两组名义总行数为 200,000，缺截止病例的实际计数另记。按实现反方同意的本轮观察方案，先每路预热一次，再交错运行基线/新请求各 **5 次成对观察**，报告样本数、中位、范围、RSS 和 tracemalloc 辅助峰值及响应字节数。记录冷热与原件核验边界，不混为纯算法速度；**不声称已完成原拟 30 次的稳定 p95 验收**。更大重复数的尾延迟测量后置，不借缩减次数宣称门槛更宽。

- 硬门槛：每次 M 次计数、M 次紧凑加载和原件核验；不得随原子数从 1 到 6 成倍增加；归一化每股一次。新流程把原 universe 和筛选一并返回，不能暗中算两遍基线。
- 新规则评价/解释单独计时：50成员、6原子观察最大值 ≤20ms，另列中位/范围；这是本轮小样本观察门槛，不能替代稳定 p95。
- 与同数据 universe 请求相比，观察中位与每一成对耗时均检查新请求 ≤`1.15 × baseline + 20ms`；增量峰值 RSS ≤16MiB。报告未通过的个别对和总体范围；未达标先找重复读取/对象复制，不能取消原件核验换通过。RSS测量方法及局限明确记录，不能把父进程继承的历史高水位误作本次请求峰值。
- 新增条件/来源摘要相对原响应 ≤256KiB；整个响应≤512KiB。超出说明证据投影不够有界，先修设计/实现再验，不运行时无声删原因。固定三种规模中，条件输出大小只能随 M/K 增长，不能随历史 T 增长。
- 20,001/200,001 行拒绝用调用探针验证“零加载零公式”；不能仅测拒绝耗时快就宣称预检正确。

若机器共享负载造成预算未达，记录环境与完整结果，换空闲同机重跑一整组；不挑单次最快值、不事后放宽指标。性能通过仍不证明超越 TradingView，双方输入与规模不同。

### 10.3 用户价值的保留/停止条件

先用合成及授权冻结样本做 8 个配对复核任务，覆盖 OR、缺截止、日期未知、临界值、不同起点、回撤负号、数值失败与全部未知；B0 与新界面交错次序。预先答案由独立参考给出，记录操作次序和学习效应。

门槛：所有入选/排除判断和原因关键项正确；把 unknown 误读为确定失败/成功、把来源步读成交易日或把 source-price 当收益的重大误读为零；相对 B0 中位复核时间至少减少 20%，且最慢任务不因找不到失败解释显著恶化。8 个任务仅作个人工作流试点，不给普遍统计显著性结论。若无明确省时/少错价值，优先保留简单排序和单组条件，停止更复杂 OR/UI 扩展；不得以收益曲线更好替代任务价值验收。

## 11. 编码前反方检查清单与本轮状态

独立反方至少确认：

1. 现有 daily_screen/universe 的重叠是否已充分排除，新增三字段/两支路是否真有使用问题。
2. §5.2 的 OR 合法支路与 partial_evidence 是否能清晰表达，何种失败应只影响某字段，何种共同失败必须阻断；不得把标准逻辑与资格政策混写。
3. 精确 M/DD 的共享提取是否无需第二轮读库/归一化；V 的估计阈值边界是否可接受，是否需要另行冻结安全带政策。
4. 源日期定位门槛与现有 universe 条件性输出差异是否足够明显；当前未知调整/可得性有没有被筛选结果掩盖。
5. 所有字段、参数、错误、身份、计数与性能边界是否能独立实现/验证；是否还有省略来源、短路漏错或未限定参数。
6. 只有纯计算/只读 API 通过时，声明是否准确；UI、Windows、真实源、用户任务和预测效果是否分别留有状态。

下一阶段顺序：独立反方逐项意见 → 本文修订与决定记录 → 先异常/独立参考测试 → 最小纯函数和只读 API → 全回归/性能/离线真实矩阵 → 按任务价值决定集合页接入。单独 implementation plan 只在审查通过后建立，避免两份未定规则互相漂移。

编码前研究阶段完成：已有功能与真实报告核读、上述官方正文核查、公式/有界格式/三值逻辑/来源资格/身份/预算/验收合同，当时只新增本文。之后按独立批准实施最小纯函数/只读 API，最终实现证据集中见[实现验收](../qualification/stock-filters.md)；未重新抓取行情。UI 接入的实际证据见[独立界面资格](../qualification/research-filter-ui.md)，本文不代其授予界面、用户效率或预测效果资格。

### 11.1 首轮独立反方逐项答复（2026-10-11）

依据 [独立审查](../reviews/2026-10-11-explainable-filters-review.md)，原 reviewer 已复核批准最小纯函数/只读 API，逐项决定如下：

- **R1 采纳。** §4.2 补齐六个语义字段的 applicability 和 source_semantics.scope，保留 absent/null/原值并绑定 source_metadata_id；F16 加入 BaoStock documented meaning 及三种存在性反例。未扩大语义字段范围。
- **R2 采纳建议的最小定义。** §5.2 source_gate 仅等于共享 coverage_known 的日期定位门槛。坏价/隔离/短历史/冲突等仍由原事实 reason 产生 U；不建多资格引擎。三值归约显式判断枚举，禁止把非空字符串当真。
- **R3 采纳收窄承诺。** §5.3、§7.2、§8 对齐为“每个坏槽已有 primary reason + 日期 gate + 字段数值失败”，同槽底层缺陷仅给原查询追溯，不复制 normalizer、不二次验证或扫描。缺截止空窗口不代表无来源异常。
- 其它意见采纳：§9.2 改为能跨合法 18 位内阈值的四个精确反例；未使用的版本错误码已移除。规范 market 只是既有交易所映射，不认证资产品类/币种/永久证券身份，新结果继续显示 source_claim/declared。本片不建设证券主数据。
- **实现阶段复核修订。** 空窗口实际端点改为 null，旧 universe 的 end_date=D 不变。独立反方批准 §5.3/§6 的固定条件目录、局部短引用、完整来源合同投影共享和定长见证行；没有删除条件、源标记或原因。50成员/5种实际解码合同（含腾讯 legacy）在重坏槽及原价极值病例分别产生 297,975/241,646 字节，较完整旧 envelope 增量 252,964/197,804 字节；这是指定合成字节案例通过，不替代全面性能或真实源资格。30 次 p95 方案调整为上述 5 对观察，尾延迟资格保持未完成。
