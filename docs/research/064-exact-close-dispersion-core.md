# 064 最小精确收盘离散核心：编码前冻结设计 v2

2026-10-13，针对 main `84179960272ffbe0c8589efeb89513c89e85ac3f`（PR58 已合并）。编码前原稿冻结于仓库外；本文为公开副本；无产品代码、API、UI 或依赖改动。独立反方已给出设计 GO；通过设计不等于产品验收。

## 1. 范围和资格决定

只增加单一 Python 纯模块 `close_dispersion.py` 和对应测试、研究/评审记录。固定当前及前19个来源日期组、收盘价水平、总体方差、均值±2σ。无调参、收益模型、percent-b、带宽比、排序、交易指示、概率/95%覆盖、去噪或预测结论。无 HTTP 路由、Store 调用、市场数据、浏览器或 UI。

明确选择现有 `research_series.daily_bars` 严格正价资格，不改该模块：四个 OHLC 都必须满足 >0 且形态有效，沿用来源代码/复权冲突、隔离来源、重复日期和无定位错误。零价在此适配器为 `invalid_price`；即使只使用 close，坏 open/high/low 仍使整个日期组无效。交易量/金额失败不额外阻止价格描述。

数学核心单独接受非负 Decimal(38,18) 格点，包括0。通道/几何允许零价的既有合同及测试不变。零数学通过不得计为本适配器零价通过；选择严格正价是为了最小复用已有来源核验，而非证明零价算术无效。未来需要与通道零价域统一时，须单独研究和复核新来源适配器，不偷偷放宽 daily_bars。

## 2. 纯函数边界与来源身份

建议两个入口：`exact_window(closes)` 仅20个源值；`dispersion_report(query)` 接收已由现有可信查询路径取得的冻结完整日线前缀。核心不接收 Store 路径，不获取数据，不导入 Store/HTTP，也不将任意字典的自报 ID 当作来源真实性证明。

报告入口做最小形状/身份检查，参照 `swing_event_information._request` 的既有模式但不调用其事件参数：query 为 dict，selection/metadata/manifest 为 dict，rows/unlocated 为 list 或 tuple；snapshot_id/batch_id/query_id、manifest.raw_sha256/source_contract_id 为非空字符串；selection.mode 为 retrospective；period 为1d；完整来源行数<=20,000；拒绝 ordinal_start/end。非空 cutoff 使用 strict_date。复用 symbol_identity，保留来源/声明身份资格，不猜股票代码或交易所。该函数只验证声明一致性，不能证明标的类型、历史可得性或闭合。

报告显式带出上述来源引用、symbol_identity 结果及 manifest qualification；固定 `method_id=source-close-dispersion20-population-v1`、`adapter_id=daily-bars-strict-positive-v1`、`numeric_policy_id=integer-moments-isqrt36-v1`。不新增 Store `_identity` 导入或通用哈希层：此切片输出完整身份对象，未来 API 若需要 analysis_id 则沿用其既有身份封装并另行验收。

本设计只消费单一来源查询，不接受另一份 context，因此不存在跨 snapshot 合并。身份引用变化必须体现在报告身份；统计值相同不表示数据版本相同。不同 cutoff/query_id 的完整报告不要求相等；逐前缀不变性比较共同日期的数值、局部窗口和无效原因。

## 3. 来源位置、坏窗与窗口身份

复用 daily_bars 的升序不同可读日期组作为位置0..n-1。可从原始 token 找到日期而 label 无效者保留位置、原因 unlocated_label；重复日期占一个无效组。日期完全不可读者无法分配位置，daily_coverage 原样披露；日历上完全缺失的日期不虚构。coverage_known 只保留既有含义，不能升级为交易日历完整。

输出 series 每个日期组保留 `position,date,ordinal,close,source_reason`；重复组 ordinal 保持 null，所有原始重复行仍由 query_id 指向源查询，不编造唯一序号。每行窗口字段为 `window_start_position=max(0,i-19),window_end_position=i,window_count=min(i+1,20)`；完整成员可由 series 的连续位置片段重建，无须在每行重复20份成员。

