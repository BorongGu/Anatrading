# 固定双股映射的后段误差核对：单对离线合同

日期：2026-10-11。状态：**10:20 UTC设计冻结；11:38 root另行批准实施，纯函数及回归已完成，原反方未发现实现阻断。资源§7的一次35调用协议及独立终核已通过，唯一REAL01及保存输出的最终独立核查已通过，允许范围限于离线来源描述。** 研究与逐项答复见[036](../research/036-pair-relationship-stability.md)，复审决定见[独立审查](../reviews/2026-10-11-pair-stability-review.md)。本计划只定义一个纯函数及有限离线验收；不改Store、旧pair/universe/peer、034/035、来源协议、HTTP/UI或依赖。

## 1. 最小任务与固定版本

建议签名 `pair_fixed_change_report(left_query, right_query, *, fit_end, evaluation_cutoff)`。输入只读，返回JSON-compatible结果；函数不做文件/数据库/网络/时钟/环境变量访问。真实加载由既有Store完成。

固定 method_id=`pair-fixed-source-change-audit-v1`，rule_version=`pair-fixed-source-change-eligibility-v1`，变换=`simple_source_relative_change`，训练60、后段20，Y=left/A，X=right/B。首稿log任务被替换；新beta与旧log-return beta不是同定义。不能输入可调窗口、损失选择器、正则、截尾或阈值。

F、P/M/U、MSE/MAE与差的精确公式以036 §6为准。MSE是固定主损失，MAE是始终返回的敏感性明细。只拒 `Sxx=0`；非零的小范围如实返回，不授予信息充分或未来稳定资格。P需要同期X，`information_timing=contemporaneous_source_endpoints`；`mode=retrospective`；结果不能作预测、因果归因或经济套利描述。

## 2. 精确算术域、静态整数界与有界展示

### 2.1 权威层次

1. 原价：既有 `decimal_value` 接受的**严格正 DECIMAL(38,18)**，不改变原token。直接复用030的`_price`和`_endpoint`已审域及预检，不新增数值输入框架；bool/float不作为价格输入。
2. 数学：以原价的精确Fraction计算所有比值、均值、OLS、映射、误差、MSE/MAE、差。零方差和差符号由该层决定，等于没有epsilon。
3. 展示：所有派生标量是 `{display: string, sign: -1|0|1}`。display为12有效数字、ROUND_HALF_EVEN、规范科学计数，零固定`0`；sign由精确Fraction给出。绝不按两个已舍入display相减判输赢。源close仍使用≤39字符的规范十进制和≤128字符原token，不套派生格式。

RMSE、相关系数、训练残差尺度、均值/RMS分解和p值删除。内部精确分数不默认导出，不能调用`str()`转换长分子/分母，也不设置`sys.set_int_max_str_digits`。

### 2.2 固定60/20的保守整数上界

以下是静态推导，尚未经实现资源实验。令每个合法close为 `a/10^18`，其中整数 `1≤a<10^38`；每个简单变化约分后的分子绝对值、分母均 `<10^38`。

- 训练120个x/y变化分母之积记D，则 `D<10^4560`。令整数 `Xi=D*x_i,Yi=D*y_i`，有 `|Xi|,|Yi|<10^4598`。
- `Sx=sum Xi,Sy=sum Yi` 的绝对值 `<10^4600`。令 `Q=60*sum Xi²−Sx²`、`K=60*sum XiYi−Sx*Sy`，有 `0≤Q<10^9200, |K|<10^9200`。Q=0正好对应Sxx=0。
- 非退化时 `beta=K/Q`，`alpha=(Sy*Q−K*Sx)/(60*D*Q)`。alpha分子绝对值 `<10^13801`，分母 `<10^13762`。
- 后段40个x/y分母之积记V，`V<10^1520`。取公共分母 `H=60*D*Q*V<10^15282`，三个模型每个误差可写成 `E_kj/H`，`|E_kj|<10^15322`。这个界包含无同伴均值和直接同伴基线。
- 因而MSE及其差可用公共分母 `20*H²<10^30566`；三项MSE分子 `<10^30646`，两项差分子绝对值 `<10^30647`。MAE及差分母 `<10^15284`，分子绝对值 `<10^15325`。约分只会减小界。

