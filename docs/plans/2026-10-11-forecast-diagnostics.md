# 单步源价格预测误差：最小纯函数实施合同候选

日期：2026-10-11。现行状态：**设计、独立实现及终态复核已完成；负责人接受开放RSS项并批准纯诊断的分层有限合并。RSS≤8MiB预算仍未验，FD-06不记全部通过。** 当前结果见[验收记录](../qualification/forecast-diagnostics.md)及本文§12。以下合同保留设计时的候选表述，不将历史冻结当成仍禁止编码。 方法研究见 [034](../research/034-causal-signal-diagnostics.md)；正式反方决定由 `docs/reviews/2026-10-11-forecast-diagnostics-review.md` 记录。本计划冻结具体接口/身份/异常/范围；冲突由正式审查逐项解决，不由实现者临时选取。

**历史执行冻结（07:45 UTC，08:11 UTC由集成负责人明确解除并启动本片）：即使设计审查接受，也须保持产品与tests不变，等待集成负责人明确解除033发布冻结并启动本片。** CPU资源结束时间不自动解除发布冻结；033仍需核对源码hash、报告和提交，提前新增测试或改signal会污染其最终checkpoint。本文只准备合同，不授权提前生成golden、跑产品或编写测试。

## 1. 唯一切片及文件范围

解决一个问题：同一截止的当前源价一步误差，相对严格前序60个共同误差有多大；现有Kalman在那些同一观察上，与沿用上价、滞后EMA的MAE/RMSE有何差异。

- 新增 `src/anatrading/forecast_diagnostics.py`，纯函数 `forecast_diagnostic_report(query, *, cutoff)`。
- 对 `src/anatrading/signal_research.py` 作最小私有状态迭代/capture提取；原 `_update` 运算次序、参数、`_causal_series` 和 `signal_report` 公共输出/身份保持兼容。
- 新增作者测试 `tests/test_forecast_diagnostics.py`；反方独立测试另存 `tests/test_forecast_diagnostics_adversarial.py`，独立参考不得导入产品计算辅助函数。
- 仅合成旧完整输出可存 `tests/fixtures/forecast_diagnostics_legacy.json`；生成说明/hash放验收文档，真实行情不写入此fixture。
- 更新034/本计划/正式评审及新增 `docs/qualification/forecast-diagnostics.md` 验收记录。其余文件不因本片顺带修改。
- 不改Store、HTTP/API、React、事件研究、pair/universe、033优化、采集、依赖或公开导出；无分钟、跨股评分、CUSUM/BOCPD、自动切模型、实时预警、参数搜索。

首片**没有events/descriptor输入**。已知停牌/公司行动证据保留在授权真实验收旁注；结果常驻日历、公司行动与可得时点未核限制，不宣称自动识别。没有事件入口不授予经济解释资格；将来若需产品传入负证据，另审schema/时点/作用域。此收窄避免照搬030的组descriptor。

## 2. 输入、截止与可信边界

### 2.1 一个Store前缀，一个D

签名只接 `query` 和必填 `cutoff`，无默认窗口/分位覆盖参数。cutoff为严格10字符ISO日，使用现有 `strict_date` 并额外限制长度；拒绝None/bool/宽松补零/时间戳。

query是**同一个D的完整来源前缀**，来自既有 `Store.query(snapshot_id,cutoff=D)` 或 `_research_query(snapshot_id,cutoff=D)`。必需顶层字段为 `snapshot_id,batch_id,query_id,selection,manifest,metadata,rows,unlocated,counts,batch_checks`。允许公开查询已有的 `quality,unlocated_quality,totals` 或内部 `read_projection='daily_ohlc_input_v1'`，不能把任意新投影当作完整前缀。只读输入，无原地pop/排序/修复。

selection沿Store既有键：`snapshot_id,mode,cutoff,ordinal_start,ordinal_end,fields,versions`。

- `selection.cutoff == cutoff` **必须成立**。缺失、None、更早或更晚均为 `research_cutoff_mismatch`；不自行裁切一个别的query_id再冒充同D查询。
- mode必须retrospective；ordinal_start/end必须None，禁止图窗重热。fields须为Store完整 `open,high,low,close,volume,amount` 序列，内部OHLC投影也保留该完整公开query选择身份。
- selection.snapshot_id与顶层相同，versions与manifest.versions相同；按现有 `_identity(selection)` 校验query_id。此哈希只识别选择条件，不认证行载荷真实。
- 只接明确 `metadata.period='1d'`；证券身份使用既有 `symbol_identity(query)`，保留source_claim/declared级别。规范市场映射不认证品类、币种、历史永久证券身份或交易日历。
- 两种Store读取形状应生成同一诊断数值和analysis_id。`read_projection`、quality/totals等未使用的附加呈现字段不进入新身份。

`snapshot_id,batch_id,query_id,manifest.raw_sha256,manifest.source_contract_id` 必须为64位小写十六进制；只核格式和上述直接对应，不重算整条batch/snapshot/原件哈希链。纯函数不读磁盘。真实调用者仍须经过Store每次原件核验，不能用本函数替代；构造一致但虚假的query不在真实性保证内。

