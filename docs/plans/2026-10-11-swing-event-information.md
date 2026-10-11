# 035 最小实施计划：既有突破与滞后路径的一次连接

2026-10-11。**第1～10节保留编码前设计记录；后续批准与实施证据见第11～12节。** 依据[研究035](../research/035-swing-event-information.md)与[独立审查SE-01～06](../reviews/2026-10-11-swing-event-review.md)。只允许下面这个专用纯函数和离线验收；033/034已发布，保持不变。本文不是采集、前向监控、API/UI或交易策略的启动许可。

## 1. 唯一实验身份与主总体

| 项目 | 首轮冻结值 |
|---|---|
| 协议 | `035-er-half-lag1-v1`；正式执行manifest绑定研究、计划、复审、源码和依赖实际hash |
| 原事件 | close严格高于此前20来源组high；沿完整前缀全部B贪心选择，下一i必须>上次i+5 |
| 背景 | i−1结束的10次close变化；D为净变化>0，E为已有ER≥1/2；Fraction精确，唯一增加条件E |
| 标签 | 后5来源组末close相对事件close的原始变化；完整路径资格沿旧定义；精确符号≤0称未上涨 |
| 报告总范围 | signal_date闭区间2024-10-11～2026-10-09 |
| 唯一主范围 | `primary_period=internal_2026`：signal_date闭区间2026-01-01～2026-10-09 |
| 全局cut / cutoff | 2026-01-01 / 2026-10-09；训练终点>=cut即purge，旧优先级不改 |
| 主支持集 | 主范围、来源获准且连接成功、A1中E两组都有共同可评价事件的固定清单股票；M/30和成员清单同报 |
| 唯一停止值 | 每股Δ_s由整数计数形成Fraction；Δ_main为主支持集的Fraction等权均值，按精确符号判断 |
| 诊断范围 | 前段2024-10-11～2025-12-31、全目标段、覆盖到的9个自然季度；季度按signal_date，同一全局cut，首末不完整 |
| 固定禁止 | 不改20/5/10、1/2、lag1、股票、标签、权重、去重或主范围；不选择最有利诊断期 |

主范围已经用于其他研究，是旧源内部描述时段，不能叫未见/OOS。全段诊断仍保留全局cut造成的purge；季度不重新purge、不重新去重，标签终点允许跨季度但不越cutoff。每期支持成员变化单列，另列同支持集合也不产生第二主指标。

## 2. 产品变更上限

编码获准后可新增 `src/anatrading/swing_event_information.py`，专用入口候选：

```text
swing_event_report(query, *, report_start, test_start, cutoff)
```

这三个显式日期用于身份和合成边界验收；真实首轮只能取§1固定值。严格ISO日，`report_start < test_start <= cutoff`，query.selection.cutoff须等于cutoff，ordinal裁剪拒绝。20/5/10/1/2/lag1不成为可调输入。不同日期参数构成不同研究身份，不能改原manifest后继续沿用旧试验名。

编码前接口补充（2026-10-11，独立审查者同意的有界澄清）：报告日期最多横跨9个自然季度，超出以`invalid_swing_dates`拒绝，不能截掉空季度；真实冻结范围仍为原9季度。完整响应字段在仓库外test-first `response-contract.txt`冻结，随输入/oracle/golden/source hash登记；不增加公开HTTP/API。

入口只接受可信Store的完整公开query或 `_research_query` 同身份OHLC投影，及同合同的合成夹具；不开放裸bars。保留snapshot/batch/query/raw/contract身份引用，复用已有最小校验；原件哈希在既有Store读取处核验，**纯函数不重复核验/重算raw或query哈希，不复制通用schema/来源认证层**。仅检查安全取值所需最小形状与结果身份字段、预算、strict日期/cutoff一致、无ordinal裁剪、retrospective模式、1d及symbol_identity；source_rejection/coverage沿旧helper。只使用既有 `strict_date`、`daily_bars`、`daily_coverage`、`source_rejection`、`symbol_identity`、`_identity`、`event_report`及其描述分布helper；`_identity`只生成新的分析身份，不提取或改造共享query框架，不依赖034的validator/collector。

