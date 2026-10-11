# 034 一步源价误差诊断：正式编码前独立审查

日期：2026-10-11。审查对象：[034 研究候选](../research/034-causal-signal-diagnostics.md)，含其 §12 研究级反方修订。审查时 checkout HEAD 为 `41190aa91d3af52c4a75e772fb2579ab4fc044c1`，工作区另有 033 并行修改。本审查仅写本文，不修改产品、现有测试、033 方案或证据。

## 1. 决定与许可边界

**最新决定：§8完成分层终审。正确性/因果性/旧输出兼容、固定真实来源诊断、时延及完整JSON分别通过；8MiB新增内存预算仍未验。集成负责人已明确接受此开放项，批准仅独立调用、无API/UI/默认服务接入的纯诊断能力有限合并。原FD-06完整资源验收未通过，真实负结果必须保留。** 以下保留首轮审查、设计批准与当时033执行冻结的过程。

**首轮决定：接受收窄后的计算目标，暂不授予编码许可。** 研究级修订已经解决主要因果公式与解释问题；接下来需要作者将下列 FD-01～FD-07 逐项落实到具体实施计划并答复，独立复核答复后再作解冻决定。即使解冻，也仅限单证券、明确单截止、固定参数的纯函数和私有共享状态接入，不包括 HTTP、页面、分钟、选股、自动模型切换或新来源认证框架。

核心价值是把现有 K/R 误差放到同一批前序来源槽上，与滞后 EMA 一起形成可复算的配对损失审计。现有 `innovation` 与 `log_return` 已分别给出 K/R 的当前误差；新增之处在于严格前序窗口、共同分母、证据与负结果。经验 q 的产品价值待固定真实矩阵判断，不能预先承诺保留。允许最终仅保留配对误差审计，不接页面。

本轮不重新审阅论文，也不重复 §12 已关闭的研究级意见。以下结论来自实际代码、旧测试和项目文档的静态核读；只用 Python 内置 math 核对上界舍入、最小非零浮点除60下溢和82槽计数，没有导入产品或运行产品测试、性能、真实数据实验或数值搜索。033 正式资源窗口结束并经协调前不得开始这些负载，约 08:07 UTC 只是当前预计结束时间。

## 2. 实际代码依据

| 核读位置 | 本次确认的约束 |
|---|---|
| `signal_research.py:42–61` | `_update` 先算 `level+slope`、预测协方差和创新，再更新状态；Joseph 标量运算顺序已经固定。直接在此取得 prior 有真实实现路径，无需重写滤波器。 |
| `signal_research.py:64–132` | 首行只初始化，`observations<=20` 为预热；坏组和数值错误令 `active=False`，下一有效行才增加 segment。既有 try 捕获 ArithmeticError/OverflowError/ValueError，新诊断错误不能被放入这里伪装为旧模型 reset。 |
| `signal_research.py:135–154` | `signal_report` 同时做 events、完整 series、coverage；新纯函数不应调用它后复制全量结果，也不能默认给其公共输出增加字段。 |
| `research_series.py:54–75,78–106` | 已有隔离、证券/调整冲突、OHLC 合法性 helper；volume/amount 失败不影响价格计算。复用这些边界，不为本片复制另一套来源判定。 |
| `research_series.py:110–151` | 按日期组保留坏/重复槽；20,000 行预算计 rows 与 unlocated；ordinal 裁剪拒绝；已定位未来可排除，但未定位及批次未知数持续影响覆盖资格。 |
| `pair_research.py:56–79` | `symbol_identity` 已能规范 source/interpretation 的证券与市场声明，并保留声明资格；规范化身份不等于来源认证。 |
| `store.py:77–87,417–493` | 复用规范 JSON/hash；Store OHLC projection 与完整查询共用既有 query_id，逐次验证原件。纯函数不另造 Store、签名或证书体系。 |
| 旧 `test_signal_research.py`、`test_research_series.py`、`test_research_adversarial.py`、`test_research_projection.py`、`test_research_api.py` | 已有矩阵参考、逐前缀、reset、精确源值、低 Decimal context、源冲突、projection/完整查询与旧 API 身份等回归；新检查不能通过改旧预期把既有行为悄悄收紧。 |

静态核读 SHA-256：

- 034：`219884f53ae9a04d05783a3f5e54517c581040edfdbfcc5feacc9b310d3be460`
- `signal_research.py`：`8b0d041a9b5731e9f719783afe09aa8936766002368fe37c55fb525f640f55c2`
- `research_series.py`：`c4f3f49e4a17d757e7cd5d5dd9bb2d2cb96d1c257276c1f8fa875ddac5e136e9`
- `numeric.py`：`a7c66d7c609e771aa8ab43a124aec418bea6261aa7ae6feb50a169627d10b58a`

同时核读 [026](../research/026-causal-signals-and-evaluation.md)、[029](../research/029-automated-ashare-data.md)、[030](../research/030-peer-relative-research.md)、[既有性能记录](../qualification/research-performance.md)、[同伴真实验收](../qualification/peer-relative-research.md)及 AGENTS。并行修改的 API/集合代码只用于确认现存边界，不要求本片修改或取得 033 所有权。

## 3. 冻结的最小实现方向

### FD-01：共享 prior 与时间顺序，编码阻断