### 2.2 行预算和最小形状

rows/unlocated必须list或tuple，源行合计≤20,000；先检查容器/长度和预算，再归一化或递推，不接无限迭代器。空前缀合法，后续返回缺D。selection/manifest/metadata/counts为dict，batch_checks为list或tuple；需要被本片使用的来源ID、manifest.versions与选择字段存在。`counts.batch_unlocated_rows`须为非负真int，拒bool；其余计数直接由现有coverage产生，不再重建Store计数认证。

行、tokens/values/checks的结构继续处于可信Store及显式合成夹具边界。**删除首版计划的逐行ordinal唯一集合、全checks结构复核、128字符/Decimal指数新上限和batch计数相等新验证。** 不替代Store解码/持久化验证，不给任意外部JSON可靠接入的保证。已有缺OHLC、非法日期、重复日期及不合格数值由 `daily_bars`/`decimal_value` 保留原失败语义；不改写输入以绕开既有normalizer。源价范围仍为既有DECIMAL(38,18)，数量/金额不参与价格资格。

已知位置晚于D的有效行不应由同D Store查询返回；构造测试不允许借伪query_id扩大结果身份。数值前缀验收应采用新来源版本、同D重新查询，或私有迭代器的独立前缀测试，不要求伪造相同ID的载荷也通过身份认证。

## 3. 预检与全局失败

按正常验证流程fail-fast，结构错误不承诺任意重排仍选同一错误。稳定 `ValueError(code)` 不回显原价/长输入；未知程序异常不得catch成普通不可评价。

| 条件 | 处理 |
|---|---|
| query/必要顶层容器、来源ID或直接对应错误 | 整调用 `invalid_forecast_query`；未知投影同此；不进入模型 |
| cutoff格式错误 | 整调用 `invalid_cutoff` |
| query截止不等于D | 整调用 `research_cutoff_mismatch` |
| 非retrospective、fields/versions选择不合格 | 整调用 `invalid_forecast_selection` |
| ordinal裁剪 | 整调用 `ordinal_window_not_supported` |
| 输入行数>20,000 | 整调用 `research_row_limit`，归一化/状态调用0次 |
| 非1d | 整调用 `unsupported_period` |
| `symbol_identity`不可用/冲突/市场未知 | 原样 `research_identity_unavailable / research_identity_conflict / research_market_unknown`，不返回猜测身份 |
| `source_rejection`识别quarantine/known_negative_sample失败 | 返回unavailable/known_negative_source；保留source/coverage，关闭主诊断，不运行模型 |

不增加batch身份/调整check名称白名单。现有 `source_rejection`只消费metadata.quarantined和batch的known_negative_sample失败；`symbol_identity`检查metadata来源/声明冲突；`daily_bars`经 `_source_conflict`消费行code/adjustflag与metadata的冲突及行check的source_code、source_adjustflag/source_adjustment失败。只复用这些实际存在的边界，不宣称其它任意同名/别名检查已自动接入。

metadata/manifest语义在快照可信边界内按原样追溯，未知复权/known_at/closed不关闭条件性源价计算；也不会因数值算出而升级。未支持的外部事件声明不能暗中注入本函数。

## 4. 私有状态捕获：不从当前残差倒推预测

### 4.1 建议最小实现结构

将现有循环提为私有 `_causal_rows(bars, *, capture_prior=False)`，逐行yield `(row, prior_or_none)`；旧 `_causal_series(bars)` 收集row并返回与旧版完全相同的list。旧 `signal_report` 仍调用 `_causal_series`，无新公开字段。若实现提出更小而同等可审的私有sink方案，须反方事先同意，不能扩为通用callback框架。

新纯函数：一次 `daily_bars` → 一次 `daily_coverage`（传已建bars）→ 一次私有状态遍历 → 只保留O(60)误差ring与当前D输出。不得调用 `signal_report` 把event_study和全历史series再算一份，不得累计T条prior或每根复制60窗。

捕获位置必须在当前y被转换/吸收、`_update`/EMA/EWMA更新之前，且在本轮 `bar.reason` 失败分支的continue之前，直接读取旧局部变量。仅在active且capture开启时创建新flow需要的独立有限记录：

```text
origin_date, origin_ordinal, origin_observations
model_segment_id
mK = level + slope
mR = previous_y
mE = ema
S = (p00 + 2*p01 + p11 + Q_level) + R
v_pre = variance_post
```

所有表达式遵守原标量运算次序；这不是第二套滤波。不要从 `log(current_close)-innovation`、当前filtered状态、当前EMA或EWMA post倒推。原前一series记录只用于独立核对capture，不作为“当时已保存”的证据。

第一条及旧reset之后尚无active状态时prior为None。把当前合法价改为非法价，可以令该步公开诊断关闭并令旧模型照原规则reset，但私有generator仍须交出此前active状态的相同prior；测试直接观察这个私有时序，不新增无效价的公开预测。generator不引用ring，不计算q/MAE/RMSE。