状态固定优先级：不足20为 unavailable/history_insufficient；已有20但任意成员 source_reason 非空为 unavailable/invalid_window，按升序列出 invalid_members 的 position/date/ordinal/reason；否则 computed。无效时全部数学结果为 null，不复用旧窗。当前坏行同样进入坏窗，不压缩/填补/跳过。索引25坏时25..44无效，45恢复。首19窗不计算，即使存在坏成员仍保留 source_reason 及 invalid_members。

无日期行保留独立的 coverage 披露，不在 series 插入猜测位置；它们使报告 qualification 为 source_coverage_unknown，但不伪造某个具体坏窗。隔离来源 source_rejection 优先决定报告 source_rejected，所有既有日期组保持既有坏原因。其他报告 qualification 复用 signal_report 的条件来源口径。

## 4. 精确源数与整数矩

exact_window 只接收 list/tuple，先验证长度恰为20再解析任何成员；错误容器/长度统一 invalid_window_length。随后用 numeric.decimal_value 完成既有类型/有限性/尺度/范围校验：bool、float、NaN/Infinity、超范围/超尺度值拒绝。非负检查独立。对规范化 Decimal.as_tuple 的 digits/exponent 构造整数系数 c，u=c*10**(exponent+18)，零单独为0；从不在默认 Decimal 上下文执行 x*10**18，也不转换float。合法非零 exponent>=-18，整数位数<=20。

n=20，M=10**38-1，0<=u<=M；每窗重算 S=sum(u)、Q=sum(u*u)、D=20*Q-S*S。D<0 为内部失败，绝不钳0。固定20，无滚动加减状态，无漂移。

精确输出：
- `sum_u`、`sum_squares_u`、`dispersion_numerator` 为整数字符串。
- `mean_exact` = 5*S * 10**-20。
- `variance_exact` = 25*D * 10**-40。

使用有符号整数的 sign、绝对值digits、指数来构造 Decimal 元组，再复用 numeric.decimal_text；绝不对 Decimal 使用可能受调用上下文影响的一元负号或其他中间运算。禁止通过源值 decimal_value 重验派生值（均值可能20位小数，方差可能40位小数）。以上表示都精确且与调用方 Decimal 上下文无关。

S<20*10**38；Q<20*10**76；S²与20Q<400*10**76<2**262，核心矩的所有中间整数<=262位。更紧的 D 上界可用 D<=100*M²，但不依赖紧界实现。均值在[0,M/10**18]，σ<=M/(2*10**18)，方差<=M²/(4*10**36)；派生下界>=-M/10**18，上界<=2*M/10**18。负下界合法，绝不截0。

## 5. 数值输出选择：精确矩 + 有证明的平方根区间

比较：
1. float64两遍方差：已被源格点碰撞否定，不选。
2. Decimal 64位 sqrt + 组合运算：很短且可复用本地 Context 风格，但 sqrt 不能简单按 FLOOR/CEILING 分别调用就声称定向边界；还需处理每次舍入及抵消，单独 value 不能证明显示正确。
3. 只给 sqrt(D)/(20e18) 符号式：最少算术，但无法直接供后续显示。
4. 固定格点整数 isqrt 包络：选择。仅增加一个标准库函数及整数运算，不依赖 Decimal sqrt/浮点/全局上下文。输出直接沿用既有 true_range 的区间一致才显示语义，不提供无证明单点 estimate。

冻结 sigma 区间格点为10**-36（20点非恒定格点的最小σ=√19/(20×10**18)，约2.18e-19，仍有充分分辨率，不以4位显示代替内部值）。令 N=25*D*10**32，则 σ*10**36=sqrt(N)。a=isqrt(N)，b=a 当 a*a==N，否则 a+1。

m36=5*S*10**16（均值恰在10**-36格点）。输出：
- sigma lower=a/10**36，upper=b/10**36；
- envelope_lower lower=(m36-2*b)/10**36，upper=(m36-2*a)/10**36；
- envelope_upper lower=(m36+2*a)/10**36，upper=(m36+2*b)/10**36。

均为闭包络，端点仍用 Decimal 元组与 decimal_text 精确渲染；端点相等标记 exact=true，否则 false。sigma宽度最多1e-36，两条边界各最多2e-36；这是数值误差界，绝非概率区间。常量D=0时完全相等；负端点原样保留。