允许一个新专用模块，例如 `forecast_diagnostics.py`，入口 `forecast_diagnostic_report(query, *, cutoff)`；只对固定三个预测器做纯计算。允许将现有循环机械提取为私有 `_causal_rows(bars, *, capture_prior=False)`，旧 `_causal_series` 收集既有 row；不引入通用事件总线、插件或公开 callback。

必须同时满足：

1. 关闭 capture 时不创建 prior 记录；旧函数签名/公开字段/字典结构、数值、参数、reset 和错误语义原样保留。`_update` 的算术顺序不重排、不改求和算法、不顺手修复旧行为。
2. 启用时从吸收当前观察前的状态保存 K=`level+slope`、R=`previous_y`、E=`ema`、K 的 S、RW 的 EWMA pre、segment、预测起点日期/ordinal、起点累计观测数。使用标量快照，不能引用稍后会被修改的状态对象。
3. 禁止当前 `log(close)-innovation` 倒推 K；禁止从后验状态逆推；创新仅作事后精确交叉检查。对于正常可计算步，K error 与既有 innovation、R error 与既有 log_return 应同环境逐值相等。
4. consumer 只保留最后 60 个共同误差槽及常数大小状态。不得把 T 个 prior、T 个窗口或完整 `signal_report` 一并保留。若 generator 在更新后 yield `(row, prior)`，应在请求截止 D 那次 `next()` 前冻结前序 ring 的 q/MAE/RMSE，然后处理 D；不为了“先保存摘要”对每根重算滚动分位。
5. private prior 的生成与 collector 的汇总错误不得落入旧滤波 try/except。未知内部不一致应抛出可辨认内部错误；不能静默重置旧模型或返回看似正常的 unavailable。
6. 当前非法价或精度碰撞可以关闭公开本步诊断；已有 prior 不得被当前价改写。测试须观测实际生成/调用顺序，不能只看最终字典碰巧相等。

允许重复计算几个 prior 标量以保持旧 `_update` 运算不动；禁止第二套 Kalman 递推。若机械提取无法保留 golden，停止并重新审查，不能扩大至多个研究模块重构。

### FD-02：单截止、身份与来源边界，编码阻断

最小入口保留显式 cutoff，但要求输入 `selection.cutoff` 同值且为严格 ISO 日线日期。缺失/不一致拒绝 `research_cutoff_mismatch`；非法日期拒绝 `invalid_cutoff`。不自动选末条有效日期，也不在纯函数内裁出新 D 后继续冒用旧 query_id。调用者应通过既有 Store 查询取得同 D 完整来源前缀；没有 HTTP 路由需要新增。

- 先校验 period、cutoff、无 ordinal 裁剪及 `len(rows)+len(unlocated)<=20,000`，再归一化/递推。输入不得被修改。20,001 行不进入递推。
- 复用 `symbol_identity`、`daily_bars`、`daily_coverage`、`source_rejection` 及现存规范 hash helper；不复制 peer-relative 的专用腾讯来源白名单，不因来源格式未“认证”就关闭一切合法日线源价算术。
- 可以识别的证券声明、未知复权/日历/closed/known_at允许条件性源价误差诊断。证券身份无法解析、明确隔离、明确身份/调整冲突与未定位覆盖问题按 FD-03 处理。不能借本片升级来源资格。
- 新 method_id 与旧 `daily-causal-research-v1` 分离；analysis_id 至少绑定有序 snapshot/query 输入及 cutoff、完整固定模型参数、W=60、p=0.90/rank=54、origin-warmup 与数值/窗口规则版本。复用既有 `_identity`，不对每根原件重新建内容身份，也不把任意调用者提供的 ID 当认证证明。
- 计划应列明实际来源摘要投影，保持紧凑且足以解释身份、调整、历史可得/闭合状态及其 unknown。输入已处于可信 Store/合成夹具边界，不为此建立通用不可信 JSON 验证或新密码学信任层；测试修改合成内容时也要区分计算不变性与真实版本身份改变。
- 首片去掉额外 `events` 输入。已知停牌/公司行动的公告、影响日期和知识时间放到固定真实验收上下文；产品明确尚未识别这些事件，经济收益/单交易日解释持续关闭。以后若要接受事件并改变资格，须另审事件范围、known_at与身份。不要只接两个事件名却暗含完整事件认证。

### FD-03：输出、失败优先级与计数，编码阻断

作者必须在计划冻结字段表及错误表，不将所有结果合成一个 green/false。最小返回保留 method/analysis/input/parameters/mode、数值单位、来源与历史资格，以及当前、前序窗口、三模型原值/差、≤60 槽证据。首片不输出 exp 价格上下界、目标价、胜率、标准误、置信度或自动信号。