当前观察照原算法更新后，在旧异常catch之外yield结果；诊断消费者才评价当前误差/资格和更新ring。**新collector的异常不得进入现有 `(ArithmeticError,OverflowError,ValueError)` catch被误当价格失败并悄悄重置旧状态。** 不包围yield/外部consumer调用扩大旧catch范围；新capture若发生未预期内部不一致，应使新调用明确失败，不能影响旧入口。所有新计算默认关闭，旧路径不执行q/误差collector。

### 4.2 每一步的强顺序

1. consumer按已归一化bars的date元数据前行。在D那次 **`next(causal_iterator)`之前**，先从已有ring冻结q/MAE/RMSE/证据与不足状态；只读D标签，不读当前close数值。不能使用会先取generator值再进循环体的 `zip(bars,causal_iterator)` 来伪装这个顺序。
2. 随后调用next：私有generator从t−1局部状态保存prior，再读取当前合格close并执行原更新，最后yield `(row,prior)`。当前失败产生原row失败，不掩盖此前已保存prior。
3. consumer以当前观察计算e、精度碰撞、当前position；若当前资格失败，可关闭公开结果，但不得改写先前保存的prior/pre摘要。
4. 如该步共同可评价，才把它追加到ring并移出最旧误差。D的q/损失证据使用步骤1冻结副本，不得误返回append后的窗口。

全历史时只在D构造q/MAE/RMSE摘要；此前只追加三个有限误差和固定源引用。独立离线逐时点评价采用§8的一次遍历参考，不反复重跑所有前缀，不为验收需求向首片公开全历史接口。

## 5. 正常值、窗口与逐字段失败

### 5.1 冻结公式

基参数完全沿026；三模型ID固定 `kalman,last_close,lagged_ema`。模型段j1…20为旧warmup；诊断以预测起点已成熟为准，j≤21无共同误差，j22起有效。W=60、p=0.90、第54小、不插值；首个完整当前为j82。

`eX=y_current−mX`；与现有innovation/log_return只作事后交叉检查。q/MAE/RMSE用当前之前紧邻60个共同可评价误差；不按模型各自删行。MAE=`fsum(abs(e))/60`；RMSE=`sqrt(fsum(e*e)/60)`。配对差直接以本次报告对应原损失相减，字段明确 `K_minus_R / K_minus_E`，负值只说明相应窗口该损失较小，不输出优劣枚举/自动切换。

q=0合法；`below=e<−q,above=e>q,inside=其余`为唯一float真值，outside为两侧之一。m±q仅展示、注明rounding，不以舍入端点重判。数值都为原有限float64与JSON最短往返表示，显示精度不影响条件。没有e/q、概率或价格目标。

固定模型/EWMA范围、coverage、连续越界与IS仅用于独立离线验收。报告保留prior的S/v_pre以便参考计算，首片不再追加这些算法统计输出。离线对称范围统一半宽a：width=2a、IS=2a+20max(abs(e)−a,0)，固定尺度c=1.6448536269514722；它不带真实0.90覆盖承诺。

### 5.2 状态矩阵

| 条件 | 当前/窗口输出与状态 |
|---|---|
| source_rejection有值 | 顶层unavailable，reason=known_negative_source；主字段与下行相同关闭，source/coverage仍给；跳过状态递推 |
| daily_coverage.coverage_known=false | 顶层unavailable，reason=date_set_integrity_unknown；current、models、comparisons、window为null，evidence为空；source/coverage仍给；跳过状态递推，无删坏点子集 |
| D无日期组/空前缀 | unavailable/cutoff_missing；同上，不用最后源日代替D |
| D是既有坏/重复/源冲突组 | unavailable，沿该组reason；current只有请求D和可追溯ordinal/规范close（存在才有），模型字段关闭；不展示前一可算行假装D |
| 当前段预测起点未成熟（正常j1…21） | current可显示源值；status=warming_up，models的prior/error/q/损失均null，reason=forecast_origin_warmup；不将旧j21 computed混成可评价 |
| 当前共同误差合格、ring不足60 | status=history_insufficient；prior/e可显示，q/position/MAE/RMSE及配对差null；window有actual_count、实际端点和calibration_history_insufficient；evidence仅保留实际可用前序误差 |
| 完整60窗 | status=computed；逐字段按下表有效/失败输出；不因某个RMSE失败关闭全部q/MAE |
| 任何既有坏/重复/数值失败 | 保留原槽、原segment行为；清空新ring，下一既有段按j重新预热，不跨段凑历史 |
| 相邻源Decimal不同但float或log相同 | 从碰撞点起关闭该既有segment剩余新诊断；reason=precision_loss_state_dependency，直到下一次既有reset；检查从j2开始，既往结果不追溯作废，旧state/旧公开数值不改 |

