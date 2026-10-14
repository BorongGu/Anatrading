# OHLC 兼容路径的最大源价跌幅：最小纯核心设计 v2

2026-10-14 UTC。状态：**独立数学设计已 GO；本 v2 完成 R1/R2 最小澄清，待审查者确认后由负责人决定实现准入。** 基准为 Anatrading main `17c9064794969340fcac1210f82e940d760c8bd4`。本设计写在仓库外；本任务没有修改、发布或运行产品。

## 决定与一小时自评

**继续推进：选择确实增加可识别数学信息的单窗纯核心。** 067 已合并；真实采集所需旧历史缺失仍阻断，不再以重复网络尝试充当研究进度。本轮实际完成前置固定反例实验的证据核读、相关现有合同/源码核读、两份一手来源定向核读及本设计；下一项可验证动作是独立反方审查本文件与证明，冻结修订后再决定最小代码实现。

前置协议 SHA256 `d243553b065158f292ef073313d958e00d32c13b5f10696f2a9e16e59bedf605`，原有 PROTOCOL.md、experiment.py、result.json、run.log 均已阅读，未修改、未重跑。原实验共 129,960 条单/双柱合成路径、420 个 OHLC 分组，精确不一致 0，结果为 GO_RESEARCH_REVIEW_ONLY。它检验有限域、重复极值和内点访问；不等于任意实数路径的证明，也不等于产品验收、真实兼容或市场价值。下文另给一般证明。

真实行情/真实适配器、API、实际浏览器与截图、Windows 原生、持续性能、人效、样本外预测与交易价值均未验。实采 NO-GO、历史可得性等原限制继续有效。

## 1. 有什么新增信息；哪些已有能力保持不动

已全文核读研究 015、050、054、060、064，并核读 numeric.py、research_series.py、pair_research.symbol_identity、candle_geometry.py、close_dispersion.py 和 064 限定验收。

- 015 保留单根 OHLC 的几何与盘内顺序不可识别性。
- 050 从收盘观察定义回撤段和恢复；054 从组成员收盘构造来源平均路径；060 从收盘记录阈值反转。它们均未计算所有 OHLC 兼容路径上的最大跌幅最小值和最大值。
- 064 提供纯 Python 核心/严格正 OHLC 查询适配器的可复用边界，其历史全窗输出成本也支持本片只返回一个选定窗。

拟增加一个纯 Python 模块 `ohlc_decline_bounds.py`、专用测试与研究/评审记录；复用已有数值解析和 daily_bars，不修改旧合同。无新依赖、Store 调用或导入、HTTP 路由、UI、CLI、通用缓存、排名、信号、参数搜索或真实数据获取。

用途只是：同一来源窗口，收盘描述遗漏了多少可识别的跌幅信息，以及 OHLC 尚允许多少顺序歧义。输出上下界均是确定性集合极值，单位为无量纲比例；不输出概率、置信区间、财富/组合回撤、可成交亏损或交易建议。

## 2. 一手资料：实际阅读与采用边界

2026-10-14 定向读取 Tommaso Proietti, *Ups and (Draw)Downs*, CEIS RP576（2024），§2 Definition 1 与 §6.1、相邻 §6.2 起始处：
https://ceistorvergata.it/RePEc/rpaper/RP576.pdf

论文以对数价格、截至当前时点的滚动收盘回撤定义对象，§6.1 以高低序列包围该对象。本片是一个固定窗口内、所有相容盘内路径的最大比例源价跌幅之极值，另有 open/close 次序约束。对象和紧界不同，不称论文复制、论文算法实现或经验结果复现；不引入其随机扰动择平局、滤波或预测。

同日读取 TradingView Pine Script 文档 “Broker emulator” 的柱内路径假设及 high historical detail 示例：
https://www.tradingview.com/pine-script-docs/concepts/strategies/#broker-emulator

该文档说明默认成交模拟会按开盘离高/低的远近选择 OHLC 顺序，更细数据可改变模拟。这里同时保留两条极值证明路径，不按开盘距离猜测实际顺序，不计算成交。下列紧界和证明是本项目推导；未据此主张文献原创或竞品优势。

## 3. 数学对象与边界

输入有序 m 根 OHLC，1 ≤ m ≤ 253。每根满足 0 < L ≤ O ≤ H 且 L ≤ C ≤ H。所有数必须可精确表示为 DECIMAL(38,18)。仅数学核心接受已排列数组；来源适配器按唯一可读日线日期排列。