| 作用域 | 必须冻结的行为 |
|---|---|
| 调用错误 | 非日线、非法/不匹配 cutoff、ordinal 裁剪、超预算及无法解析的证券身份用现有/明列 ValueError；未知编程错误不转成泛化可用性原因。 |
| 全局来源限制 | 隔离源、无法定位行或 `batch_unlocated_rows>0` 关闭主诊断，保留 coverage、精确源信息与原因。计划须说明哪些计数仍按结构可算、哪些未执行，不能以 0 冒充未执行。 |
| 局部源/基状态错误 | `daily_bars` 和旧 signal 给出的坏/重复/冲突/数值错误保留槽位，清 ring；下一既有 segment 重新预热。明确冲突不能降级为普通 unknown。 |
| 截止缺失/坏价 | `cutoff_missing` 或该源槽原因；不回退前日、不把缺当前视为范围内、不把上一窗口冒称截至 D 的完整当前诊断。 |
| 正常段 j1…21 | 预测起点尚未成熟；j21 虽旧 `warmup=False`，其起点仍是 j20，不能计作共同合格误差。 |
| 正常段 j22…81 | 当前三模型共同误差可算；q/前序MAE/RMSE/范围真值为 null，原因 `calibration_history_insufficient`。不足 60 不展示缩短窗损失。 |
| 正常段 j82 起 | 使用紧邻同段 j−60…j−1；不得按模型分别筛选，不删坏值补历史。 |
| 诊断精度/损失失败 | 按 FD-04 的状态段和字段依赖处理，保留原因及槽；不能把诊断失败传播为旧状态 reset。 |

正常 82 槽的强验收为 21 个预测起点未成熟、61 个共同误差；其中 60 个前序窗不足、1 个完整。源/状态不可评价与起点未成熟、共同误差必须互斥且守恒；同段精度失效优先于 warmup，不得让 tainted 后缀被统计为普通预热。无法定位原行与已定位日期组是不同计数单位，重复组也不能与原始行数混算。

窗口证据至少能复算三模型损失并追溯各条 origin/observation 日期与 ordinal、segment 及观测数。current 和 window 的时间字段应定义一次，不在每个模型复制来源摘要。公开 `calculation_status`、`source_qualification`、`historical_availability` 分开；即使数值可算，也只能写条件性源价格诊断。

### FD-04：数值契约与失效依赖，编码阻断

- 源值仍是既有 DECIMAL(38,18) 可表示正价与规范精确字符串；raw token通过源引用查看。不要用 `1e999` 作为新算法接受范围，也不要扩大 numeric/store 的值域。
- 从同段 j2 检查相邻精确 Decimal 不同却 float 或 log 相同；立即将该既有 segment 余下新诊断标 `precision_loss_state_dependency`。仅到旧模型真实 reset后恢复。第一处之前的结果不追溯作废，旧 signal 不改。
- q=排序绝对误差第54名；用 error-domain 的严格比较判 above/below/inside，相等为 inside，q=0有效。不加 epsilon、不输出 e/q。
- MAE 用 `math.fsum(abs(e))/60`；RMSE 用明列顺序的 `sqrt(math.fsum(e*e)/60)`，每个非零 e 的平方下溢为0或非有限都显式失败。sum、mean、sqrt、difference 的有限性及正数除60下溢边界也须在实现中明列，不能只查最终 NaN。
- RMSE 单模型失败只关闭该 RMSE 及相关 K−R/K−E 差；q/MAE/current error保持各自资格。失败槽在固定60槽 ring中保留，直到离窗才可能恢复，不删槽后补满。
- lower/upper失败只关闭展示端点，不把仍可判断的 outside改为false；width或interval score失败仅影响对应离线指标，不改变误差或观察计数。
- delta_MAE/RMSE 的方向固定 K−baseline，负值只描述该窗该损失较小；分别列 K/R/E 原值，不能选最有利损失或者根据两步较好报告“胜率”。

原代码支持的源价 log 范围有限，一些溢出极端不会由正常 Store价产生。测试可对专用私有数值 helper注入有限浮点边界验证失败传播，须明确是数值防御测试，不能为覆盖分支去改源合法域或旧模型。

## 4. 必要验收门槛

### FD-05：独立 oracle 与旧 golden，编码阻断

编码顺序：先写新异常用例、局部手算和独立参考，再作最小产品变更。旧 tests 保持原预期。新增验证至少覆盖：

1. **独立高精度参考。** 60 位局部 Decimal context，从精确源字符串取 ln，用通用 2×2矩阵独立实现 K 与 EMA、RW，再独立取窗/分位/损失。不可调用产品 `_update`、prior、q、loss helper。计划预先列出普通有限轨迹、长度、种子及源价量化规则；`abs=2e−11,rel=2e−10` 仅用于该固定正常集合。不要在测试失败后放宽或换样本。
2. **表示值与时间另轨。** 段索引、资格、reason、计数、同环境 prior/前序摘要用精确比较；float临界布尔用独立直接误差比较，不用高精度结果或数值容差吞掉翻转。保留034的 `m=1,q=.75×2^-52,y=1+2^-52` 上界舍入反例。
3. **边界。** 长度20/21/22/81/82；j82当前冲击不入自身q；54个小误差/6个大误差、q相等和全零；当前D缺失/重复/坏价；reset前后恰60槽；D之后值改动；仅改变当前合法值且资格不变，prior/q/前序损失逐字段不变。
4. **状态失效。** j2及预热后发生float/log碰撞、之后超过60步仍关闭、既有坏组后恢复；正常相等源价不算碰撞；平方下溢/非有限、RMSE离窗恢复、一个模型损失失败不剔除共同槽。未定位与可靠未来日期分别检验。
5. **原样兼容。** 在改代码前冻结旧 `signal_report` 完整规范JSON/golden，覆盖正常、常数、跳变、重复、未定位、明确冲突/隔离、低Decimal context、数值reset和价格展示失败。修改后逐字/逐字段全等；启用诊断前后再运行旧报告也相等。比较 `_update` 原签名和旧 monkeypatch失败用例；旧API envelope/analysis_id不变。
6. **真实Store边界的合成测试。** 经正常decoder→临时Store分别获取 public query 与 OHLC projection，新报告完整相等；输入、源字节、query/export及旧报告未变。新纯函数不复制原件核验；调用者仍每次按既有Store路径读取。
7. **实际回归。** 新专属＋旧 signal/series、research adversarial、projection、API的受影响集合全部跑；最终固定版本再跑仓库全套并分报失败/跳过。未改Web不以未跑UI认定本纯函数失败，亦不授予UI、Windows或真正预测效果资格。