对于precision_loss后缀，current源值及首个碰撞date/ordinal可追溯，models/窗口数值及证据关闭；不能仅清空ring后过60条就恢复，因为K/EMA状态仍依赖碰撞观察。

| 仅损失/显示运算失败 | 最小作用域 |
|---|---|
| 非零e平方为0、平方非有限、RMSE平方和/均方/sqrt失败 | 对应RMSE及依赖该项的差null，分别numerical_underflow/numerical_failure；q/MAE仍按各自定义保留。正平方和除60变0也算underflow。坏平方槽仍在60窗里，直到出窗才可能恢复 |
| MAE fsum失败、和非有限，或正绝对值和除60变0 | 该MAE及对应差null，其它字段保留；正→0为numerical_underflow，其余数值运算失败为numerical_failure |
| q非有限/负值（合法有限误差不应出现） | 内部合同错误，整新调用失败；不可静默选另一个分位或加地板 |
| m±q某展示端点非有限 | 对应lower/upper null、price_range_numerical_failure；有限e/q的position仍按误差域计算 |
| 配对减法非有限 | 仅相应差null/numerical_failure，损失原值保留 |

有限性按sum→mean→sqrt→difference逐步检查；数学上应非负的量若出现负值为内部合同错误，不能加epsilon/夹到0。全零sum/mean是合法零；正sum除60到零必须与它区分。`t=math.ulp(0.0)`时`t/60==0`；`e=math.sqrt(t)`时`e*e==t`非零而`(e*e)/60==0`，因此只查平方不够。两例仅用于私有损失helper防御测试，不伪装成正常Store价格可产生的轨迹。

本片不追查同坏源行所有潜在缺陷；沿现有bar的primary reason，原checks由来源引用回查。未知实际日历/间隔、闭合、复权、公司行动和known_at始终是独立限制，不与上述计算失败合并成“来源已合格”。

## 6. 输出与身份

顶层固定键：`method_id,analysis_id,inputs,parameters,mode,units,source,source_qualification,historical_availability,limitations,result`。

```text
method_id = daily-one-step-source-diagnostic-v1
mode = retrospective
inputs = [{snapshot_id, query_id}]
parameters = {
  cutoff,
  base_model: fixed_parameters() 的完整原值,
  window: 60, absolute_error_quantile: 0.9, order_rank: 54,
  quantile_method: nearest-rank-no-interpolation,
  forecast_origin_min_observations: 21,
  policies: 固定版本组
}
source_qualification = conditional_frozen_source_observations
historical_availability = unverified
units = {log_coordinate: ln_source_price_numeric_value,
         error_and_loss: natural_log_ratio, variance: natural_log_ratio_squared}
```

policies至少固定 `source_window=daily-source-date-groups-v1`、`predictor=pre-update-private-prior-v1`、`calibration=common-lagged-errors-60-v1`、`comparison=binary64-residual-domain-v1`、`precision=collision-blocks-existing-segment-v1`；以上是方法身份常量，不接用户覆盖。

source仅含 `{batch_id,raw_sha256,source_contract_id,identity,period}`，identity为 `symbol_identity`原返回（含其身份声明qualification）；详细调整/单位/legacy/运输/语义字段通过同一snapshot/query/contract回查，不复制整个metadata、不新增认证状态。固定limitations至少包括：`retrospective_source_version,calendar_and_corporate_actions_unverified,adjustment_basis_unverified,historical_availability_unverified,bar_closure_unverified,source_identity_not_security_master_verified,fixed_engineering_parameters_not_calibrated,empirical_quantile_without_coverage_guarantee,no_prediction_alpha_or_trading_return_claim,one_step_observation_target_not_latent_trend`。historical_availability首片总为unverified，即使输入含未经本片核验的known_at声明；这说明本算法未证明历史可得，不抹去原始声明。source_qualification说明数值解释边界，不是来源pass认证；实际计算是否可用由result.calculation_status单独给出。

`analysis_id=_identity({method_id,inputs,parameters,source})`；使用现有规范JSON，完整输出不加入时间戳/耗时/机器名。source绑定以上直接来源引用与身份资格，不重哈希所有行；真实性继续依赖可信Store。新快照/参数/来源身份变化应变ID，固定同D的两个读取投影不变。公开旧single的method/analysis_id不引用新诊断，不因这次提取改变。

result固定包含：