所有源行（含unlocated）≤20,000，超限在normalization/event公式前拒绝。来源中的坏价格/超DECIMAL域值遵循既有组无效规则，不向新函数扩展数值支持域。日期缺口不补，旧identity及公开输出不改。

只新增必要测试、合成fixture及本片资格文档；修改旧event、ER、signal、Store、HTTP/UI、锁文件或依赖均超范围，须停下复审。30股汇总由仓库外固定离线验收脚本从单股结果完成，不新增通用集合引擎、数据库表或服务入口。

## 3. 一次连接的确定路径

1. 验证输入/预算，`daily_bars(query)`一次，`daily_coverage(query,bars)`一次。先记录来源资格，允许未知复权/日历/closed/known_at继续作为源版本限制；只有既有source rejection或无法定位覆盖问题关闭新比较。
2. 对结构合格query恰好调用 `event_report(bars,20,5,test_start,cutoff)`一次，**包含新比较因coverage关闭的来源**。旧返回的signals、rows、counts、partitions在此时已固定；不能先按背景/新资格过滤bars。旧入口整体失败则旧和后续计数null、事件null，记录 `legacy_event_failure`；没有部分旧成功的完整结果。
3. 按旧rows的index核对日期/ordinal/start_close和bars位置。获准来源的每个B，直接取 `[i-11..i-1]`11槽，作固定10次Fraction价差；精确N、L、ER、D、E写到该B的一条见证。`L=0`沿ER=0，D/E都false；一般E仍无方向。**不调用efficiency_report逐事件重分组全部context**。
4. 精确sign由原Decimal端点比较，核对旧合法float label的符号。按旧label/evaluation状态及新来源资格产生§4交叉表。正常支持域内意外索引/条件缺失/符号矛盾/非有限均为 `connection_invariant_failure`：整证券新比较关闭，保留完整旧事件投影和旧计数，N/L/D/E新输出整批置为未执行/失败，不能只移除出错事件。
5. 从同一B账本按signal_date产生A0、A1、E=true/A2、E=false、前段/全段/季度统计。不重新检测B、不重做贪心选择，不复制3份行情。主全日期baseline直接引用旧`partitions.test.baseline`，其日期恰好等于唯一主范围；诊断时期**不提供另造的全日期baseline**。旧全前缀基线如保留，必须写其真实起止，不能移花接木。
6. 释放bars、旧signals及不需要的完整旧对象。返回固定字段的事件见证和摘要；不返回每条的完整11行OHLC/完整query，只留背景首末日期/ordinal/index和共享源身份，足够定位复核。

原件读取在调用者既有Store边界进行，每证券一次 `_research_query`、一次原件核验，紧凑投影不改变公共query_id。函数纯计算，无I/O。离线30股按固定顺序逐证券读取、算、写私有结果并释放上下文，再读下一证券；不同时持有30份全query。

复杂度：新增连接O(10×B)，见证O(B)，固定时期分组/分布排序成本另计；旧normalization排序、event_report分布排序和持有输入均保留，整个流程不宣称纯O(T)或O(1)内存。B≤T≤20,000，每条字段/窗口定位数固定，不复制全前缀。无缓存、线程、队列、策略DSL或泛化插件。

## 4. 两个旧状态与新资格：固定输出分层

### 4.1 状态优先级

| 条件 | 旧label_status | 旧evaluation_status | 新比较 |
|---|---|---|---|
| i+5不存在，已存在未来槽可含坏组 | immature | selected时immature；否则overlap_excluded | 不进入共同集 |
| i+5存在，路径坏 | invalid | selected训练信号且label_end>=cut时purged；其余invalid/overlap_excluded | 不进入共同集 |
| 路径合格，末价可算 | valid | selected且未purge时valid；否则purged/overlap_excluded | 来源/连接合格时才comparable |
| 新coverage关闭，但旧有valid | 旧值 | 旧值 | source_unavailable，原valid数进入全局排除列 |
| 任一新连接不变量失败 | 旧值 | 旧值 | 整证券internal_failure，原valid数全进内部失败列 |
| 旧入口整体异常 | null | null | legacy_event_failure；依赖旧计算的计数均null |