所以所有返回派生标量的规范Fraction分子/分母最多30,647十进制位，保守取 **110,000 bits**。按先约分的Fraction逐步计算，二元加减的交叉乘法、乘除的临时整数可取 **220,000 bits** 保守界。实现不得用不约分的20项分母连乘累加来突破这一界。该推导只用于固定输入域与固定步数，不是任意长度的有理数平台；超出界属于实现不变量失败，应停止并修复，不能动态放宽支持域。

普通实现可以采用中心化Fraction公式，不必为运行构造D/V/H；上述共同分母只用于证明位数上限。测试需要独立记录关键阶段的实际bit长度，检查最大支持域/互异分母路径，不用结果输出巨长精确分数。

### 2.3 只用标准Decimal生成有界展示

从Fraction的整数n、d直接构造`Decimal(n)`、`Decimal(d)`，不先转str；在新建独立Context的localcontext内直接做一次除法，再用`.11e`规范科学计数格式。Context固定prec=12、rounding=ROUND_HALF_EVEN、Emin=-40000、Emax=40000、capitals=0、clamp=0、flags清空；九项traps全部显式设置：InvalidOperation/DivisionByZero/Overflow/Underflow/Subnormal/Clamped/FloatOperation开启，Rounded/Inexact关闭以允许预期显示舍入。不得继承外部或DefaultContext的精度、指数界、traps和flags，退出不得改变外部context。零专门显示`0`，非零指数绝对值小于30,648，完全落在正常域内。