相容路径由逐根有限正价序列拼接而成；每根首点 O、末点 C，最小值 L、最大值 H，内部可有任意重复/往返，所有点在 [L,H]。相邻柱以已给出的前 C 和后 O 直接相邻，不插入未观察价格。允许 O/H/L/C 相等；重复值保留为证明路径的独立位置。对任一路径 P 定义：

D(P) = max(0, max_{s<t} (P_s − P_t)/P_s)。

目标 lower = min_{相容 P} D(P)，upper = max_{相容 P} D(P)。窗口从首根 O 初始化，不借用窗前峰值。可在每根内用单调线段补全证明路径而不改变极值，但这不授予时间连续性、成交或跨缺日可见性。

**供给范围是合同的一部分。** 输出 `scope=supplied_bars_compatible_paths`。未提供的日历日期、柱内未报告极值、前后市/非交易时段、窗前价格都不在集合约束内。即使没有检测到坏行，真实完整时间区间也可能有遗漏。upper 只约束已提供柱兼容路径；若漏柱，不能称完整真实区间跌幅上界。真实缺失区间可任意接近 100% 跌幅，现有数字不给额外限制。lower 也只以源值可信且共尺度为前提，不保证为经济收益下界。

## 4. 紧界公式与证明

初始化 M=首根 O，lower=upper=0。逐根令 A=max(M,O)，B=max(M,H)，更新：

lower = max(lower, (A−L)/A, (H−C)/H)
upper = max(upper, (B−L)/B)
M = B

首根的 M 是初始化 O；其后 M 为此前所有柱的最高值。第一式中的 A≤B；两式均为精确有理数。

证明下界：当前 L 被访问前，所有前柱极值及当前 O 已访问，故至少有 A 到 L 的跌幅；当前 H 被访问后最终必须到 C，故至少有 H 到 C 的跌幅。此前已产生的最大值不能消失。任何相容路径因此不小于 lower。

证明上界：任何当前柱内谷值 ≥L，任何在它之前出现的峰值 ≤B。正价比值 1−谷/峰随峰增加、随谷减少而增加，故它不超过 (B−L)/B。对所有柱取最大得到 upper。

达到性：逐根使用 O→L→H→C，前最大值到 L，以及升到 H 后到 C，恰给 lower；逐根使用 O→H→L→C，恰给 upper。跨柱 gap 从前 C 到后 O 已含在同一扫描，后 O≥后 L，不产生超出公式的新最大值。两条均符合相同 OHLC，故两个界均可达到。**证明给出两个端点可达到，不额外声称二者之间每个值均可达到。**

因此 close-only 最大跌幅 ≤ lower ≤ upper <1；lower=upper 表示此标量在该相容集合被唯一识别，路径、极值真实时刻和交易结果仍可能不唯一。

## 5. 最小实现入口、数值与见证

### 5.1 纯数学入口

`exact_bounds(bars)`：只接收 list/tuple，先检查 1..253 长度，再检查每项为恰四项 list/tuple，顺序固定 O,H,L,C；不消费任意迭代器。先完整验证全窗，再计算，任意非法项拒绝整个窗，不发部分结果。容器/长度为 `invalid_ohlc_window`，行形状为 `invalid_ohlc_bar`；数值保留 NumericError 原因码；非正为 `nonpositive_price`，几何错误为 `invalid_ohlc`。错误包含首个失败的 bar_index/field（不存在则 null），不给源身份认证含义。

使用 `numeric.decimal_value` 的既有类型/有限性/范围/尺度合同；bool、float、NaN、Infinity 拒绝。采用规范 Decimal tuple 构造 18 位定标整数 u，1≤u≤10^38−1；不执行受调用者上下文影响的 Decimal 乘减除，不转 float。现有 parser 接受的等值十进制词法仍接受，不自创新词法规范或全局改 parser。

最小算法建议直接对两个极值路径各做一次常数状态最大跌幅扫描，同时扫描 close-only 基线。这天然保留最早端点含义，代码比维护公式候选的同值映射更简单。路径以迭代视图产生，不复制 4m 项数组。公式作为证明与产品测试的交叉检查，测试主 oracle 则独立枚举所有先后点对。

每次先以此前峰值计算正跌幅，再仅在价格严格更高时更新峰；同价峰保持首次。最大跌幅只在严格更深时替换。正跌幅并列取最早谷位置，再取该谷前最早等高峰位置。注意“最早”按各自证明路径的顺序解释；不同路径的槽位顺序不同，不能当成实盘时间比较。