source rejection使旧normalization按原规则标坏，可能得到确实0个B；这是已执行的旧0。新来源关闭后的分组统计/计算次数仍为null。规则不可计算、未执行和真正计数0不可混同。

输出保留旧label_status/label_reason及evaluation_status，不用一个字段覆盖另一个。新来源/连接状态用单独字段表示，理由列表含已知来源限制；无需建立可注册状态框架或逐模型数值降级系统。

### 4.2 固定守恒与支持集

旧入口成功的证券按每个signal_date范围输出旧状态及资格归类。资格可以是已知0，未执行D/E统计仍须null，分解适用范围分开：

```text
raw_B = overlap_excluded + selected_B
selected_B = old_valid + old_immature + old_invalid + old_purged
old_valid = comparable + source_unavailable_valid + internal_failure_valid
selected_B = condition_computed + condition_source_unavailable + condition_internal_failure
下面仅对admitted且连接成功的证券成立：
condition_computed = D_true + D_false
D_true = E_true + E_false
comparable_D_true = E_true_pos + E_true_zero + E_true_neg
                  + E_false_pos + E_false_zero + E_false_neg
```

旧evaluation五状态×新资格三类（admitted/source_unavailable/internal_failure）表完整保留；另列旧label三状态×旧evaluation五状态，识别invalid被purge、valid被overlap等组合。旧入口失败时这些表为null并给原因，不填零表。它们是交叉层，不能跨层相加。

明确关闭例：来源coverage关闭，旧selected=3（valid=2、immature=1）。

| 可知资格/旧状态 | 值 | 未执行计算 | 值 |
|---|---:|---|---|
| comparable / source_unavailable_valid / internal_failure_valid | 0 / 2 / 0 | D_true / D_false | null / null |
| condition_computed / condition_source_unavailable / condition_internal_failure | 0 / 3 / 0 | E_true / E_false及两组符号/分布 | 全部null |
| 旧valid、immature在source_unavailable列 | 2、1 | Δ_s | null |

前三项旧状态/资格恒等式仍成立；后续D/E分解不适用。`condition_computed=0`表示已知没有获准计算的条件，不能把D_true/D_false改成0来凑式子。

主比较共同集为来源获准、连接成功、旧evaluation_status=valid、D=true的事件，E两组都用这一资格。单股任一E组为空时Δ_s=null；不存在额外“float下溢剔除集”。主M只取在唯一主时期两组都有支持者，30股全清单保留未支持/关闭原因。跨30股若有输入或计算失败，整体记录partial/failed及成员，不把其余结果说成完整30股通过；已算数值可以保留为有明确支持集合的描述。

必须给条件保留率及遗漏代价：在共同集上`count_A2/count_A1`、E两组各自正/零/负和R分布、`positive_E_false`与`positive_E_false/positive_A1`；零分母null。全部原selected上的条件保留数另列，未知标签的遗漏正例数不可推定为0。

### 4.3 输出与身份

单股结果的固定header绑定method/protocol版本、三日期及20/5/10/1/2/lag1、snapshot/query、raw/contract、证券声明和source资格；analysis_id使用现有规范identity。执行manifest另绑定实际research/plan/review/code hash，避免将可变文件路径或执行时间当数学身份。真实清单的成员顺序/组别、source hash及完整结果hash在离线总报告绑定。

每个B一条见证：旧date/ordinal/index/selected/两状态/标签端点与估计；此前高点和事件close；背景首末定位及精确N/L/ER（整数分子分母）；D/E；精确label sign；新资格与原因。N/L可用有符号有理数表示；float展示不影响条件。共享源/参数只放header一次，不在每行重复元数据。未选、purged、invalid、immature也保留，私有结果不裁到UI最近100行。