测试与oracle的新文件名、夹具集合和运行命令由作者写入计划。独立实现审查仍必需；本文件没有把未来用例算成已通过。

### FD-06：同工资源比较，编码阻断

034的20k新增计算≤100ms必须解释为**匹配共同工作后的诊断增量**，不能写成整个新入口总耗时。已有记录中20k单股含规范化/完整报告公式约0.5秒。新入口省略 event_study与完整series，若直接和完整 `signal_report` 比速度，会把省去的工作拿来掩盖诊断开销。

冻结如下有界实验，待033窗口正式释放后协调运行：

- 固定5k/20k输入，A、B使用相同Store读取/原件核验、归一化、私有causal iterator与消费策略；A drain既有row，B开启capture并执行collector。两边都不持有T条输出，或两边都持有，不能混用。
- 每组各预热一次，然后5对交错；记录每对A/B/Δ、中位和范围。20k诊断新增公式成本每对Δ≤100ms；端到端每对 `Tnew<=1.10*Tbase+100ms`。不以5次给p95、不删除“不好看”的正常运行。
- 独立进程的相同基线/新路径峰值RSS对比，新增≤8MiB；完整新结果规范JSON≤32KiB，包括≤60条证据与来源摘要。峰值测量说明输入/初始化归属，不把生命周期RSS差直接称纯函数净分配。
- 归一化一次、同一核心状态递推一次；`_update`调用次数与基线一致。20,001源行在递推前拒绝。可用计数spy检验，不靠耗时推断。
- 纯计算ring额外内存O(60)、末窗排序O(60 log60)，整体仍有既有日线分组排序/原输入成本。不得宣称整个流程O(1)内存。逐时点评分属于独立验收脚本，不能每个截止重载原件/把每次O(T)报告循环成隐藏O(T²)性能结论。

若上限失败，先检查重复扫描、对象复制、每根排序；保留原证据并复审，不删除证据或绕原件核验。未测不等于通过。

### FD-07：固定真实窗口与解释基线，编码阻断

真实运行前先写冻结输入清单，含全部30成员、原实体/manifest、snapshot/query、源起点、截止、源码及脚本hash。复用已授权的原件和Store，不发新行情请求；原件和逐股价格结果继续留仓库外。

关键补足：[029](../research/029-automated-ashare-data.md)与现存真实验收证明每股原件有640条；484/478/475是2024-10-11起的报告目标视图。**本算法必须从实际冻结640条原件的起点向截止递推，目标日期仅作分报告，不得在2024-10-11重新初始化。** 每股具体起点由冻结原件确认，不能假设相同。

保留034预定矩阵，不因误差结果调整：

- 三个原10股组所有成员，D=2026-10-09；不只展示K优于RW的股票。
- 688981.SH：2025-09-05缺截止；2025-09-09复牌观察。
- 688012.SH：2025-12-31缺截止；2026-01-05复牌观察。
- 全30股按2025-03-31、06-30、09-30、12-31及2026-03-31、06-30、09-30分报告，区间内每步使用自身此前60误差。自然季度末没有源记录时保留缺失；不偷换最后交易日。

按同股同日期共同可评价槽，比较K/R/E点预测MAE、RMSE；范围比较包括K固定S尺度/K经验、R的EWMA pre/R经验及E经验。固定c=1.6448536269514722只是正态尺度参考。独立离线报告至少有上下侧/inside计数、平均宽度、连续越界和error-domain interval score；五种范围使用同一评分/缺失规则，失败保留在总体与对照缺失计数中。不在构造q的60条上报告“90%验证覆盖”。

季度/30股观察相关、成员按当前选择，真实矩阵已经在其它功能中使用过；它仅授予来源兼容与指定源版本的误差诊断。没有PIT、未见样本外和执行账本，不能形成alpha、经济收益、交易成功率或真正置信带。停牌旁注明确源观察的实际跨日，不把复牌误差写成一交易日预测。源复权/公司行动不明保持限制，不能按大残差自动剔除或reset。

若经验范围仅靠变宽取得更多inside，或相对EWMA无可解释新增信息，不进入UI；若点误差审计也不能改善固定核查任务，继续收窄。负结果必须保留，换W/p、损失、模型或日期均属于另一轮尝试。

## 5. 作者答复与解冻条件

请作者提交具体计划并逐项回应FD-01～FD-07：实际文件/函数、private prior生命周期、接口/字段/错误枚举、身份公式、常见与异常计数、oracle固定样本、旧golden产生方式、匹配A/B测量和640前缀真实矩阵。