两个路径 ID：`olhc-extremizer-v1` / `ohlc-extremizer-v1`，槽序分别 `[open,low,high,close]` / `[open,high,low,close]`。保留全部重复槽位：H=O 时最早峰可能是 open；L=O 时最早谷也可能是 open；不能强制把见证写成 high/low。端点字段 `bar_index,slot,path_position,price_exact`，其中 path_position=4*bar_index+槽位序号。数学结果不带虚构时分秒。

每个边界输出 `value={numerator,denominator}` 和 `witness={path_id,hypothetical:true,peak,trough}`。最大值为0时 value=0/1、witness=null，路径 ID 仍由顶层规则给出。不用零深度端点冒充真实回撤。close-only 同样返回精确分数及峰谷 bar_index（无正跌幅时 null），其择平局规则也是最早谷/最早峰，明确与 050、054 既有规则独立，不改它们。

顶层另给 `identified`（精确分数相等）与 `ambiguity_width=upper−lower` 的约分分数；不输出四位近似、风险分级、每柱结果或整条假想路径。权威分数 numerator/denominator 为十进制整数字符串，分母正，gcd=1。不使用显示值判定相等。

所有价格整数<10^38；单个跌幅分子/分母<10^38；两个跌幅比较或区间宽度的中间交叉积<10^76<2^253。宽度约分前分母最多76十进制位。无需 LCM、对数、sqrt 或任意精度 Decimal 运算；整数上界与 m 无关。局部核最多 2×4×253+253=2,277 个点访问（不包括输入解析），常数扫描状态；保留输入/输出成员证据另计 O(m)。

### 5.2 来源报告入口：限定的纯查询适配

`decline_bounds_report(query, start_date, end_date)` 只消费已由可信读取边界获取的完整日线前缀。它不访问 Store、不读取原始文件、不下载、不自行认证任意字典。start/end 是严格 ISO 日期、start≤end；query.selection.cutoff 必须恰为 end_date，mode 必须 retrospective，period=1d，拒绝 ordinal_start/end 裁切。**两个端点都必须恰有来源日期组**，缺端点返回 unavailable，不回退到近邻日期。

形状检查与 064 同类：query/selection/metadata/manifest 为字典，rows/unlocated 为 list/tuple，source rows+unlocated≤20,000。各源行、values、tokens、checks 等必须满足既有 query 结构；损坏结构统一受控 `invalid_decline_query`，不吞掉内部算术错误。snapshot_id/batch_id/query_id/source_contract_id 非空字符串、每项≤256 UTF-8字节；raw_sha256 为64位小写十六进制；symbol_identity 沿用现有来源/声明一致性检查。身份格式错误整调用失败，不伪造 unavailable 报告。

原样复用 daily_bars 与 daily_coverage 的来源日期组规则；选择日期闭区间 [start,end]，不做日历填补或交集。完整前缀中的日期组用于覆盖/来源核验，只有选定窗送入数学核。窗口超过253组为 `ohlc_window_limit`，在数学及成员结果构建前拒绝；不能截前/后253组。单柱 start=end 合法。

资格分层冻结如下：

1. 来源隔离/known_negative_source，或任一源行明确来源代码、复权冲突，关闭本报告。冲突核验复用 research_series 的 source_rejection / _source_conflict；核验全部已供给源行，避免重复日期掩盖全局冲突。逐行调用现有 helper，只记录该行按既有优先级返回的首个来源冲突；每行至多增加一个 `source_conflict_counts` 计数，不只看所选日期组的 reason。`source_conflict_policy=first_rejection_per_source_row`；发生首个冲突后被短路的后续判据标作未评估口径，不承诺穷举同一行并发的所有原因。known_negative_source 单列来源级 `source_rejected` 布尔标志，不按行重复计数。未来行新增这类全局反证可以撤销资格，区别于未来纯数值不变性。
2. 任意未定位 label、不可读日期、batch_unlocated_rows>0 或 coverage_known=false，关闭本报告为 `source_coverage_unknown`。无法确定它是否落在窗内，不为它编造位置。这比064局部离散允许带未知覆盖计算更严格，独立明示，不改变064。
3. 起止任一日期组不存在：`endpoint_not_present`，同时列 `missing_endpoints`；空来源亦如此。不向更早有效点回退。
4. 选定窗任意 source_reason（重复日期、坏价、坏 OHLC、missing_ohlc 等），或唯一源 ordinal 无效，使 `invalid_window`。日期组仍占位，整窗不计算，不跳坏行、不重置后继续。
5. 其余 computed；日历未提供的日期仍未知，固定声明 `calendar_completeness=unverified`。volume/amount 的失败不额外阻止价格计算。