## 5. 数值合同：支持域证明替代额外框架

合法源价 `10^-18 <= C < 10^20`，两不同源价差≥`10^-18`。既有标签是**精确Fraction比值减1后转float**，非零绝对R在`(10^-38,10^38)`；20,000项绝对和<`2×10^42`。所以合法域不需给每个事件新增underflow/overflow资格，也不复用034的log碰撞后缀状态机。

N/L用Fraction；ER=abs(N)/L或显式零路径约定。E精确比较`2*abs(N)>=L`且L>0。D单独看N>0。原标签sign精确比较Decimal端点；合法float sign必须相同，矛盾为整证券内部失败。负R可能舍入到−1但端点仍正，保留estimate说明。超域/零/负源价按原normalization无效组处理。

比例与主真值：`p_s,g=Fraction(zero+negative,count)`，`Δ_s=p_s,true−p_s,false`，`Δ_main=sum(Δ_s)/M`；输出最简分子/分母及可选float展示。每组空时null；M=0时null。停止判断只使用Fraction与0比较，不能用显示百分比、epsilon、float均值或挑一个误差尺度。R均值/type-7分位继续复用既有描述helper，明确float64估计。

**独立oracle的普通数学域容差在产品编辑前固定如下：** 合成≤200源槽，正价格在[1,1000]，均值/分位先独立按有理数算；设n为该统计有效标签数、M为其float标签最大绝对值，允许绝对误差 `16 × 2^-52 × max(1,n) × M`。M=0须精确0，空集须null；此界仅为预定验收容差，不是全域误差定理。每条R直接与独立精确比值转float逐值比较，旧公开输出/golden逐字段精确一致；合法极端价、−1舍入边界另用直接表示值检查，不套普通域容差。所有B/selected/D/E、符号、日期、计数、Fraction比率及Δ/停止真值始终exact，不用容差吞掉翻转。若容差用例不通过，先记录失败并审查原因，不根据实际输出改松容差。

## 6. 先有小型独立证据，再写一次连接

### 6.1 改产品前冻结

在正式批准后、第一次新产品文件编辑前，保存当前旧 `event_report` 和必要旧公开 `signal_report`/API完整输出golden及输入/源码hash。用仓库内独立小型合成fixture，不修改034 fixture或旧预期；测试版本生成后不自动刷新golden。至少覆盖：

- 平坦/单向/折返与ER=1/2边界
- 连续突破20/23/26及按条件错误重去重的反例
- 细微合法价差、极端合法正端点和R舍入−1
- 坏路径但h不足；坏标签且跨cut；未选事件的有效/无效/跨cut组合
- 旧valid但有unlocated导致新全局关闭；来源冲突/隔离；重复/坏OHLC

独立oracle只用标准库Decimal/Fraction和直接窗口，输入来自原合成字符串；不得调用产品normalization、ER、event、去重或统计helper。价格资格以分母整除10^18和范围检查独立核对；检测B用朴素此前20组max，选S用直接循环；标签、窗口、两旧状态、新资格及精确计数差值分别算。样本规模≤200源槽足够，不建第二套通用事件引擎。期望表/每个字段生成方式留hash与说明。

小型新测试先执行，应因新入口缺失而失败；同时旧golden生成/重放通过。报告真实通过、预期失败及跳过，留完整日志；不得先实现再声称test-first。未来测试文件可新增 `tests/test_swing_event_information.py` 及必要的独立反方测试；旧tests不修改。

### 6.2 新实现必须通过