262位仅指精确矩。新增缩放平方根 N<2**373，a*a 与 (a+1)**2 也<2**373；这是显示包络额外中间量的独立保守界，不把整个实现称为262位。至多113位十进制整数，可用已有128位私有 Decimal Context 安全做最后4位显示；不改 numeric.py 的全局合同。

每个区间都有 display（固定4位小数）及 display_reason：在独立 Context(prec=128, rounding=ROUND_HALF_EVEN) 下分别 quantize 两个精确端点到0.0001；先比较 Decimal 数值相等性（不以带正负零的字符串作判定），相等则给该4位字符串，不等给null/ambiguous_display_rounding。显示负零统一为0.0000；精确负数端点不改。均值/方差始终给完整精确文本，不强制4位。近零σ可能显示0.0000，但其精确非零区间仍保留，不将显示值反写为数学零。

## 6. 编码前验收矩阵（固定，不按结果改门槛）

A. 历史证据账本保持分层：原四个冻结精确源案例为1/1.000000000000000001、1e19/(1e19+1)、1e-18/2e-18各交替20点，以及99/101/十八100；constant100是协议后附加例。独立零修正另列五例与五次案例通过，不说五次运行。旧正价 JS 审计中零拒绝错误原样保留，不替代当前资格。

B. 核心每例对 Fraction(原始精确字符串) 的中心化总体方差/均值逐项全等；D同时对190对差平方和全等。覆盖上述四例、constant100、零修正五例、最大格点常量/相邻值、十九1加100、线性趋势、水平跳变；结果不合并成独立市场样本。

C. 平方根 oracle 不复用产品 isqrt：测试用独立整数二分平方根或 Fraction 平方不等式证明 a²<=N<(a+1)²，并核对 exact 标志；每条派生端点再用精确 Fraction 推导验证。覆盖 D=0、完美平方、非平方、最大离散、极小格点和负下界。专门核对±半个4位显示单位及其两侧，端点跨舍入边界必须返回 ambiguous，负零按规定显示。数字类型不得出现float；序列化往返完全保留文本。

D. 源解析与适配器分开测：恶意调用方低prec、ROUND_DOWN、不同traps/Emin/Emax仍给同样核心结果；20值限制先于算术；错误价格类型/超范围/超尺度/非有限值拒绝。数学零可算；daily_bars全零/任一零OHLC无效；通道原零资格回归保持。

E. 合成可信查询字典（不打开任何Store）：定位错误、重复日期、不可读日期、代码/复权冲突、隔离、volume/amount坏、cutoff、非日线、窗口裁剪和20,001来源行边界；身份字段缺失/冲突拒绝。验证不修改输入；不得把来源声明当作原字节重新核验。

F. 因果性：对每个前缀重新算，同一日期局部输出等于完整序列对应行；追加/修改仅未来日期不影响既有窗；打乱输入物理行顺序只保留同一日期排序结果。改变历史重复/源值允许改变相应窗口，必须变化的query身份由可信查询层提供。

G. 最终实现提交必须重跑新增测试及受影响 numeric/research_series/price_channel/candle_geometry/true_range/signal_research 测试；环境就绪后完整仓库检查另列。当前禁止任何Store运行，故现有含Store集成的测试暂不在本切片运行；完整产品测试需要家长明确解除该执行范围再另行运行。公开研究记录需在编码前增加本设计及独立反方回复，不回写旧实验协议。

## 7. 当前环境与实施门槛

只读检查时间2026-10-13 20:49 UTC：干净 main如上；无 .venv、无 web/node_modules；PATH默认 Python3.12.14（不满足>=3.14,<3.15），无 python3.14；Node24.19.0/npm11.9.0符合README。默认Python环境缺duckdb/pyarrow/pytest，fastapi0.141.1和uvicorn0.52.1不等于锁定版本，httpx0.28.1已存在；绝不视为项目已就绪。

后续支持路径按README：官方Python3.14.0，创建隔离.venv，`python -m pip install -c requirements-workbench.lock -e '.[dev]'`；若要完整前端检查，用现有web/package-lock.json执行npm ci，无自行升级。本设计任务未安装。另有同环境恢复任务时以其最终实测为准，不覆盖其目录或环境。