- `calculation_status,reasons,coverage`；§5.2中的status均对应此字段，枚举为unavailable/warming_up/history_insufficient/computed。reasons为稳定去重code列表，字典序。computed允许某个独立损失字段失败，具体见field_reasons；不另造绿色总pass。
- `current`：请求D、实际当前date/ordinal、规范close字符串、当前segment_id/segment_observations、source_prefix_start与当前state_segment_start。缺D时null；异常组没有唯一ordinal时保留null。不称规范close为原始token。
- `window`：expected_count=60、actual_count、start/end观察日期及origin起止、`window_unit=source_observation_intervals`。只指当前之前的共同误差支持，当前不在其中；模型完整状态仍从实际来源前缀起点形成。不可评价整体时null。
- `models`：固定三模型顺序，每项 `{model_id,prediction_log,error_log,abs_error_quantile,lower_log,upper_log,position,mae_pre,rmse_pre,field_reasons}`；field_reasons仅对失败字段给稳定code，值存在且无运算失败不能凭空加失败reason。warming_up结构仍固定、数值null。
- `prior_scales`：`model_innovation_variance_pre,rw_ewma_variance_pre`及origin引用；只读capture，初始不可用或当前被门控关闭为null。无sqrt年化。
- `comparisons`：MAE/RMSE的K_minus_R、K_minus_E与逐字段reason，无总体评分。
- `evidence`：至多60条**前序**误差，每条 `{origin_date,origin_ordinal,observation_date,observation_ordinal,segment_id,origin_observations,kalman_error_log,last_close_error_log,lagged_ema_error_log}`，当前该条的segment_observations=origin_observations+1，按观察日期/ordinal有序；不复制源OHLC或整历史，不包含当前误差。
- `cohort_counts`：只在运行了状态遍历时给互斥的起点未成熟/共同一步可评价/来源或状态不可评价，以及共同可评价中的pre_window_insufficient/complete。跳过模型时为null，不能用0冒充已统计；全源coverage另在顶层result保留。
- `diagnostic_block`：precision_loss时首个碰撞date/ordinal/reason；其它时null。不保留全部受影响后缀复制品。

完整模型数值报告的正常82槽守恒：21个起点未成熟＋61共同误差；61=60前序窗不足＋1完整。优先级为已有row失败→precision_loss后缀→起点未成熟→共同误差；三类计数不直接复用旧warmup字段。count只是source-slot账目，不能翻译为交易天数或独立样本数。

返回级别优先级固定为：调用参数错误先抛出；可归一化后，隔离源优先于date_set_integrity_unknown，后者优先于cutoff_missing，再按当前row失败→precision_loss后缀→起点未成熟→窗口不足→完整窗口。多个全局限制可并列于reasons，但主字段关闭规则一致。模型未运行时cohort_counts=null；coverage是正常归一化得到的原始行/日期组账目，仍可给出。缺D也不运行模型。当前坏组且覆盖已知时，为对账此前段仍完成到该组的一次递推；cohort_counts包含该坏槽，models/comparisons/window/prior_scales=null，evidence=[]。precision_loss后缀同样关闭这些字段；正常预热则保留固定三模型null结构。history_insufficient时models保留prediction_log/error_log，prior_scales可用；完整损失字段各自失败不改变共同误差或完整窗的计数。

## 7. 独立验收与旧兼容

### 7.1 两轨oracle，先负例

1. 数值轨：作者在 `tests/test_forecast_diagnostics.py` 内写自包含参考：从源字符串用60位局部Decimal context取ln，使用通用2×2矩阵乘/加/转置、Joseph更新与独立EMA/RW；不导入产品 `_update`/capture/窗口/损失函数。误差、q和损失用 `abs(actual−ref)≤max(2e−11,2e−10×abs(ref))`，仅用于下表冻结的普通轨迹，不把此容差推广全部极端轨迹。基模型参数按026文字常量独立定义；EMA/EWMA半衰系数在高精度参考独立计算，不调用fixed_parameters取得计算中间值。
2. 严格轨：索引、j22/j82、54名、源资格、零q、相等、二进制nextafter和m±q舍入反例均直接核对表示值/整数结果；不靠Decimal近似或容差裁决inside。

固定普通fixture，全部长度160、`i=0…159`。先在60位Decimal context算 `P_i=100×exp(g_i)`，按`quantize(Decimal('0.00000001'), rounding=ROUND_HALF_EVEN)`输出恰8位小数字符串，再由双方从该源字符串读入；OHLC四值相同，日期为2020-01-01加i个自然日、ordinal=i+1。这是合成来源日期，不暗示交易日历。唯一例外Z直接用close='1'以得到log精确0。生成全确定性，**不用随机数，seed不适用**；不在失败后换种子/量化或放宽容差。

| fixture | 冻结 `g_i` 或直接价格 |
|---|---|
| Z | 直接价格字符串'1'，160槽；严格零误差/零q/inside参考 |
| C | `g_i=0`，恒定100；仅普通数值轨，不以高精度零误差强判float position |
| T | `g_i=0.001×i`，固定对数斜率 |
| A | `g_i=0.002×(i mod 2)`，上下交替 |
| J | `g_i=0.0005×i+0.08×1[i≥80]`，持久跳变 |
| P | `g_i=0.0005×i+0.08×1[i=80]`，单点冲击后回归原轨 |
| V | `g_0=0`；`g_i=sum(a_k×c[(k−1) mod 8],k=1…i)`；`c=(-2,-1,1,2,0,1,-1,0)`，k<80时`a_k=.001`，否则`.004` |