上述优先级决定主 reason；`reasons` 是各已执行分类器返回的原因码去重列表，`source_conflict_counts` 只计逐原行首个来源冲突，`invalid_members` 只记每个窗口日期组的既有首个 reason；这三者的统计单位不同，不相加为异常总数。coverage 的计数保持既有含义。输出固定 `suppressed_source_predicates=not_evaluated_after_first_rejection`，不另造逐行并发判据明细。正常结构下仍遍历全部源行和选窗成员，避免遗漏后续行；每行/组内部仍按既有 helper 的首个拒绝短路，未评估的并发原因不计0或称不存在。invalid_members 按窗口位置完整保留。窗外普通坏价/重复日期仅留在 coverage，不改变窗内数学资格；窗外无法定位/全局冲突仍关闭。来源 ordinal 只作定位：合法值为非 bool、0..2^63−1 整数，选窗内唯一，输出十进制串；重复日期组保持 ordinal=null；原 query 的所有行均保持不变，使用顶层 query 身份加该 source date 回查整组原行。报告不嵌入逐条重复原行引用，不编造唯一序号、不扩张成员字段或输出载荷。

### 5.3 报告身份与证据

顶层固定：
- method_id=`source-ohlc-compatible-max-decline-v1`
- adapter_id=`daily-bars-positive-selected-window-strict-coverage-v1`
- numeric_policy_id=`scaled18-rational-earliest-extremizer-v1`
- scope=`supplied_bars_compatible_paths`
- identity 包括 snapshot_id、batch_id、query_id、raw_sha256、source_contract_id、selection（本次已核字段）、symbol_identity、manifest.qualification 的深复制。
- window 包括 requested_start/end、resolved_start/end（仅确实存在时）、bar_count、first_open_initialization=true。
- coverage 保留 daily_coverage；source_qualification 保留原值，计算不能升级来源。
- members 为至多253个连续窗口位置，字段 index/date/ordinal/open/high/low/close/source_reason；OHLC 是规范精确文本，不能解析的值为null。源 token 不重复复制；标记 `price_evidence=normalized_source_values`、`raw_token_status=not_embedded`，原 query/raw hash/ordinal 用于已授权来源回查。
- status/reason/reasons/invalid_members/missing_endpoints、source_rejected、source_conflict_counts、source_conflict_policy、suppressed_source_predicates，以及数学结果。

computed 时结果含第5.1所有字段；任何 unavailable 时 lower/upper/identified/ambiguity_width/close_only 全部null，成员/身份/coverage保留。witness端点仅引用 members 中的 bar_index 与对应字段，报告补 date/ordinal 时必须由该成员解析，不接收自报见证。限定说明始终含：hypothetical_extremizers、window_pre_history_excluded、calendar_and_bar_finality_unverified、adjustment_and_corporate_actions_unverified、historical_availability_unverified、source_values_not_economic_wealth、upper_not_full_real_interval_bound_if_observations_missing、no_prediction_or_execution_claim。

不新增通用 analysis_id 或哈希层：完整身份与精确成员是本地纯输出，可信调用方负责来源链。相同身份字符串不能认证任意输入，也不能允许忽略成员内容的缓存。未来API/导出接入必须另审 content binding；本片不创建缓存。复制可变身份/成员，输出修改不得污染 query。

## 6. 基线与必留反例

所有数字为 (O,H,L,C)。保持前置四例，不按实现结果改期望：