1. 全部旧golden、旧query/export/analysis_id和已有相关测试不变；新函数不改变输入对象、旧报告对象或Store。
2. 独立oracle逐字段对齐B、selected、背景11槽、D/E、原符号、新资格、所有范围计数及Fraction主真值；源极值/低Decimal context仍正确。
3. 当前合法事件价格更改且保持突破，背景不变；追加/改未来合法数据不改变先前B/selected/背景。标签成熟/失效与来源版本资格变化分开验证。
4. `i+4/i+5`成熟边界、label_end=cut的purge、跨季度不再purge、报告起点以前的B仍影响选S。日期缺口不填，源步与自然日跨度都可查。
5. 覆盖关闭后旧valid仍在source_unavailable列；注入旧入口错误→未执行null；注入新join/sign错误→整证券内部失败而非局部剔除。所有状态交叉表守恒。
6. 零事件、D全false、E单组、全零标签、主M=0、主正/负/精确零、显示约为零但Fraction非零；遗漏正例零分母null。
7. 调用spy：每合格query normalization/coverage/event各一次；每B最多10次价差；不调signal/Kalman/forecast/efficiency_report；20,001行在这些公式前拒绝。30股外层逐证券读完释放，不重跑每个历史截止。
8. 既有解码→临时Store→公开query/私有OHLC投影→新函数结果一致；旧公开查询与导出字节/hash不变。该项仍为合成Store验收，不能冒充真实源。

独立实现审查及受影响回归通过后，才进入§7真实一次运行。最终代码变化后重跑受影响与全仓既有命令；Node/build可以证明旧前端回归，不等于新UI/浏览器，因本片没有UI。

## 7. 预先固定真实输入矩阵

只复用已授权的034原成员清单：`members.json` SHA-256 `fa4948d336e9bc66609e15b08f9522db85bfb2c374b9ef6af77aa2620e3fe6ec`。每股原件、snapshot、raw、contract绑定该清单，不重新选股票、不联网。原请求矩阵`ba90d60c17c49dc64850c9b8e88d56fa7bf28aff5089007ced484c8fc09d384b`仅作来源参照，不复用其中不同cutoff的query_id。

| 固定组 | 全部成员 | 本次请求 |
|---|---|---|
| 银行10 | 601398.SH、601939.SH、601288.SH、601988.SH、600036.SH、601166.SH、600000.SH、002142.SZ、600919.SH、601009.SH | 每股一次完整640源组，cutoff=2026-10-09 |
| 白酒10 | 600519.SH、000858.SZ、000568.SZ、600809.SH、002304.SZ、000596.SZ、000799.SZ、600702.SH、600779.SH、603589.SH | 同上 |
| 科创板混合业务10 | 688981.SH、688012.SH、688008.SH、688111.SH、688036.SH、688271.SH、688050.SH、688599.SH、688063.SH、688333.SH | 同上；不称同一行业 |

总共30个唯一请求、19,200源槽。28股源起点2024-02-19；688981.SH为2024-02-01，688012.SH为2024-01-29。报告目标两年前更早上下文必须保留参与B-only选择，不能按2024-10-11重新起步。上述内容只读既有身份/成员/覆盖清单，没有读取本轮真实OHLC、标签或ER结果。

每请求产生一个事件账本、唯一主范围、固定前段/全目标段与9季度诊断；不为这些范围重新读取或调用event_report。原15个缺来源日期及已知停牌范围从现有覆盖证据附注；5源步可能跨停牌，按实际首末日期报告。无事件、单组退化、未知及内部错误全部保存；不补数据、换股票或取最近较早日期替代缺失。

首次执行前形成035私有manifest，记录30条实际同cutoff query_id、原件/Store/源码/方案/复审hash，冻结输出位置和完整命令。独立只读原件逐槽核对来源身份及固定样本；原行情/逐事件源价/账本只写仓库外新目录，不覆盖034证据。主Δ、三组、全部成员和固定时期一次输出，无择优抽样。没有效果结果也可以完成程序/来源兼容验收。

## 8. 资源实验：可识别范围与停止

优先验收§6次数、预算、单条固定字段及逐证券释放。没有为本片设置“必须更快”或沿用034的8MiB增量门槛；不满足有界工作结构则阻断，不能通过减少见证或略去原件核验换绿。