解冻前需要明确删除首片events接口，并解决generator先更新后yield时前序摘要的实际保存顺序。计划中的每项应能对应一个具体测试，不以“遵循034”替代实施细节。作者答复后由本审查追加复核决定；本段首轮状态为**未获编码许可**，最新决定见§6。

本轮完成：静态核读、上述局部手算核对与本正式审查文档。实际产品测试通过数：无本轮执行；产品测试、真实误差、性能、浏览器、Windows、未见样本外/经济效果均未跑。没有产品或旧测试变更，没有提交或推送。


## 6. 作者逐项答复后的正式复核决定

2026-10-11 07:45 UTC。已实际核读作者的 [具体实施计划](../plans/2026-10-11-forecast-diagnostics.md) §1–11及FD-01～07逐项答复，并复查034同步修订。**限定设计通过，已知编码前设计阻断全部关闭。执行仍冻结。**

| 原阻断 | 已核实的具体关闭依据 |
|---|---|
| FD-01 | 计划§4明确私有generator、capture默认关闭、active时先于坏bar continue保存prior；consumer在next(D)之前冻结ring摘要。新增时序spy与collector异常外抛测试，不改旧_update标量次序/异常域。 |
| FD-02 | 计划§2–3固定同D/query选择身份、可信Store与现有helper；已删events、逐行schema/ordinal认证、值长度/指数新限制及猜测的batch check别名。未认证调整/日历仍可作条件源价诊断。 |
| FD-03 | 计划§5–6明确顶层资格、calculation_status、historical_availability及主失败优先级；模型未运行计数为null；坏组/精度后缀/预热/共同误差互斥。证据补足segment及origin_observations。 |
| FD-04 | 计划§5与§7按square→sum→mean→sqrt→difference检查，补上正sum除60下溢；字段依赖和坏平方出窗恢复明确，precision后缀仅随旧reset解除。 |
| FD-05 | 计划§7固定Z/C/T/A/J/P/V七条160槽生成式、8位源值量化、60位独立矩阵oracle及严格表示值轨；12个改前完整golden场景、旧源码hash/副本和最终回归顺序固定。 |
| FD-06 | 计划§9固定5k/20k同drain A/B、5对每对增量与总耗时、同消费峰值RSS和32KiB全响应；旧event/full-series工作不混入增量基线。 |
| FD-07 | 计划§8固定640原件前缀、全部30股、244个预定公共纯函数端点。全时点评价用产品私有状态流/collector单遍执行；保存产品e/q后独立核严格布尔，独立数值oracle另轨。高精度末位不覆盖产品inside。 |

这里接受新计划的紧凑source摘要与固定未核限制：source绑定batch/raw/contract/声明身份，详细源语义由同snapshot/query追溯；不要求再复制全部manifest或构建新认证框架。返回calculation_status不授予概率、PIT、经济收益或成功率资格。真实流使用产品私有helper不构成独立数值oracle，计划已把两类证据分开；244端点再核公共纯函数与流结果的一致性。

复核版本（包含作者07:45追加的执行冻结声明，07:46复核）：

- 计划 SHA-256：`eef3798b293e00ebbf767e45c350815049f40165e5a48ad1b834ac6068b57aa5`
- 034 SHA-256：`9cb12272999f9dec7f14e58e80f36cfd874a5187ce57fe308ae96cd2cb6ef363`
- signal、research_series、numeric的三份hash与§2一致；此时没有034产品/测试实现。

### 执行起点与仍未取得的资格

父任务07:44 UTC明确：033正式资源验收、109文件最终hash核对及发布/提交尚未结束。**即使本设计获批，034产品与测试文件仍不得先改，golden生成和任何产品测试/benchmark也不得先运行。必须等待父任务明确解除033发布冻结并指令启动下一片。** 不以08:07预计时刻到达代替解冻通知。

解冻后允许范围仅为计划列定的新纯函数、signal私有机械提取、新合成测试/golden与验收文档；先冻结旧源码/完整golden，再写异常与oracle，再做产品变更。若要改Store/API/UI、重写多个模型、增加事件入口或更改来源资格，应回到审查。若与033最终提交后的依赖版本发生实际差异，先核差异并更新基线，不能跳过改前golden。

本次决定完成的是编码前设计审查。产品实现、独立代码复核、全部新旧测试、244真实端点与全时点诊断、资源预算均未执行/未通过；UI、Windows、任务价值、未见样本外与经济效果也未取得。研究与计划通过不等于实现验收，更不等于K优于RW。


## 7. 首版实现独立审查与冻结决定

2026-10-11 08:27 UTC。父任务已于08:11明确解除033发布冻结并启动034，故§6的执行冻结为历史状态。本节实际审查 `forecast_diagnostics.py`、signal私有提取diff、作者测试/golden及本审查独立新增的 `tests/test_forecast_diagnostics_adversarial.py`。

**当前未发现遗留实现阻断。允许冻结下列版本，进入预定真实244端点/单遍诊断、资源和最终全仓回归。此决定只通过本节所列实现与focused范围，不代表新功能整体已验收。** 本审查不重复发网络请求、不运行作者负责的真实/资源实验。