1. [(100,100,100,100),(100,120,80,100)]：close-only=0，lower=1/5，upper=1/3。同收盘没有回撤，仍有必然正跌幅与盘内顺序歧义。
2. [(100,100,100,100),(120,120,80,80)]：close-only=1/5，lower=upper=1/3。相同收盘序列也能对应不同 lower；OHLC 增加可识别信息。
3. [(100,120,100,120),(120,120,80,100)]：lower=upper=1/3，close-only=1/6。前柱高点先于后柱低点；不能仅以本柱幅度判定。
4. 常量100：三个值均0，全部正跌幅见证null。
5. 单柱 (100,120,80,100)：lower=1/5、upper=1/3；只有一根也可计算，不能套用至少两个 close 的限制。
6. 缺柱反例：仅给前后两根常量100得上下界0；若遗漏中间路径100→1→100，真实区间最大跌幅99/100。原0上界不得外推。
7. 顺序反例：先平价1、后平价2，两界0；全窗最高到最低粗公式给1/2，违背先后次序，不能采用。
8. 平移反例：100→80 跌幅1/5，整体加100后200→180为1/10；比例仅对共同正倍率不变，不对平移不变。倍率变换须仍落在输入格点/范围内。
9. 极小正差：最大格点 (10^38−1)/10^18 与低一个格点；跌幅=1/(10^38−1)>0，float碰撞不得改成0。
10. 重复槽位/峰谷：O=H 时峰择 open；O=L 且前柱有高峰时，当前最早谷可为 open；相同深度较晚谷不得覆盖较早谷，较晚同高峰不得覆盖首次峰。

最强朴素基线为两条假想路径各展开≤1,012点后，枚举全部先后点对，用 Fraction 求最大值和最早见证。它足够服务人工小例，本片仅带来可复用精确/有界计算与来源约束；没有已测人效优势。

## 7. 编码前冻结验收与停止条件

先写异常测试再实现；独立 oracle 不调用候选扫描，也不复用其峰更新。数学验收均要求精确全等、0容差，不按结果调参数。

A. 原有限域：保持 alphabet={1,2,3}、每根长度2..5，全部360条序列、全部有序双根组合，按OHLC分组，从原路径全先后点对得到极值；与129,960条、420组账本一致。对产品返回上下界、两个端点达到性、close-only≤lower≤upper<1逐项比较。原协议输出不覆盖，新增实现验收单独保存。

B. 见证独立oracle：对两条证明路径全点对枚举，并按 `(谷位置,峰位置)` 最小择平局，核对值、bar_index/slot/path_position/price_exact、字段映射和null。覆盖每种OHLC相等组合、跨柱gap、平峰/平谷、多次同深度、较早open与较晚low等值、最低先于最高、只有末close下跌。不得只核见证自洽。

C. 固定例与边界：上述10例，m=1/2/253、0/254拒绝；最小/最大合法格点、循环分数、相邻大数、近1跌幅、宽度为0和非零。完整输出JSON往返无float且精确字符串不变。恶意 Decimal context prec=1、不同rounding、Emin/Emax与traps不改变结果。输入容器/结构、bool/float/NaN/Infinity、缺值、非正、范围/尺度、几何错误均整窗拒绝。

D. 每个合法前缀：固定起点重新计算与独立前缀oracle一致；在已有固定窗后追加/修改有效未来数值不变旧数学和见证。最大跌幅上下界各随追加不减，二者差值无单调承诺。正倍率缩放（保持输入合法）不改分数与位置；给平移、删除行、逆序明确反例，不误要求不变。

E. 合成可信 query 夹具（不用Store）：严格日期/精确cutoff/start/end、非日线/非retrospective/ordinal裁切、身份字段缺失及冲突；重复日期、重复/坏ordinal、unlocated/unreadable/batch_unlocated、隔离、代码/调整冲突含被重复组掩盖的情况；窗口内任意坏OHLC整窗失效；窗口外普通坏价保留coverage；volume/amount坏仍可算；缺端点不回退；全体缺日仍只标未知日历；源行20,000/20,001及窗253/254边界。所有分支保持结果null规则、成员/分类结果无截断。固定一条同时含 code 不符、adjustflag 不符及 source_adjustment 检查失败的合成行，另放入重复日期组且置于选窗外：它仍关闭报告；该行只给 source_identity_conflict 的计数加1，两个被短路原因不列为已评估结果。其他独立行返回的调整类首因仍各自计数。同一原行重复的失败 check 不使它被计多次。重复日期成员须 ordinal=null，仅保留 query 身份和日期定位；验证未生成逐原行引用字段，且原 query 所有重复行未被改动。

F. 身份/不可变性：改snapshot/batch/query/rawhash/selection/qualification必须反映报告身份；相同价不同来源不会相混；query和原行不被修改；编辑输出不改变query。改变历史行可以改变结果；不同query身份的完整报告无需字节相同。未来纯数值变化与未来全局来源反证分别测试。