代码冻结并协调CPU窗口后，资源脚本在仓库外先审后跑。固定5k/20k合成递增正价格（密集B的有界最大记录压力），同一日期/源形状/消费方式：A为输入校验+一次normalization/coverage/event+共同旧事件投影，B为新纯函数的完整连接；A不运行signal_report。A/B都保留各自完整结果并编码JSON，另记不含编码的函数边界。基线是独立脚本wrapper，不为测量给产品增加开关/另一路公开入口。

- 时延：锁定环境，输入生成排除在函数计时外；每路预热一次，AB/BA/AB/BA/AB五对，全部原始ns、中位、范围及结果字节保留。端到端另含实际临时Store读取/原件核验，清楚标边界。五对不声称稳定p95或性能优势。
- 函数阶段Python分配：四个独立进程A/B×5k/20k，imports和输入构造完成、统一gc后才启动tracemalloc；记录调用及JSON编码阶段current/peak，持有完整结果，A/B同消费。只解释Python被追踪分配，不叫RSS/native内存或完整进程增量；不追踪输入准备峰值来代表函数占用。
- RSS：同四进程记录启动/import/input/函数后VmRSS、VmHWM与ru_maxrss作进程观测。若最终高水位仍由输入阶段决定，写明函数增量不可识别；即使A/B总峰值差为0/负也不认证额外内存为0/负。tracemalloc和RSS不能互相冒名补证。
- 结构/结果：原件核验、query读取、normalization/event调用次数与20,001提前拒绝是独立硬验收；完整JSON大小、每条见证字段数、B≤T≤20,000及只保留必要结果可核。不隐藏输出随B增长。
- 停测：完成固定协议即记录事实；测量无法辨识、不稳定或计时器错误可判未验，保留原脚本/输出。任何修测方案先审，不改变输入/删慢对/重置高水位/反复运行到通过，不扩大产品来适配测量。

本次计划没有运行上述资源实验，033/034的原负结果和RSS未验均保持原样。

## 9. 负结果与完成条件

程序/来源层完成需全部受影响验收、独立复核和固定真实分母对账；经济结果不是实现通过的前提。效果表只使用§1唯一主时期的精确停止值，给三类结果：

1. `M=0`、整体条件退化或输入/连接失败使主计算无资格：退化/无法比较，保留缺失和原分母，不换参数。
2. 精确Δ_main≥0：固定样本方向不支持，停止以降低5步未上涨比例为由扩张035；不改h、阈值方向、样本或标签救结果。
3. 精确Δ_main<0：固定样本有描述性负差；必须同时报告M/30、不同信号日期、遗漏正例数量/比例、两E组幅度分布、三组和固定季度冲突。它不构成发现/概率/交易或自动升级许可。

主值与同支持合并权重、预定前段或季度方向相反时标不稳定；不能删除冲突期，允许结束。负差很小、支持集中、遗漏大量正例或现有人工查看已足够，也允许保留旧能力而停做；不现场发明最低样本/提升门槛挑赢家。不使用IID p值、置信区间、Sharpe或重采样引擎。

本轮结果无论正负，都不得自动开始前向采集、监控、API/UI或交易模拟；后续需独立价值决定和授权。前向SE-05还要求基线完整前缀起点/逐槽hash固定、版本仅追加；滚动截短、修订或补早史另版，该阻断不延误旧源描述。所有尝试/错误/取消/重跑保存；条件、时间或数据变化登记新试验，不能覆盖失败。

## 10. 本次交付与复审请求

已完成文档层：035逐项答复SE-01～06、本计划的输入/时间/数值/分母/单次连接/验证/真实矩阵/资源口径。未新增产品、tests、fixture或执行脚本，未跑真实效果或benchmark。等待原审查者复审SE-01～04，再由负责人决定是否正式批准上述test-first与实现范围；审查接受研究不自动启动编码。


## 11. 批准与实现检查点（2026-10-11 09:28 UTC）

负责人于09:12正式批准冻结计划内的test-first/golden与单股纯函数；SE-01～04已关闭，SE-05继续阻断前向扩展。批准时研究SHA `c9f2ffa0b786b8c147a15bcaab9686344e90bbe880041951919828b5b6e602db`，复审SHA `7078c734c48849855236ea4c58732a2df9a979d36b6dffdeba68a78e0a6ad2a8`。最多9季度的接口澄清已在产品出现前冻结，未改变真实主/诊断范围。