### 7.1 已实际核验的实现边界

- `_Prior`为不可变NamedTuple；`_capture_prior`在当前close读取及坏bar分支前执行，并位于旧数值catch外。默认旧路径不分配prior。consumer先freeze D的ring，再调用next；当前实现没有`current_close-innovation`倒推。
- `_update`标量表达式与旧源码一致。新 `_causal_rows`替换旧append的位置只yield已有row/prior，旧 `_causal_series`收集原row；原事件计算、public字段和旧API身份未扩展。
- 新单D流程归一化一次、流遍历一次、D处freeze一次；collector是固定slots及maxlen=60 deque，不调用旧signal_report/event_report、不保存T条state或T个窗口。该结构检查不代替尚未运行的20k资源预算。
- 日期组坏/重复、旧数值reset与精度封段分开；j21仍属预测起点未成熟。精度碰撞从发生点阻断现有segment，超过60步也不自愈；真实旧reset之后才恢复。
- 损失逐模型保留同一60槽：一个模型平方/均方下溢或溢出不抹掉其它模型的q/MAE/RMSE；mean正→0与合法0分开，非有限内部误差抛出内部错误。展示端点溢出不改误差域position。
- `calculation_status`、来源解释边界和历史可得未核分列。已有源声明/未知调整照条件源价算术可用，未认证信息不变为PIT/概率/成功率。作者发现并补齐明确rounding限制 `display_endpoints_rounded_position_uses_residual_domain`，本审查接受且最终测试已包含。

### 7.2 独立对抗测试与旧golden追溯

独立新增 **45项**，首跑 **45 passed，0失败、0跳过，0.56秒**。未导入作者的fixture/oracle/helper作为参考，另写规范查询生成器、日期组和通用2×2矩阵对照。覆盖：

1. 200槽独立日期组/矩阵对照，坏点或重复位于j1、j21、j22、j61、j81、j82、j116的断链、前序窗口、共同计数；逆源顺序不改变日期组时钟。
2. close=1的20/21/22/81/82/83严格零与分母边界；current-close访问spy，证明capture早于当前值读取，即使当前bar无效；capture ArithmeticError向外传播，旧入口仍原样工作。
3. 500槽只有一次D摘要，ring始终≤60，禁止调用旧完整series/events；该用例只检验结构，不作为20k性能测量。
4. j2、j21、j22、j81、j82、j100精度碰撞后缀与旧坏价reset恢复；单模型loss失效、正均方下溢、sum溢出、非有限内部输入、单侧展示端点溢出。
5. 独立误差域interval-score手算与舍入端点反例。当前产品没有IS接口，该测试只核固定验收公式和position，不假称真实逐步评分已验。
6. source-only/declared/声称known_at仍未升级资格；实际合成decoder→Store两版可靠未来价修订时，固定D完整数值结果相等而analysis/source身份改变。追加无法定位未来行则降低整体资格，不能用前缀数值不变掩盖新未知覆盖。public query与OHLC projection一致，查询不变。

改前证明另做独立只读回放：`signal_research.before.py` SHA为原`8b0d041a…f55c2`，与当前HEAD改前文件逐字一致；核读冻结脚本的编辑前hash断言、12场景、锁版本和manifest。未运行冻结脚本重新生成期望。独立加载旧副本，逐场景重放12份完整报告，均与封存JSON完全相等；当前实现同样12份全等，另核12份旧API完整result与analysis_id。低Decimal context、单次_update失败、第60次price-scale失败均独立重建注入。源副本存在不只是作者声明，已实际核hash与重放。

### 7.3 最终focused运行与版本

实际命令：

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_forecast_diagnostics.py tests/test_forecast_diagnostics_adversarial.py \
  tests/test_signal_research.py tests/test_research_series.py tests/test_event_study.py \
  tests/test_research_api.py tests/test_research_projection.py tests/test_research_adversarial.py