20:51 UTC 环境恢复补记：并行环境任务报告现有锁约束安装已完成，仓库.venv为Python3.14.0，pip check通过；相关纯数值/来源测试199通过、7项Store相关测试deselected，git保持干净。本设计未安装。该报告来自环境任务，不冒充本设计独立运行；接下来可用恢复解释器执行设计算术核验。

下一门槛依次为：独立反方审查本冻结合同（尤其严格正价取舍、373位显示中间量、身份信任与坏窗）；答复并冻结修订；纯模块及合成测试实现；限定测试验收；经授权恢复集成检查范围后执行全套，再决定是否需要API。此设计不依赖旧虚拟环境、私有行情、网络抓取或UI，因此环境依赖就绪后具备最小实施可行性，尚无产品运行/耗时/真实兼容证明。

已做：只读源码与公开协议核读、依赖版本探查、设计。未做：产品测试、实验重跑、Store、真实行情、浏览器、Windows原生、性能和金融验收。没有接触受禁的市场数据库。

## 8. 新设计微验证（与历史实验分开）

20:52 UTC，在本文件已写明公式后创建并运行仓库外设计微验证脚本 `design-oracle.py` 一次，Python3.14.0、仅标准库、无仓库模块导入。17个合成窗口逐项通过中心化Fraction均值/方差、190对差、独立二分平方根、精确平方包络及核心/显示位数界检查；6项4位half-even、跨舍入边界、负零显示检查通过。实测最大核心矩262位、最大缩放根被开方数371位；合同仍保留373位保守上界。结果记录为仓库外 `design-oracle-results.json`；该设计阶段脚本不作为本仓库产品可复现验收入口，产品独立参考见 `tests/test_close_dispersion.py`。这不是产品解析/适配器/逐前缀测试，也不是旧063脚本重跑，不改变历史四例+一附加例和另行五例零修正账本。

## 9. 独立反方结论与冻结

2026-10-13 20:52 UTC，独立 reviewer 检查源码、设计和oracle后给出 GO，无设计阻断。其发现与落实：
- 最小非零σ不能写成5e-19；已修正为√19/(20e18)，并在新设计oracle中保留十九0加1格点反例。
- 派生数构造显式用整数sign/digits的Decimal元组，避免一元负号受调用上下文影响。
- display相等以量化后Decimal数值比较，并规范负零。
- 20点长度必须先于源成员解析检查；本v2限定list/tuple，不接任意无限迭代器。
- 来源引用始终是既有可信查询的身份声明，不能当作独立认证。

v2冻结后才进入产品编码。v1保留为审查工作稿；design-oracle和其结果为单独设计微验证，后续产品实现必须独立验证这些合同，不能以设计GO替代实现验收。

## 10. 实施回归范围

完整回归可使用测试中新建的临时纯合成Store夹具；真实/历史Store、原始行情和捕获文件不在执行范围。不寻找或恢复缺失私有夹具，缺样本明确跳过。先静态检查测试路径，再运行允许集合。第6节G的临时全Store排除由本节更窄的回归范围替代。

## 11. 实际最小输出形状

实现入口为 `anatrading.close_dispersion.exact_window` / `dispersion_report`。报告 `identity` 完整带出 snapshot_id、batch_id、query_id、raw_sha256、source_contract_id、selection、symbol_identity 和 source_qualification（原 manifest qualification）。复制可变身份数据，结果编辑不修改输入。method_id、adapter_id、numeric_policy_id、parameters、coverage、qualification、units、limitations 位于顶层。

`series` 直接包含第3节位置/窗口/源状态字段和第4、5节八项数学结果。不可算时八项均为 null。区间的字段为 lower、upper、exact、display、display_reason。核心错误长度为 invalid_window_length，源数沿用 NumericError，负源价为 negative_price；不把内部负D失败静默转成零。

旧模块、API、UI、依赖、旧报告身份及导出格式没有修改。逐窗只重算固定20项。设计冻结时尚未测量运行成本；实现后的两项另行冻结资源观测见[验收记录](../qualification/064-exact-close-dispersion-core.md)，其较大输出成本阻止未经预算审核直接接入API/UI。后续接入和真实来源资格需单独验收。