- 产品创建前：14例≤140行合成输入、独立Fraction oracle、旧event/signal完整goldens、源码与响应合同已冻结。fixture SHA `fbc53e3a052325e9c3a47fa71569718d17c70dc6e275b61d80cebd1bc9e83979`；新入口缺失的作者测试48项预期失败、旧golden14项通过，日志与product-absent证据保存。独立反方也先保存缺模块红灯。
- 一次连接：新增`src/anatrading/swing_event_information.py`，其余产品源码未改。使用可信query最小gate、一次normalization/coverage/event、每B固定10次Fraction价差、至多12个时期摘要，无公开服务或UI入口。
- 首轮作者61通过/1失败：失败来自独立oracle保留底层精确sign，但公共合同在来源关闭时要求新sign=null的接缝；只修测试映射，oracle/golden不改。后续追加预冻结普通域分布容差、身份与cutoff边界，作者83项通过。
- 反方首轮21项通过后发现失败回退的损坏index可能附到别日prior_high，修复为date/ordinal不匹配时null。原v1源码和首次日志保留；未改变事件、旧状态、条件或标签。反方补充断言是在修复后执行，记录为green，不宣称新增red。
- 修复后module SHA `ab8f3c38a65baf3fed85a2169fd16209ad757e5a093cf5568594243ecbf3a303`。独立受影响复核：作者83、反方21、旧相关62，共166通过、1项既有私有ER样本缺失skip。skip不计真实验收。
- 负责人批准先完成全仓回归与源码/fixture冻结；随后真实worker独占Store执行固定一次重放，资源负载排在真实之后，另开CPU窗口。实现审查通过不预判真实方向，也不授权按结果调参。

仓库外证据根为`/workspace/shared/anatrading-swing-event-information-2026-10-11/`（test-first、oracle、regression、performance）；独立审查证据根为`/workspace/shared/anatrading-swing-review-2026-10-11/`。原件和逐事件真实账本均不入库。资源脚本先经静态审查、A gate AST核对，任何真实/资源最终结果另记本片资格文档，未跑项目不算通过。


## 12. 执行完成及停止决定（运行后补记）

全部执行遵守第1～9节固定协议；使用第11节module及`implementation-freeze.json`（SHA `87126159a16066736af0d192226e22f861636ea1f78b5740a8f79e71568e57b2`），未换参数、阈值方向、数据、主时期或分母。完整层次/命令/hash与未验项见[资格记录](../qualification/swing-event-information.md)。

- 全仓2644通过、49既有skip；Node128、TypeScript/Vite构建通过。独立真实30股全部来源/连接成功，原件与旧证据未变；主Δ=86/315>0，M=14/30，按预设负结果规则停止扩张该条件。
- 14股主支持只保留22/81共同事件、漏26/30正例；全30口径22/108、漏34/38，完整分母及全部诊断期保留。2025Q3反号不会成为新主值。
- 负责人在真实Store关闭后批准资源固定一次窗口；5k/20k、五对、四内存进程完成且无重跑，结构/次数/预算上界通过。20k新/旧函数中位1.177/0.514秒，完整JSON14.91/6.71MB，新增完整事件见证的时延、分配和输出成本已如实记录；资源优势未取得。
- tracemalloc在输入后启动，获得Python分配观测；VmRSS/VmHWM和ru_maxrss只作进程观测，函数新增RSS仍未验。没有把零峰值差或Python分配伪称RSS通过，没有追跑修绿。

本片收口为纯离线专用诊断与负结果审计，无API/UI/默认接入。停止以该固定ER条件改善主标签为由扩张；前向SE-05与PIT/复权/公司行动/成交、Windows/浏览器、49旧skip继续未验。后续独立研究需新的明确用户任务和审批，不沿用本片“算法优势已验”的结论。