G. 成本：无整历史逐窗输出，完整成员≤253、见证≤6端点。限定投影后的身份及来源资格JSON≤16KiB，否则 `ohlc_metadata_limit`；整份 compact UTF-8 JSON≤256KiB，否则 `ohlc_result_limit`，不删字段/原因/成员凑预算。成员的有界字段使正常上限足够保守，仍必须在最终序列化后实检。输入词法文本/已构造query的内存属于已有可信读取边界；本纯核不声称抗任意无限词法载荷。

H. 实现完成后另冻结一次资源观测：分别用253根有效最大/最小交替值、253根无效组、20,000来源行中选253根的合成query，独立子进程，256MiB地址空间、120秒墙钟/CPU、完整输出256KiB限制。量测解析/排序/核/序列化、进程RSS和输出字节；超过预算即停止，保留失败，不扩大预算重试。它是限定资源观测，不是稳定性能或函数增量RSS证明。数学核O(m)，整个适配器包含O(n log n)排序与O(n)存储，n≤20,000，不能称整链O(253)。

I. 产品回归后续范围：新增测试及受影响 numeric/research_series/candle_geometry/close_dispersion/price_channel/true_range/signal_research；必要时完整允许集合单列。禁止读取旧DB、真实捕获或寻找私有样本；合成Store集成与原生socket/浏览器不在本设计任务内。缺私有样本skip保持未验。依赖/产品/环境兼容实际通过、失败、skip、未跑分开报告。

任何数学不等式、达到性、见证、身份、坏行保留、预算或不变性失败，停止进入实现/发布下一阶段，保留反例并审查定义或实现；不改旧冻结实验期望以适配结果。独立反方可否决用途增量或收窄接口。

## 8. 最小选择的取舍与下一步

候选比较：
- 仅保留研究推导：成本最低，但已有重复可验证的信息缺口值得一个小纯模块；若独审认为无具体使用需求，可停在此处。
- **单窗纯核+薄可信查询适配（推荐）**：两条证明路径共用简单扫描，fraction输出，无显示/异步/网络生命周期；可验证新的可识别信息，且资格成本有限。
- API/UI或多股批量：引入请求ownership、导出身份、端到端展示、成员对齐和额外资源验收，当前证据不支持扩张。
- 复用某条默认成交模拟路径：无法给出未知顺序的区间，且引入未经证明的实际次序，放弃。

本片不把253当市场最优窗口，不把严格正价当对其它资产的理论裁定。源码接口是研究复用边界，尚未成为用户工作流；如无后续真实查询资格与具体研究任务，维持core-only。

交付后先请独审确认本 v2 的两项澄清，重点检查路径集合/缺柱边界、一般紧界证明、重复槽位择早、全局来源反证与局部坏价分离、宽度整数范围和错误预算。独审意见逐项答复、必要时形成v2并重新冻结；只有负责人明确GO后才创建最小实现。当前工作树只读检查为干净，原实验未重跑，没有新的产品/真实/预测验收声明。

## 9. v1 → v2 变更与独审闭环记录

v1 原件 DESIGN.md 保持原字节，SHA256 `276d0d3593ec3a1b1b3f2eb43235f87f249ce360736f501ec20a78c2e4f08f95`。独立审查已给数学设计 GO，并要求 R1/R2 澄清；本次只写仓库外 DESIGN-v2.md，无产品修改。

- R1 接受较小方案：采用已有 helper 每行首因分类及短路语义。新增并发判据收集并不影响是否拒绝和数学结果，也无明确用户需求，本片不增加该诊断框架。源码来源级隔离标志、逐行首冲突计数、逐日期组首因和coverage分别披露，不称全并发原因穷举。冻结三冲突同一行、重复日期掩盖、窗外位置的合成反例。
- R2 接受最小表示：原 query 不变；重复组成员只以顶层 query 身份和日期回查，ordinal=null；没有逐重复原行引用、原文复制或扩大载荷。
- 不改公式、数学域、253柱限制、择早见证、字节预算、缺柱解释或原实验标准。旧 v1 与审查的负面发现均保留。
- 独立审查额外报告8,000三柱组合、64,000极值顺序路径、16,000见证比较及8固定例均通过；这些是独立合成数学补证，未由本设计者重跑，不与原实验相加成市场样本，不替代产品适配验收。

下一门槛：审查者确认此 v2 hash 后回报明确 GO/NO-GO，负责人再授权实现；确认前不写产品代码。