这些量化后的普通源价在0.01～1,000,000内；超出此冻结集合的极端防御样例只验具体合同，不套用上述精度承诺。C等非1常数可因float EMA组合有末位残差，q/position以产品表示值的独立直接误差判断核对。截取Z/T/J的20/21/22/81/82前缀验索引；有限集合的逐前缀/未来修改测试允许小规模重跑，不能把这种测试策略当作真实逐步评价的性能架构。

覆盖034所有反例，重点加：当前有效价格变化而捕获prior逐字段完全不变；修改未使用的当前high/low但仍OHLC有效不改预测；当前变无效/precision_loss是公开资格变化，保存prior不可被重算覆盖。collector注入异常需使新调用失败，旧公开路径不得因此被重置或改值。所有入参深拷贝对照不变。

q手算54个0.01+6个0.10→q0.01；当前0.02应above，不能先append使q升至0.02。正常82槽、重复/坏点后重启、precision_loss从j2阻断至真实reset、有限零误差/零方差、RMSE下溢而MAE/q保留分别覆盖。私有窗口helper可接已构造的60个误差以独立检验算术：全零；54×.01+6×.10；一个t与59个0的MAE除60下溢；一个sqrt(t)与59个0的RMSE均方下溢；一个1e200与59个0的平方溢出。t为math.ulp(0.0)。后续追加60个正常误差，失败槽自然出窗后相应损失才恢复。不得把helper用例伪造成DECIMAL源价轨迹。

时序spy记录D前freeze摘要→capture prior→本轮旧_update→公开current计算→append的调用序；当前坏bar仍记录capture后旧reset。capture=False时prior分配计数为0。主动让窗口helper抛出RuntimeError或ArithmeticError，断言新调用向外失败，旧状态迭代/旧公开报告不变；不能仅比较最终结果推定时序正确。

### 7.2 兼容硬门槛

- 在第一次产品编辑前，核验旧signal源码hash仍为034记录的`8b0d041a…f55c2`，保存完整源码只读副本与hash到仓库外验收目录；运行旧 `signal_report` 冻结**完整规范JSON**，不能只冻结摘要或少数字段。依赖版本不明时不得生成。全部调用lookback=20/horizon=5/test_start=None，query.selection.cutoff=fixture最后日期。
- golden的固定集合：上述Z/T/J原样；T的i=40价格四值改'0'；T的i=40行复制成不同ordinal的同日期行；T的i=40标签改None移到unlocated；T的i=40 tokens.code与metadata.source_code冲突；T的i=40 tokens.adjustflag与metadata.source_adjustflag冲突；metadata.quarantined=True的T；全局Decimal context.prec=3的T；T的旧 `_update` 第40次调用只抛一次ArithmeticError、之后委托原函数；T的 `_price_scale` 第60次调用返回(None,'price_scale_out_of_range')、其它调用委托原函数。分别生成，不能合并成只命中首个reason的单用例。后两者为原控制流/展示防御注入，不改变旧函数签名或扩大源范围。
- 生成fixture时保存生成器/输入/旧源码hash；旧完整输出可存上述合成JSON文件。修改后相同环境、相同注入逐字节全等，单独检查既有API envelope/analysis_id；诊断调用前后再取旧报告仍全等。不得刷新golden掩盖差异。独立反方还须核对旧副本与实际diff，避免作者先改核心再冻结。
- 原 `tests/test_signal_research.py`、`test_research_series.py`、event/API/projection既有回归及全Python回归在最终源码上执行；没有前端改动也不能声称浏览器已验。实际通过/失败/skip/未跑分别报告。额外直接检验 `_price_scale(1000)` 与 `(-1000)` 原失败；不得以1e999源价制造新算法接受范围。
- 新公开/内部Store读取形状新报告完全相同；旧query/export不变；无新增Source/Store API。所有原件核验依旧由调用者执行，测试spy记录没有为三个模型重复读取/归一化。
- 不在033性能独占期间运行产品测试/大样本；等待协调允许后再执行。本文阶段只有读代码和小手算，测试均未跑。

计划命令（**尚未运行**；只能在正式设计许可、033资源释放且集成负责人明确解除发布冻结并启动本片之后）：先用已锁定`.venv/bin/python -m pytest -q tests/test_forecast_diagnostics.py tests/test_forecast_diagnostics_adversarial.py`；再运行`.venv/bin/python -m pytest -q tests/test_signal_research.py tests/test_research_series.py tests/test_research_adversarial.py tests/test_research_projection.py tests/test_research_api.py`及实际event回归；最终`.venv/bin/python -m pytest -q`。不修改旧测试预期、不安装新依赖。新输入拒绝与资格用例先写再改产品；golden须在产品改动前生成并封存。

## 8. 固定真实窗口与资格

真实路径复用029已存原件→已批准legacy封套→Store。**每股原件640行是递推前缀起点，目标视图484/478/475行只是展示/报告范围；不能把2024-10-11当初始化日重新预热。** 每个D由Store读取该源全部≤D前缀及全部unlocated；保存每股实际起点和本次query_id。若Store中的源已被裁成目标视图，应暂停真实验证并回到原640行版本，不混称同一模型。