```

结果：**369 passed，0失败、0跳过，12.99秒**。其中作者当前194、新增独立45、既有相关130；45及作者此前各次运行已包含于369，不能累计为更多独立测试。最终源码与测试hash：

| 文件 | SHA-256 |
|---|---|
| `src/anatrading/forecast_diagnostics.py` | `e5239afb87aba79de46bf5cf1db1bc7fe748f389e1234031c2261b60510804f7` |
| `src/anatrading/signal_research.py` | `ad6a6f6849970f2d6f6c9079566b31d2ddd5a4045e6c6a05924d9b1e5fee7a11` |
| `tests/test_forecast_diagnostics.py` | `78deddd4dc8dfffc94a9f4c9c1943883bb78ee50a145ba5760e87e3ff6ce7c27` |
| `tests/test_forecast_diagnostics_adversarial.py` | `b90b480b70add835a94f76cb2a726d64f4bad76ededb75710de52cccf4621329` |
| `tests/fixtures/forecast_diagnostics_legacy.json` | `bd68f0583a5441930bdfa47dafe23bf6b9a0fb8fc332227f77fda802fa007eb4` |

私有日志与可复算脚本位于仓库外 `anatrading-forecast-diagnostics-2026-10-11/`：`reviewer-first.log`、`reviewer-focused.log`、`reviewer_replay_legacy.py`、`reviewer-legacy-replay.json`，另有作者封存的legacy输入/manifest/旧源码。`git diff --check`通过。独立测试只使用合成数据，本审查没有把真实原件或价格复制入仓库，也未改作者产品/测试。

### 7.4 后续门槛与未完成项

- 待真实固定30股、244端点及产品同float残差域单遍结果，并保留全部缺失/失败、独立数值oracle和已知停牌旁注。
- 待5k/20k匹配drain A/B、每对新增≤100ms/端到端、峰值RSS及完整输出≤32KiB实测；任何超限按原合同处理，不以本次focused绿灯放宽。
- 待最终固定版本全仓Python回归、汇总、独立复核结果与提交核验；源码或测试若随后改变，相关验收必须在最后版本重跑。
- 未运行本片浏览器、Windows、用户任务价值、真正未见样本外或经济效果。纯函数没有新增UI/API，不能借旧界面/旧来源通过来替代这些资格。


## 8. 最终原始证据复核与有限合并决定

2026-10-11 08:51 UTC。本节覆盖§7.4的后续阶段，保留原时点记录。审查直接核读全仓日志、真实清单/运行脚本/结果、时延原始ns与两轮RSS原始stdout，独立重算保存值和hash；**没有重复运行全仓、真实状态递推或资源实验，也没有新增网络请求。** 产品与测试保持§7.3冻结版本，终审又逐个核过112份Python、54份web、合成fixture及两份锁文件，共169份，全部一致。

### 8.1 分层结论

| 验收层 | 最终决定及范围 |
|---|---|
| 实现、因果性、数值边界、旧public/API兼容 | 通过§7限定范围。独立45项、联合369项与改前12份完整golden证据有效；无已知遗留实现缺陷。后续没有产品/测试漂移。 |
| 最终固定版本回归 | Python **2540通过、49跳过、0失败**；Node **128通过、0失败/跳过**；TypeScript/Vite构建通过、52模块。已核原日志hash、运行前后169文件hash；本审查未重跑。49项skip继续未验，既有弃用、bundle及npm环境告警保留。 |
| 真实来源读取兼容与指定版本误差诊断 | 通过固定30股、完整640源前缀、243唯一端点/244用途及产品float单遍对账。只对冻结版本和明确窗口有效；未知来源语义/历史可得时点不升级。 |
| 时延、完整响应和执行次数 | 通过预注册5k/20k、匹配drain与全部五对规则，详见§8.3。不能据有限样本宣称稳定p95或性能提升。 |
| 新增内存≤8MiB | **未验/inconclusive。** 两轮均无法识别诊断阶段增量，脚本布尔不构成通过；也没有证据证明产品超限。FD-06完整资源门槛保持开放。 |
| 预测或经济增量 | 未取得。目标视图30/30成员K的MAE、RMSE均劣于RW；三组RW经验范围平均IS也略劣于EWMA。无概率、PIT、交易成功率或alpha资格。 |

### 8.2 真实原始证据独立核对及负结果

核对仓库外真实目录 `anatrading-market-samples/forecast-diagnostics-validation-2026-10-11/` 的冻结manifest、预注册脚本和 `final-run/` 原件。审查另存只读核对程序 `reviewer_terminal_evidence.py` 与结果 `reviewer-terminal-real.json` 于合成验收目录，不导入产品或重开Store：

- 核 **554份**交付产物hash；核243份公开响应的规范JSON摘要、来源边界和历史可得未核标识。241份实际D的完整result（不含查询覆盖摘要）与单遍保存端点逐字典相等。243唯一请求为241 computed、2 unavailable；映回预注册244用途为241/3，未回退缺失D。
- 读取全部30份产品float压缩轨迹，共 **19,200源槽**：630 warming_up、1,800 history_insufficient、16,770 computed。每股640从原件起点运行，目标前4,695槽没有丢弃；14,505槽属于固定两年目标视图。实际起点差异与停牌跨度均保留。
- 对五种范围共 **83,850个保存评分**，从已保存的产品误差/半宽独立重算严格position和interval score。另从保存误差重算全部30股目标视图损失和三组共同日期范围汇总。该复算检验评分消费端，不冒充独立滤波oracle；60位矩阵轨是另外的数值证据。
- 核40原件/40完整查询、ledger及既有冻结证据前后不变；运行记录839次Store查询、972次纯调用。脚本及结果证明public/compact、重复和重开后倒序请求一致。source价格、原单位、snapshot/query/batch/contract身份未被诊断改写。
- 高精度轨最大记录绝对差 `4.665324894532422e-15` 只作为本真实样本观察值；预定监控阈值未触发，不把合成数值保证外推至所有真实/极端输入。严格布尔继续以产品float残差域为准。

**独立确认：2024-10-11～2026-10-09目标视图的30/30成员，K一步MAE和RMSE均高于RW，均低于滞后EMA。** 三组共同日期的RW经验范围平均宽度低于RW-EWMA，但平均IS依次为银行 `0.058818209812290786 > 0.05801918609651599`、白酒 `0.092284105361369 > 0.09090549239014681`、STAR混合业务 `0.14990440954049794 > 0.1482311234012089`。共同日期分别484、484、469，不将跨股/跨日重叠观察当独立样本。

因此本片的真实产出是可核查的误差审计及负结果。不得将K相对EMA较好、K经验范围相对固定S较好、q范围较窄或局部inside更多，包装为K优于RW或经验范围全面提升。固定所有窗口和失败项保留，不追加W/p搜索、择股或日期筛选；本片不据q扩张页面、选股或自动模型切换。用户任务价值、长跨度价值及真正未见样本外效果仍需新问题/新数据另审。

### 8.3 原时延有效，RSS两轮均不可判

原资源组08:39:24～08:40:07 UTC运行。本审查从原始ns独立核全部20对，并核完整响应长度/hash、次数spy和预注册源文件一致。20k公式五对B−A为 `66.621096 / 35.077170 / 16.055187 / 9.034701 / 52.554644 ms`，逐对均≤100ms；5k公式五对同样通过。5k和20k端到端全部逐对满足 `B≤1.10A+100ms`，保留负增量与波动，不删异常对。全响应分别21,498B、21,688B，均≤32KiB。归一化/coverage/iterator、D冻结、原件核验与source SELECT次数符合计划；20,001行在状态递推前拒绝。

原RSS四进程的输入/预热/最终共12个 `ru_maxrss` 都是730,677,248B，无法识别匹配诊断增量。原JSON的差0/通过布尔已由独立复核降为inconclusive；`resource-review.json`保留此解释，原结果不删除、不覆盖。

负责人随后只批准一次RSS测量器纠正。本审查在执行前静态核过v2脚本及freeze：相同输入/原operation/消费、固定四新进程、当前地址空间VmHWM主口径、ru_maxrss对照、所有phase记录、不重置高水位、不重跑时延。08:47:43～08:47:48运行后又逐份核stdout/phase和所有产物hash：

| 行数 | A输入后=最终VmHWM（B） | B输入后=最终VmHWM（B） | 最终B−A（B） |
|---|---:|---:|---:|
| 5,000 | 165,253,120 | 163,983,360 | −1,269,760 |
| 20,000 | 316,071,936 | 315,994,112 | −77,824 |

四个当前地址空间测量都被自身输入准备高峰遮蔽。观测差虽小于8MiB，无法据此推断诊断新增内存为零/负值/≤8MiB；warm与final的VmRSS记录也不能替代全过程增量峰值。**第二轮最终仍为inconclusive，停止复测，不调阈值、不选run、不更换输入追绿。** O(60) ring与无全series的结构证据保留，但不代替实测预算。有限时延和JSON验收不依赖此失效的RSS资格。

### 8.4 工程建议、负责人决定与开放项

独立工程建议：可以把现有功能作为**独立调用的纯诊断能力有限合并**。依据是严格单D/20k入口、共享旧递推且完整旧输出兼容、固定有界collector、充分因果/异常/数值证据、无API/UI或默认服务入口，以及真实负结果可复算。这里没有授予原计划全部验收通过，也不承诺现有内存预算。

**2026-10-11 08:50 UTC，集成负责人明确接受开放RSS预算项并批准上述有限合并方向。** 这是对当前合并范围的工程决定，与“8MiB门槛仍未验”分开记录。未来接入服务前，须另行审定能识别输入准备与计算阶段峰值的匹配资源实验；当前未授权为追绿继续补测。若产品、状态生命周期、数据入口或默认调用关系改变，重新评估受影响验收。

仍未取得：8MiB增量预算、49个既有skip覆盖、Windows原生、本片浏览器/用户试点、任务价值、PIT、源复权/日历/公司行动认证、真正未见样本外及交易效果。现有未知信息保持未知。真实源价与私有证据继续留仓库外；审查没有提交/推送/合并，发布状态须由集成负责人对实际提交另核。

### 8.5 最终证据定位

产品与测试hash沿用§7.3，未改变。详细资格记录见[正式验收文档](../qualification/forecast-diagnostics.md)。以下hash已直接核验，原始逐点价格与报告不入仓库：

| 仓库外证据 | SHA-256 |
|---|---|
| `anatrading-forecast-diagnostics-2026-10-11/final-full-checkpoint.json` | `a5e4d10b7c8a89819553b815c9bdca325976ea5acd4556772600b6a37e85a742` |
| 真实目录 `final-run/results.json` | `959232df5eca298884f989ee704c51361fbe3d9bb45c37ab08ef394a99f6d62e` |
| 真实目录 `final-run/report.md` | `9c14ceabb522ef13d9ac28a48bd0e33c86576ea7cdbb88c6baa1a12e69207618` |
| 合成目录 `performance/results-run-01/results.json` | `8cba4b4beae925e9d1a3d44ced8996d1a4b68e7b88c0d287329230f194438130` |
| 合成目录 `performance/rss_correction_v2.py` | `df1cee4d95eab747aadf4fc0f25371e828433064d57aaf097f5e64e12c376e03` |
| 合成目录 `performance/rss-v2-freeze-final.json` | `bbef07d9987344750bcb22d7730fae2f5d4921a2540b776ba4ac53d005ad89fb` |
| 合成目录 `performance/rss-v2-results-01/results.json` | `d908d521099cc3da222d89c60edd83e14082748e34376eab4cf12fbe5eefa45a` |

本节终态：**限定工程合并ready；FD-06完整资源资格未ready；预测增量未取得。** 不以合并决定改写测试、样本、来源或统计资格。