[Python 3.14 Decimal官方文档](https://docs.python.org/3.14/library/decimal.html#decimal.Decimal)的Quick-start、Decimal构造、Contexts和scientific格式段落明确：int构造精确，context精度不截断构造值，算术/格式按上下文舍入。本次只读文档核对，未执行运行实验；不需要自己实现bitlen估指数格式器，也不调整Python整数转字符串限制。内部最多30,647位的整数转换成本计入资源测量，最终只输出已舍入的短Decimal。

规范display如`-1.23456789012e+12345`，最多21字符，非零不会显示0。一次12位除法后`.11e`只补齐12位有效数字，不再次降低精度；禁止先用80位近似再判精确中点。sign仍来自Fraction。独立格式oracle使用整数pow/divmod和half-even余数比较，并覆盖中点两侧、进位和±10^-6000，不调用同一Decimal除法生成期望。

## 3. 直接复用既有来源边界，删除新增资格框架

本片**没有descriptor、events或新的行schema/check/token深度/长度验证器**。签名只接两个完整query及两个日期。来源规则以030已审实现为准，不复制另一套认证逻辑：

1. 两源原始行数各≤20,000、合计≤40,000先预检，然后各调用一次既有 `peer_relative_research._source`。它已检查完整Store/现有OHLC projection、retrospective且无cutoff/ordinal裁剪、必要字段/计数/身份、腾讯strict/legacy日线未复权请求，以及已知全局反证；原样复用其ValueError，不修改helper。两股规范身份或snapshot相同另拒绝。
2. 每源再扫描一次rows/unlocated，用既有 `_position` 归组可靠日期，构造并集。label/token冲突或不能可靠定位的行使本次完整比较 `position_integrity_unknown`；token可靠但label不合格仍占坏槽。来源检查和日期分组最多两遍**全源扫描**，不含下面有界所选槽处理。
3. 只对固定最多81个日期槽调用已有 `_endpoint`；所选候选的 `_row_conflict/_checks` 及已审分类常量用于局部资格。重复/缺端点保持失败，不取末条；唯一所选端点核OHLC和源token，最多162个。多候选重复槽无需计算价格，保留候选总数、前三ordinal和未列数。
4. 路径外不另扫描/重算局部价格，不生成外部异常列表或新schema。无定位行保守关闭比较；可靠路径内局部来源冲突、未知fail关闭所用端点及相邻区间；量额失败/source_order行级披露遵守原helper分类，不升级价格资格。

可复用 `_source/_position/_endpoint/_row_conflict/_checks/_price` 及其现行分类常量，不调用030四成员公开报告、不伪造成员、不抽通用校验平台。固定依赖测试及旧golden检测helper语义变化。两次全源扫描后只选择固定槽；允许复用既有助手对端点作有界重复读取，不宣称所有内部字段只访问一次。精确Fraction至多计算160个区间变化，不为全源拟合逐日模型。

原件认证仍由Store每次加载完成；纯函数信任未改写Store输入，query_id或自填verified不额外认证数据。原helper当前限腾讯strict/legacy、SH/SZ、未复权请求；其未知/反证边界不提升。**本片不凭新声明授予A股/CNY、复权、日历、闭合或PIT资格。** 这是带既有来源限制的价格值映射，不扩大国际异步市场。

**删除首版事件过滤承诺。** 停牌/公司行动不新增产品输入或自动过滤层；已知公告只在离线验收旁注中记录。单侧真实缺日由并集/缺端点规则自然阻断；若停牌仍有源OHLC，产品只能做有条件来源算术，不能凭值存在认证可交易。公司行动覆盖始终unknown，任何误差都不能解释为经济关系破裂。若问题需要按行动调整或排除停牌报价，应停止本片并另补数据任务，不能偷偷加events分支。

## 4. 固定网格、局部失败与状态

fit_end/evaluation_cutoff必须严格ISO且`fit_end<evaluation_cutoff`。fit_end不在可靠并集时`anchor_missing`，不回退，`grid_defined=false`，观察/合格数为null，trace/rows为空，planned仍60/20。fit_end存在而某侧端点不合格为`anchor_invalid`，可确定日期槽仍保留。

令fit_end=d0；F为其此前恰60区间、61槽，E为随后在evaluation_cutoff内恰20区间；合计最多81位置。坏槽不删除、不扩窗凑满；E超过d20不纳入。单侧缺dj阻断进出该槽的j/j+1两区间。共同缺日仍不能由并集发现，calendar=unknown。

`evaluation.eligible`仅计已观察E区间中**两侧四端点及局部来源资格全部合格**的数量，独立于F是否可拟合，不是损失汇总分母；网格未定义则null。F完整且E恰20/20合格才形成比较；不能用19个合格区间作完整块。可靠位于E内的局部异常不撤销已合格F；共享d0坏则同时影响F及第一E。无法定位或全局来源反证不属于E局部异常，可按既有规则使全调用失格。

结构/全局错误直接保留已审helper的ValueError；新增仅`invalid_dates,research_row_limit,research_duplicate_symbol,research_duplicate_snapshot`。无任意数据回显，无新验证调度器。结构合法的局部原因按固定顺序：`position_integrity_unknown,anchor_missing,anchor_invalid,history_insufficient,local_source_conflict,unclassified_source_failure,duplicate_endpoint,unlocated_endpoint,missing_endpoint,endpoint_price_check_failed,missing_ohlc,invalid_price,invalid_ohlc,constant_training_x,evaluation_incomplete`；沿用endpoint原原因，必要时合并去重。没有新事件原因。

fit.status仅`ready,constant_x,unavailable`；evaluation.status仅`not_located,pending,invalid,complete`：

| 情况 | 固定结果 |
|---|---|
| 无法定义锚点网格 | evaluation=not_located、fit=unavailable，汇总全null |
| F不足或来源/端点失格 | fit=unavailable，全部P/M/U解释、误差及汇总null；E仍可列独立合格x/y事实和eligible数，不另取A的干净训练估M |
| F全合格，仅Sxx=0 | fit=constant_x，my和Sxx保留，alpha/beta=null；完整E时只保留M/U损失，P和相对差null |
| E数量不足20，已有区间全合格 | evaluation=pending，区块汇总全null；F不受影响，已有行可解释 |
| E任何已观察区间失格，或无定位行影响比较 | evaluation=invalid，所有完整区块汇总null；已合格F在纯E局部错误时仍保留；也不足20则一并保留evaluation_incomplete |
| E恰20且全合格 | evaluation=complete；是否有P/基线汇总再取决于fit资格 |

顶层status优先级：fit不可用或evaluation为invalid/not_located→`unavailable`；E pending→`incomplete`；F constant_x且E complete→`baseline_only`；F ready且E complete→`source_description_complete`。禁止stable/reliable/broken字段。未知价格经济语义永远不会被`source_description_complete`升级。

## 5. 固定报告、身份与输出上限

最小顶层键：`method_id,rule_version,analysis_id,parameters,sources,status,reasons,fit,evaluation,trace,limitations`。

- parameters固定fit_end/evaluation_cutoff、60/20、变换、Y/X方向、主MSE/敏感性MAE、12位half-even格式、information_timing与mode。
- sources：两侧role/symbol/snapshot/batch/query、原来源qualification/strict-or-legacy标识，行数及来源日期/无定位计数；不复制整manifest/tokens/原件。
- fit：status，planned_intervals=60、observed_intervals（网格未知为null）、start/end，mx/my/alpha/beta/Sxx的有界标量，x_range={min,max,constant}。F完整时这些数学值可得，Sxx=0只关闭alpha/beta。失败时不拟合任何部分。
- trace：最多81个不同日期位置，每侧有candidate_count、最多按ordinal升序的前3个候选ordinal、omitted_candidates和有界原因；唯一候选时可保留close_token/close_exact。相同端点只列一次，不为20个区间重复复制源价格。所有来源定位用snapshot/batch/ordinal，不伪造projection缺失的locator。
- evaluation：status、planned=20、observed/eligible、实际start/end；主`mse={P,M,U,delta_PM,delta_PU}`；固定明细`mae`同结构；x_range同fit，并有`outside_fit_range_count`（严格超min/max，constant时亦适用；失败不能用好样本计总体）。已有行最多20，每行是index/start/end、reasons、x/y、P/M/U、eP/eM/eU、squared_delta_PM/PU、absolute_delta_PM/PU，标量都采用§2格式。未观察日期不生成虚构行。
- limitations固定：economic_return=false,total_return=false,prediction=false,causal_attribution=false,stability_certified=false,historical_availability=unverified,calendar=unknown,closure=unknown,corporate_action_coverage=unknown,adjustment=request_declared_semantics_unverified,current_selection_retrospective=true。不增加声明来改变这些值。

analysis_id为canonical JSON SHA256，绑定method/rule/parameters和**按left/right角色顺序**的symbol/snapshot/query引用。公开/内部projection共享输入身份；可靠未来纯数值不变性只针对固定过去数值，新版本ID可以改变。不得为了生成analysis_id重新序列化全部源行。

canonical UTF-8报告 **≤262,144 bytes**，包括完整20行；派生scalar最多21字符display及小sign，trace≤81×2侧×3候选，只复制必要来源ID与有限枚举原因，不复制metadata/manifest/窗外异常详情。不得默默裁掉主行/原因让体积通过；超过界是合同实现失败，停下修复。精确分数长整数既不进入JSON，也不写日志。

用户文字唯一比较语义为“此固定区块MSE/MAE较高/相同/较低”；sign=0才等于。MSE/MAE反向必须保留；X后段常数或范围外观察只能提示信息背景。不给“旧关系可以继续用”、结构破坏原因或发生时间。

## 6. 先固定的正确性与旧输出验收（未执行）

### 6.1 独立精确oracle

审核者自行从源字符串与label/token建并集、资格与81槽，独立将Decimal拆成整数/10幂，不能调用新产品/旧daily_bars/作者fixture生成期望。参考OLS用两列设计矩阵的**非中心化精确正规方程** `beta=(nΣxy−ΣxΣy)/(nΣx²−(Σx)²)`、`alpha=(Σy−betaΣx)/n`；产品可用中心化Fraction。输出/差/展示均独立重算。

精确oracle无需容差。格式oracle采用整数比值的十进制指数范围、pow/divmod余数及half-even判定；手算中点两侧和进位另验。不得调用产品格式助手或同一路Decimal除法作期望；sign直接比较独立Fraction。

验收入口固定为**实际生产使用的私有精确算术核**：它返回Fraction供唯一格式层消费；独立测试用自己从原串/网格得到的非中心化公式结果逐项比较该核的精确值。公开报告再逐项核display、sign、位置和失败状态。12位JSON展示本身不能证明内部精确一致；不为测试新增第二套产品计算器、公开长分数或专用原值导出接口。

固定矩阵：

| ID | 预注册构造 | 验收目标 |
|---|---|---|
| S01 | 036 §7.1的100/101/102→100.5有限十进制源 | mx/my/alpha/beta、三MSE及两差逐项等于文中精确分数；两时期高相关不认证稳定 |
| S02 | 同一F，E保持原100/101/102交替 | P完美、训练零残差不阻断；损失差全保留 |
| S03 | 理想变化层F y=2x，E y=1.8x，x交替±1/100 | P能赢但不能输出稳定；与源级fixture分开报告 |
| S04 | F的X恒定；另测Y恒定；E的X分别零/非零常数 | P退化与基线保留按合同；非零常数亦无斜率信息 |
| S05 | 理想核层P误差=[1,1,10]+17个0，M误差=[2,2,2]+17个0；U由同期x独立决定 | MSE_P=102/20 >12/20，MAE_P=12/20 >6/20；单点主导须可逐行复核，不自动删点 |
| S06 | 理想核层P误差=[0,0,10]+17个0，M误差=[4,4,4]+17个0；U由同期x独立决定 | MSE_P=5 >2.4，MAE_P=.5 <.6，两种固定损失反向 |
| S07 | 精确真相等、差±1/10^6000、half-even中点、进位；合法close极近18位差 | sign精确，不受科学展示相等/float下溢或全局int-string限制影响 |
| S08 | 单侧删除d5、d5重复、d0缺失、label/token冲突、停牌缺日、停牌端点有OHLC及未知公司行动旁注 | 缺d5使第5/6区间失败；有源OHLC不能获可交易资格；没有events输入或事件过滤承诺；完整分母不变 |
| S09 | E分别0/1/19/20/21个源槽，cutoff固定；修改d1/d0/d20/d21 | 成熟、共享边界、相邻变化依赖和可靠未来数值边界全部正确 |
| S10 | 全局身份/调整/隔离、既有源范围反证、所选槽未知fail/未知位置、只有量额失败 | 结构拒绝与局部空值符合既有helper及§4；不新增窗外异常摘要；unknown不能变资格 |
| S11 | 角色交换、逐股正比例缩放仍在合法域、不同Decimal context、输入不变 | 新模型重新拟合，数学相等为精确Fraction相等，不复用旧log beta |
| S12 | 2×20k行、最大重复/所选槽失败、超过限额、互异大分母算术 | 先预检，选窗后才精确算术，位数/JSON/候选省略计数符合固定界 |

S05—07是核心得失/展示反例；不能把任意误差向量冒称源级OLS可实现。来源端到端对照至少S01、S02、S08—12；来源路径用例另经合成strict/legacy捕获→decoder→临时Store读取公开与OHLC projection，两者整个报告一致。随机游走/共趋势只验无协整/稳定/套利字段，不要求随机每段P输。

### 6.2 旧golden与回归

批准编码后、改任何产品前，冻结旧输出到仓库外验收目录，记录源码hash及canonical JSON hash；**现在没有生成golden或跑测试**。旧pair源SHA `a08cc8e64918639b44ec17e6a92e697d935c2229753560a3d44ea207c1ff85ba`，peer源SHA `a4c71f78d17a027c1f51f2fa70a503b0877743f2709473b23c64299a6966f577`，numeric源SHA `a7c66d7c609e771aa8ab43a124aec418bea6261aa7ae6feb50a169627d10b58a`。若基线被其他获准任务改变，先记录并独立审查影响，不默默刷新golden。

旧pair固定数据日期为2026-01-01起自然日标签（明确合成），lookback=5：G01 A=[10,11,9,12,13,19],B=[20,21,23,22,26,24]；G02同G01但仅A删第3日期；G03同G01但A重复第3日期；G04 A=[1,4,9,16,25,36],B=[1,2,3,4,5,6]；G05 A=[10,11,9,12,13,19],B=[2,2,2,2,2,2]；G06交换G01角色。前后完整输出与固定错误行为必须一致，不允许借新任务更正旧模块。

受影响回归固定包括旧pair/universe/peer_relative/research_series/research_projection/numeric/source_formats测试与新片两套独立测试；若最终获准发布，还须root安排现行全仓检查。数量只计实际跑到的集合，不能相加重复子集。此计划不修改034/035测试或成果结论。

## 7. 资源验收的固定矩阵与预算（测前冻结；结果见§11）

**2026-10-11测前准入修正，经原反方脚本静审后冻结执行。** 原冻结计划SHA `25378d47248da620fe1e1f1ff20153e92c572788d751adc3c13ac1cfb19462b9`及全文副本保留。原文把四种5k/20k配置同时用于纯函数A与Store完整B；静态核读发现腾讯`build_request`仅允许count≤640、请求跨度≤366天，`validate_capture`拒payload>count。B无法合法导入5k/20k，不绕decoder或伪造Store。以下在**未取得任何性能结果前**撤回不可达B规模，A压力域与所有既定门槛不变。此修订不能解释为5k/20k完整加载已验收。

以下性能数均为测前冻结的工程停止门槛；执行结果另列§11，不根据结果反推门槛。在当前Linux Python3.14锁定环境运行，源码/依赖/输入前后hash一致，不并行真实效果或其它benchmark。

- **A四配置，预构造合成Store形状DTO，只验纯函数+canonical JSON消费：** R05N=两侧各5k正常行；R20N=各20k正常；R20A=各20k行分布在81个日期槽、重复标签与固定`invalid-price` OHLC token/None值及既有numeric失败，所有候选在所选范围内，预期不可比较；重复槽先拒绝，不声称该配置重算了唯一端点价格；R20Q=各20k行，固定81槽使用边界DECIMAL和互异分母，其余常数100。5k/20k DTO是支持域压力构造，不声称可由当前腾讯capture合法取得或通过真实Store来源认证。
- **B三配置，真实合成capture→decoder→临时Store，计两次完整公开Store query/原件核验+函数+JSON：** B640N/B640Q每侧640个连续自然日标签，请求仅末366日、count=640，最后81槽全部在请求范围内。前274条早于请求起点，保留并披露现有metadata的`before_start_count=274,in_request_count=366,request_range_mismatch=true`；腾讯解码器没有为这些行添加`source_date_range`检查，不能虚构。B640Q在末81槽采用同一数值压力构造。B640A每侧640行分布81日，重复标签与`invalid-price` OHLC token由真实decoder产生既有numeric失败/None值，请求覆盖该81日；缺少可用拟合是合法结果。B不注入伪造来源检查，不修改输入合同或Store。

固定数值构造：按升序扫描整数[10^37+1,10^37+100000]，只保留与所有已保留整数gcd=1的候选，取前158个；不足即fixture准备blocked，不扩大扫描范围。每侧81个close的整数a在第0槽为1、第1槽为10^38−1，余79槽分别用列表偶数/奇数位置，除10^18形成合法close。无筛大素数、新依赖或网络，生成在计时之外；它是固定压力样本，未穷尽数学最坏路径，静态界仍见§2。

每个配置固定1次预热、3次计时，记录全部值及中位数，不丢任何一次。只在这次预热里，用有限wrapper观察实际生产`_bounded`的规范Fraction位数、B的`_verify_raw`次数及原件digest读取字节；必须调用原函数、try/finally还原且报告字节不变。三次正式计时不用wrapper；220k临时整数界只作静态证明，不假称实测。逻辑query为B每次2个；不把逻辑调用或readinto次数写成操作系统物理read次数。

计时采用perf_counter。输入构造/导入不计A，输入导入不计B；B必须计完整加载和原件核验。预算不变：A中位数R05N≤2秒、R20N≤5秒、R20A/R20Q≤10秒；B每配置中位数≤30秒；每次JSON≤256KiB。A另在独立新进程、输入已构造后启动tracemalloc，函数+序列化新增Python分配峰值≤32MiB，整个进程VmHWM≤256MiB；B完整调用新进程VmHWM≤512MiB。每配置内存只测1次；计时与内存不混跑。整进程峰值含解释器、依赖及输入构造；不能把高水位差0写成新增占用0，不能将Python分配当完整RSS，缺读数记未验。

固定matrix_id=`pair-stability-036-A4-B640-7cell-v1`。总量修订为 **7配置×(1预热+3计时)=28次调用，另7次新进程内存调用**。每股每次最多1个逻辑Store query，纯函数无I/O。仪器只占既有预热，不另加模型调用；测量器、fixture与hash先经独立静态审查，再由root批准CPU窗口执行。原始文件/依赖改变或并行干扰使测量无效时，先说明并停止，不在同窗口反复重试择优。

任一位数、体积、时间或内存门槛不达，冻结失败并停后续真实阶段。只能另提局部精简实现的修订评审；不得换参数/数据/门槛重新定义通过，不建立缓存、队列或配对平台。

## 8. 单一真实预注册与五个用户问题（结果见§11；用户任务未验）

### 8.1 唯一真实来源案例

只使用既有选择版本 `anatrading-two-sector-pilot-2026-10-11` 的bank成员，按规范symbol字典序取前两只；第一只Y、第二只X。固定fit_end=2026-06-30、evaluation_cutoff=2026-07-31、60/20，现有未复权请求与原snapshot不换。角色与日期已在036首稿写下，本次不因变换改选择。

| ID | 固定输入/操作 | 成功或停止标准 |
|---|---|---|
| REAL01-P | 从既有选择记录确认两股，绑定snapshot/query/raw hash和私有验收清单版本，写私有manifest；先于任何本片变化/误差计算 | 缺记录/版本即blocked，不换股票。manifest及原件不提交仓库 |
| REAL01-Q | 每股公开完整query与OHLC projection各1次，共4个逻辑query；完整Store原件核验，不改源值 | 公开/投影报告完整一致；缺锚点/F/E资格即保留unavailable并结束，不改日期补样本 |
| REAL01-O | 独立读取两份原始响应各1次，自行建日期/token网格；最多81日期×2股=162个唯一端点与最多160个变化逐项重算 | 精确值、差sign、格式、覆盖与全部失败一致；P赢/输/等于都可通过正确性 |

该矩阵只执行一次。若Store加载技术错误先报告，不把其它来源/新采集当替代；任何重试需root确认其为同一固定动作与技术原因。加载取得完整query时允许先抽取header冻结身份，但在manifest写入核验前不计算/展示OHLC变化，不让结果反过来选择成员。

这是**已见来源兼容/算术核对**；当前成员选择、复权/公司行动/PIT未知均保留。没有统计或交易增量成功指标，不将30只历史样本当独立未见留出，也不基于结果新建监控。真实阶段不得与本片资源测量并发。

用户随后要求扩大行业数据，优先级已上升；新数据不自动替换这里冻结的成员/来源，也不自动成为未见检验。若后续改用新数据，先另行修订预注册并复核，当前真实阶段保持未启动。

### 8.2 五个固定用户问题

仅当用户愿意参与，按匿名合成报告作答；未参与标未验，不让助手代替用户“答对”。每题0/1，是否给出所需关键答案记录，不报告统计显著改善。

| 题 | 展示材料与问题 | 允许的正确答案 |
|---|---|---|
| U1 | S01：两段相关都高，冻结映射在E是否比两个简单基线少出错？ | 两个MSE差都正，P在这段更差；高相关不能覆盖旧映射误差 |
| U2 | S04：E中X为同一非零值、误差很小，能说斜率稳定吗？ | 不能；后段没有X变化来辨别斜率，低误差不给未来许可 |
| U3 | S05：平均平方误差差异主要来自哪里？ | 指向误差10的那一行，保留其原值；一次冲击主导不自动等于持久变化 |
| U4 | S08：一侧缺d5，应能否用其余18区间形成完整比较？ | 不能；说明第5/6区间阻断、固定20分母，报告不可比较 |
| U5 | 一个大来源跳变且公司行动覆盖unknown，能否称经济关系破裂？ | 不能；原因未知，须核源调整/行动/修订等证据，不能做因果归因 |

先旧页再新报告的同人顺序有提示/学习效应，只能记个案可用性；若做严谨比较需另行冻结平衡顺序和任务设计。本片不自动扩大这项评估。

## 9. 10:20设计冻结时的状态与审批边界（历史）

本次只修订036并新增本计划，未改源码、tests或034/035；未生成golden、跑合成产品测试、真实误差或资源测量，未提交。文档校验通过，原反方10:20 UTC复审关闭R1—R4，设计已冻结。

2026-10-11 10:12用户要求优先扩充行业数据。本片当前只收口最小设计复审；**即使原审查者关闭R1—R4，也不启动test-first、golden、产品或真实/资源执行**。后续须由root结合数据任务另行明确启动。若届时获准，才可开始一个纯函数及两套独立测试；算术/网格/旧golden通过后方可按固定资源与真实次序验收。任何阶段失败按对应停止规则保留原结果。用户任务无增量则停离线；未知与低误差均不授予未来沿用许可，不扩大UI/筛选/提醒/配对排名。

## 10. 启动与首轮回归时记录（历史；不覆盖设计冻结历史）

2026-10-11 11:38 root另行批准test-first/golden后实施。原设计冻结研究SHA `0843a174998b69b8f63511db4517cd2c5b7d5667f8b66f7ed0dee2571dd36016`、计划SHA见§7，原反方核实此前只改状态/链接。产品入口存在前，两套测试各有缺入口ModuleNotFoundError/Exit2日志，作者与反方分别保存六个完整旧pair golden；后续逐字一致。只新增一个纯函数及两套测试，未改旧模块、旧tests、HTTP/UI或依赖。

S05/S06最初的`U=M`是假想误差向量冗余，不能同时由该固定映射实现；现撤回该假设，冻结P/M主反例不变，实际核输入的U由x决定。没有按U=M宣称验收，也未新增第二产品计算器。资源§7则按静态准入边界作测前修正，等待脚本复审与root执行授权。真实单例保持§8原选样，未运行；扩展120只不加入本片。

## 11. 一次资源与唯一REAL01运行后的状态

资源按本节测前修订版本（执行时计划SHA `a29ee7e26f151f74fc1fce000d158b2ca03f9501dea9868f29e18514ac1e9d9a`、脚本SHA `cad23d983e2288b8e40b454d369bac6be836621b817be8221b5da6939294b60b`）于12:09:55—12:12:19 UTC执行，35/35固定调用全部硬门槛通过，原反方独立核对原始记录通过。未重跑、删慢次或改门槛。A为大输入合成DTO；B仅合法640行完整公开query，不能改称5k/20k真实Store已验。A整进程VmHWM最大232.613MiB、新增Python分配11.593MiB；B整进程最大210.555MiB；最大JSON61,302字节。规范Fraction观察最大53,603bits，220k临时界仍只有静态证明。逐格时间、范围错配、字节及测量口径见[资格记录](../qualification/pair-stability.md)。

资源过后root另批唯一REAL01，原成员Y=002142.SZ/X=600000.SH、原30股库来源、60/20与6月30日/7月31日参数保持不变；4逻辑query/3纯函数调用及保存输出的最终独立核查已通过。实际F=03-31至06-30，60区间/61槽；E=(06-30,07-28]，20/20合格；请求cutoff=07-31，固定前20区间不扩展到cutoff。P在这个后段的MSE和MAE都低于M、高于U；不能改映射/配对/窗口追胜，也不能据单例认证稳定、经济意义或预测。新120只仍独立备案。五个题仅有自动语义反例和可读字段，human utility未验。

源码与两套测试保持实测版本，完整Python2741通过/49跳过、Node128通过、TS/Vite通过；受影响724/10是子集，不重复计数。Windows原生、浏览器、用户判断增量与经济/未来有效性均未验。此后仅补状态和资格记录，不改数学合同；对外发布由root最后冻结安排。