固定对象与D完全沿034：

- 全原30股，D=2026-10-09，保留全部结果/失败；三组分别报告，不给全市场结论。
- 688981.SH在2025-09-05/09；688012.SH在2025-12-31/2026-01-05：缺D应失败，复牌源区间注明跨停牌。公告只作验收旁注，不伪装纯函数自动识别。
- 全30股，季度固定边界2025-03-31/06-30/09-30/12-31、2026-03-31/06-30/09-30；边界缺日不回退。逐步评价由离线参考/验收脚本执行，不为其加产品全历史路由。

未知复权/公司行动、源known_at、当前成员选择、共同市场冲击均保留；这些已在别的功能用过的日期不叫未见测试。真实原价与逐步响应留仓库外，提交仓库仅资格摘要/合成数据。没有真实变点标签，不报检出率；没有执行/费用，不报经济收益。

按每模型同槽记录前序MAE/RMSE；独立评价固定q与K模型尺度/RW EWMA范围的inside/below/above、宽度、IS与连续越界。只评价各观察自己的先前q，禁止在同一校准60窗自证覆盖。所有候选和失败保留，不调W/p补救不利结果。

离线逐时点评价脚本保留在仓库外验收目录，hash/命令列入qualification；不成为产品接口。每股经Store读取并核验完整640来源至最大D一次，随后按来源槽**单次顺序遍历**，用产品私有 `_causal_rows(capture_prior=True)` 与同一诊断collector/窗口helper组合，保存O(60) ring、当前模型状态、季度累计及越界run状态。每步在next之前冻结前序摘要，再取prior/current、评价、入ring；这项逐时点工作仅在仓库外验收脚本做，不让单D产品入口每根排序。正式真实分报采用**产品同二进制残差域**，直接根据已保存产品e/q独立核对strict below/above/inside；不得以高精度/矩阵参考的末位不同重判产品布尔。另行独立60位/矩阵参考作数值oracle及差异记录，与产品结果分轨；它不能替代产品轨迹充当全时点验收。

若逐步明细需保留则流式写仓库外文件，不缓存每个前缀/每个60窗。固定W60下直观末窗排序为O(T W logW)，状态工作内存O(W)；禁止为全部历史时点重跑产品前缀并掩盖O(T²)。公共纯函数再复核预先列定的端点请求：30个末日、4个停复牌边界、30×7个季度边界，共244个请求位置（如有相同位置可去重并列数），与同二进制逐步结果对账；每一位置仍由Store取得同D完整prefix并逐请求核验，不复用另一D的query_id。每股源起点与全部成员清单先冻结，任何原件不足640/身份不符都停真实部分，不悄悄改初始化。离线脚本对私有helper的使用不授予新public全历史入口，也不能为便于脚本而扩成通用callback框架。

## 9. 资源与停做门槛

单源20k，W60、三个中心；无辅助事件payload。原 `daily_bars` 排序/状态成本计入端到端，新增ring/末窗排序为O(T)+O(WlogW)，附加工作内存O(W)、紧凑结果O(W)。旧公开函数仍为O(T)输出；新函数不复制其全series。

033独占结束并获协调允许后，同机5k/20k固定合成前缀：i=0…n−1，精确源价`100+Decimal(i)/1000`、四OHLC相同、日期1980-01-01加i个自然日，ordinal=i+1，无随机数/坏行。使用局部足够Decimal精度生成规范源文本并经同一现有解码/Store路径取query。每路预热1次、交错5对。冻结**相同消费方式**A/B：A为同一日线归一化＋ `capture_prior=False` 的causal_rows流，仅drain既有row；B为相同归一化＋capture开启＋diag collector。A/B均不保存T条row。旧完整signal_report仅用于golden/另列参考，不作为新片增量基线。记录完整计时边界，不能用省去events/全series来掩盖diag开销。

- 20k的五对公式层，**每一对**`Δ_i=T_B,i−T_A,i≤100ms`，等价`max_i Δ_i≤100ms`；不能只要求中位≤100ms。100ms是新增预算，不是整个20k入口上限。独立进程也采用同drain消费，峰值RSS增量≤8MiB；明确初始化/输入归属，不称其为净分配。最终紧凑新报告≤32KiB，包括完整≤60证据。报告中位/范围/每对，5次不称稳定p95。
- 端到端同Store读取/原件核验路径**每一对**总耗时 `T_new,i≤1.10T_base,i+100ms`。两路同一完整前缀/同样必要源校验/同样drain消费；不得A保留T行、B仅保留60行而宣称新增低内存。
- 计数/来源加载若经Store最多一次来源读取与原件核验；纯函数自身0 I/O。归一化和基模型各1次。20,001行时二者0次。
- 未达到时先查重复扫描/复制/捕获T条prior，不放宽口径、不删原因/证据、不取消原件核验。共享负载下结果另列并在空闲时重跑完整组，不挑最快单次。

停做条件沿034：前视/窗口删坏/资格升级即阻断；若需扩多个模块则收窄；经验范围只靠扩大宽度改善inside或相对已有EWMA无解释增量，则不接q/UI；配对误差审计可独立保留。没有任务价值不扩UI，没有独立证据不接选股/变点/交易。

## 10. 正式反方意见逐项答复

| 正式意见 | 已落合同及对应验证 |
|---|---|
| FD-01 私有prior和时间顺序 | §4保留原_update与旧catch；generator不接ring，active时在坏bar分支前capture；consumer在next(D)前freeze。§7的spy、当前有效/无效价改动、错误注入与旧golden分别核验。 |
| FD-02 截止、身份与可信边界 | §2–3同D严格相等、_identity选择身份、完整Store前缀；只复用既有来源helper。删除events输入、全check验证、ordinal唯一集合、值长度/指数新guard和猜测batch check别名。 |
| FD-03 状态、失败、计数 | §5–6字段表、调用错误与返回优先级，calculation_status/source_qualification/historical_availability分列；未跑计数null、正常82槽守恒、证据附segment/起点观测数。 |
| FD-04 数值与依赖 | §5逐步检查square/sum/mean/sqrt/difference，补正sum除60下溢；§7私有helper手算边界与出窗恢复；precision后缀不自行洗白。 |
| FD-05 独立oracle和旧完整输出 | §7固定7条160槽精确生成式与量化、无随机种子；严格零单用close=1。12个旧完整golden场景含低context/隔离/冲突/reset/展示失败，必须先冻结再改产品；保留旧测试预期。 |
| FD-06 同工资源 | §9 A/B均归一化+同causal流drain，5对每对公式Δ≤100ms及端到端预算，同消费独立进程RSS；无events/全series节省的混淆。 |
| FD-07 固定真实矩阵 | §8从每股原640起点递推，仅将目标视图分报告；完整30股/全部冻结D、产品同二进制私有流单遍评价+244固定公共端点；独立数值oracle另轨，严格布尔用保存的产品e/q核对，无全prefix O(T²)评价。 |

## 11. 编码前审查待定记录（历史）

正式反方需逐项确认：单D/query_id一致、无events、全部原640源前缀、私有generator/capture是否最小且不改旧异常捕获、所有空值/计数、可信Store边界、oracle双轨范围、同边界性能基线及32KiB可表示性。设计获批并经集成负责人另行解除发布冻结、明确启动后，才先写异常和oracle，再做最小代码；此前继续只做文档。

已完成：实际Store query/count/投影、symbol_identity、numeric、signal状态结构静态核读；本计划接口/身份/错误/窗口/预算提案。未完成：正式复审决定、产品实现、测试、真实诊断、性能、UI/Windows、用户任务或效果资格。未将本计划当作完成声明。


## 12. 执行闭环与保留的停止决定

2026-10-11，正式设计反方关闭FD-01～07；033发布后集成负责人08:11 UTC明确解除冻结并启动。测试先行、旧12完整golden和七条数值oracle冻结后完成约定最小实现。原反方45项加作者194项及旧相关130项共369项通过；最终Python2540通过/49跳过/0失败、Node128通过、TypeScript/Vite通过。实现源码及169份完整冻结在全仓、真实与资源后均未变化，未改旧公共输出、Store、HTTP或UI。

30×640单遍及244预登记用途完成，243唯一端点严格对账，241端点computed、2缺D；映回用途为241 computed、3预期缺D。目标视图全30股K一步MAE/RMSE均劣于RW、优于滞后EMA。三组RW经验范围虽更窄，平均IS均略差于EWMA；保留所有负结果，不调W/p、不重选源/窗口。

按§9停止门槛，本片保留纯计算误差审计和限制披露；不据q推进入口或页面扩张，不添加选股/换模型/变点。下一预测算法若继续，应另审目标、预登记数据与评价口径。资源时延、JSON和次数已过；原RSS高水位污染使该证据inconclusive，另版本单次VmHWM补测仍受输入准备高峰遮蔽，RSS增量预算继续未验、不追加重跑，未证明产品超限。两轮原证据与最终独立决定见[资格记录](../qualification/forecast-diagnostics.md)。这些结果不授予历史可得、未来概率覆盖、潜在趋势准确性或经济收益。


08:50 UTC负责人工程决定：在独立终审已明确两轮RSS均无法辨识增量的前提下，接受该开放项并批准有限合并；仅独立调用纯诊断，不接HTTP/API、UI或默认服务。因果、兼容、固定真实负结果、时延、JSON与次数有各自证据，不能把它们抵换内存预算。RSS≤8MiB继续未验、非产品超限结论、非FD-06全通过；在未来默认服务或UI接入前须另审可辨识的同工资源协议和用户任务价值。原及v2结果hash、全部phases与最终独立范围见[验收§5–7](../qualification/forecast-diagnostics.md)，不删除原测量问题或追跑刷绿。
