# 007 · 国际交易研究软件高级功能矩阵

核查日期：2026-10-03—04。用途：为 F01–F17 提供功能定义、数据门槛和有限的后续验收任务。**这是官方说明书与源代码调查；13 款产品均未完成客户端实测，未验证 A 股数据兼容或交易效果。** 未安装、购买、开通行情，也未执行下列验收任务。

证据标记：**D**＝实际核读官方文档相关段落；**C**＝核读固定版本原始代码；**I**＝仅官方搜索索引摘录，原文访问失败。D 不代表通读产品全部手册，空缺也不代表产品没有该能力。本文沿用 [003 的可识别性边界](003-volume-microstructure.md) 与 [004 的四层验收](004-data-validity-and-evaluation.md)，不新增收益结论。

## 1. 比较时必须保留的语义

| 名称 | 最低数据与定义边界 |
|---|---|
| 实际成交分布 / Footprint | 逐价实际成交量需要逐笔或可信的逐价汇总；由低周期 OHLCV 分配出的分布须标为估计。Footprint 中的“买/卖”可能来自报价比较、tick 涨跌或低周期蜡烛方向，三者不可混写。 |
| 成交 Delta / 盘口不平衡 / 事件 OFI | 成交 Delta 累加已分类成交；盘口不平衡比较选定深度的挂单规模；Cont 型 OFI 累加有序最优报价及数量变化。名称含有 order flow 或 imbalance，不能证明采用了 OFI 公式。 |
| 盘口热图 / 回放 | 深度热图需要深度观测及时间信息；完整事件回放还需要顺序、历史覆盖与记录完整性。仅成交打印无法恢复挂撤单。 |
| VWAP / Anchored VWAP | 同覆盖范围的实际成交额与股数可给出 `ΣA/ΣV`；以 OHLC 代表价乘量是另一种估计。锚点、会话、截止时间及累计范围均属于参数。 |
| TPO / Volume Profile | TPO 按所选时间块记录价格出现；Volume Profile 按价格聚合成交量。TPO 字母数不能直接解释为成交量、逐秒停留时长或投资者持仓。 |
| Tick Replay / Bar Magnifier / 回测 | 指标事件回放、低周期路径细化、模拟成交各有合同。较细行情仍不能单独证明排队位置、容量、冲击和真实成交。 |

这些是比较口径与项目推论；各产品已经核到的具体机制列于下表。

## 2. 产品、核读范围与算法边界

| 产品 / 证据 | 核读的具体高级功能与直接来源 | 数据、方向与信息时点边界 | 功能族 |
|---|---|---|---|
| **TradingView · D** | [Volume Footprint](https://www.tradingview.com/support/solutions/43000726164-volume-footprint-charts-a-complete-guide/) 的低周期来源、方向分类、重绘段；[Bar Magnifier](https://www.tradingview.com/support/solutions/43000669285-what-is-bar-magnifier-backtesting-mode/) 的周期表与覆盖上限。 | Footprint 按低周期价格方向分配买卖量，含同价继承规则；并未因此取得交易所主动方。历史越深可能改用更粗数据；官方明确会重绘。Bar Magnifier 使用更低周期 OHLC，最多覆盖 200,000 根低周期柱，早期交易可能无覆盖。 | F04、F07、F08、F13 |
| **Sierra Chart · D** | [Numbers Bars](https://www.sierrachart.com/index.php?page=doc/NumbersBars.php) 的定义、准确性与数据要求；[Market Depth Historical Graph](https://www.sierrachart.com/index.php?page=doc/StudiesReference.php&ID=375&Name=Market_Depth_Historical_Graph) 的深度记录要求。 | Numbers Bars 要求日内 1 Tick 数据与可靠 Bid/Ask 成交分类；完整盘口深度并非其必要输入。深度热图另需相应记录/历史深度。只有现时深度不能补出过去缺失记录；历史日线不能直接替代逐笔足迹。 | F04、F07、F08 |
| **NinjaTrader 8 · D** | [Volumetric Bars](https://static.ninjatrader.com/support/helpGuides/nt8/order_flow_volumetric_bars.htm) 的 BidAsk/UpDownTick 分类；[Volume Profile](https://static.ninjatrader.com/support/helpGuides/nt8/order_flow_volume_profile.htm) 的 Minute/Tick 数据分辨率；[Tick Replay](https://static.ninjatrader.com/support/helpGuides/nt8/developing_for__tick_replay.htm) 的注意事项。 | BidAsk 比较成交与买卖报价，价差内成交延续先前方向；UpDownTick 比较成交价。Minute Profile 将分钟量均分到高低区间，Tick 模式另算。Tick Replay 主要回放 Last 事件，只带成交时 BBO；缺报价可代入 Bid=Last、Ask=Bid+1 tick，不能当完整报价历史。官方明确其用途不包含精确历史成交仿真。 | F04、F07、F08、F13、F15 |
| **Bookmap · D** | [Heatmap](https://bookmap.com/knowledgebase/docs/KB-SettingUpAndOperating-HeatmapMainChart) 的挂单热图；[成交点聚合](https://bookmap.com/knowledgebase/docs/KB-SettingUpAndOperating-HeatmapTradedVolumeVisualization)；[Imbalance](https://bookmap.com/knowledgebase/it/docs/KB-Indicators-Imbalance) 的公式、可见范围和权重。 | 热图描绘已观察到的挂单流动性，成交点描绘执行量；需要对应深度和成交数据。成交点按像素时间片聚合，缩放会变。盘口/成交量不平衡采用选定范围的买卖侧差和比，拖动或缩放会改变读数；不能直接冠以 Cont 事件 OFI。深度观测无法识别未展示的全部隐含量或交易意图。 | F04、F07、F08 |
| **ATAS · D** | [Replay](https://help.atas.net/en/support/solutions/articles/72000662041-replay-trading-simulator-) 的三种数据模式；[Cluster Search](https://help.atas.net/en/support/solutions/articles/72000602240-cluster-search) 的筛选条件与 Use Previous Close。 | Candles 和 Ticks 模式中的 BBO 均为近似；Ticks and DOM 才包含成交和盘口变化。Cluster Search 能筛选量、Bid/Ask、Delta 等，Use Previous Close 选择已闭合柱。各数据源如何赋予主动方向仍须核验；实时未闭合柱数值变化不能与闭合历史重算混为一项。 | F04、F08、F11 |
| **Quantower · D** | [Cluster](https://help.quantower.com/quantower/analytics-panels/chart/volume-analysis-tools/cluster-chart) 的价位聚合与过滤；[Historical Time & Sales](https://help.quantower.com/quantower/analytics-panels/chart/volume-analysis-tools/historical-time-and-sales) 的字段；[TPO](https://help.quantower.com/quantower/analytics-panels/tpo-chart) 的时间块与附加成交分布。 | 成交明细将 Aggressor flag 与 Tick direction 分列，可导出核对；字段来源与缺省值仍依连接器。Cluster 被阈值排除的量可显示 0，须区别真实零成交。TPO 附加 Volume Profile 要求 tick 历史；价位步长会改变聚合。 | F01、F04、F07、F08 |
| **AmiBroker · D** | [AFL TimeFrameExpand](https://www.amibroker.com/guide/afl/timeframeexpand.html) 的 expandFirst/Last；[Walk-forward](https://www.amibroker.com/guide/h_walkforward.html) 的 IS/OOS、滚动与固定起点。 | 官方明确：把本周 High 用 expandFirst 展开到周一会提前泄露周内后续高点；周 Open 的情形不同。Walk-forward 支持训练优化后推进测试，但反复观看并挑选 OOS 的行为仍须由实验协议约束。 | F04、F12、F13、F15 |
| **MultiCharts / .NET · D+I** | [购买页](https://www.multicharts.com/purchase/) 可见 Portfolio Trader、Walk-Forward 等功能入口（D，仅证实功能名称）；[.NET Programming Guide v1.1 §4.6.7，页 50](https://download.multicharts.com/downloads/MultiCharts.NET-ProgrammingGuide-v1.1.pdf) 的官方索引给出 Bar Magnifier（I）。 | 索引摘录列出 tick/秒/分钟/日等细化选项；PDF 未成功读取，不能声称核验了全部填单规则。网页特性正文访问亦失败。先补齐原文及版本，再确认 MultiCharts 与 .NET 的差异、历史覆盖、组合与 walk-forward 实际行为。 | F13、F14、F15；机制待补证 |
| **TradeStation 10 · D** | [Intrabar Order Generation](https://help.tradestation.com/10_00/eng/tradestationhelp/chart_analysis/intrabar_order_generation.htm) 的实时/历史区别；[Look-Inside-Bar](https://help.tradestation.com/10_00/eng/tradestationhelp/subsystems/spr_topics/report/look_inside_bar_back_testing_strategy_performance_report_.htm) 的细化周期。 | 实时 IOG 可每 tick 求值；历史 IOG 本身只知道 OHLC 四点，需 Look-Inside-Bar 的更细历史补充路径。更细输入仍需独立核验限价/止损先后、缺数据覆盖与成交假设，不能据 IOG 名称认定逐笔精确回测。 | F13、F15 |
| **thinkorswim · D** | [AnchoredVWAP](https://toslc.thinkorswim.com/center/reference/Tech-Indicators/studies-library/A-B/AnchoredVWAP) 的日期锚点与偏差带；[thinkScript VolumeProfile](https://toslc.thinkorswim.com/center/reference/thinkScript/Functions/Profiles/VolumeProfile.html) 的价位、起新分布、扩展区参数。 | 文档说明从用户锚点累计；本轮未核到其底层代表价与成交额使用方式。VolumeProfile 可在扩展区聚合图表数据；最终全段分布不能回填为早期已知量。事后选到最低点的锚定结果只可用于相应回顾任务。 | F07、F15 |
| **MetaTrader 5 · D** | [Tick Generation](https://www.metatrader5.com/en/terminal/help/algotrading/tick_generation) 的真实/生成 tick 与缺失处理；[Strategy Testing](https://www.metatrader5.com/en/terminal/help/algotrading/testing) 的数据模式、forward 分段；[Tester Journal](https://www.metatrader5.com/en/terminal/help/algotrading/tester_journal) 的不匹配记录。 | “Based on real ticks”仍可能在某分钟有 M1 柱、无真实 tick 时生成 tick；无相应 M1 柱的 tick 会被忽略。Last 图表与 Bid/Ask 执行价格须区分。外汇 tick volume 是变价次数，其经济含义与证券成交量不同，见[官方量指标定义](https://www.metatrader5.com/en/terminal/help/indicators/volume_indicators)。 | F02、F04、F13、F15 |
| **QuantConnect / LEAN · D+C** | [Portfolio Construction](https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/portfolio-construction/key-concepts) 的 Target 与再平衡触发；固定提交的 [EquityFillModel](https://github.com/QuantConnect/Lean/blob/705b9551be1aaa821c7f77896a7eb8fcd07b92ee/Common/Orders/Fills/EquityFillModel.cs) 市价/限价路径；[VWAP 指标类](https://github.com/QuantConnect/Lean/blob/705b9551be1aaa821c7f77896a7eb8fcd07b92ee/Indicators/VolumeWeightedAveragePriceIndicator.cs)。 | 默认组合模型可随 Insight、证券池和时间规则再平衡；目标数量与实际成交分开。所读 EquityFillModel 满足条件后可填整笔订单量，未由此证明排队或容量。该 VWAP 类用 OHLC4 和 Volume 做指定周期加权；不能把这个类直接认定为实际金额/量或锚定 VWAP。 | F07、F12、F13、F14、F15 |
| **StockCharts · D** | [Advanced Scan Workbench](https://help.stockcharts.com/scanning-and-alerts/technical-scans/advanced-scan-workbench) 的复合条件、日期与 ChartList；[Anchored VWAP](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/anchored-vwap) 的锚点用法。 | 可定义多条件扫描并指定计算日期；这不能单独证明当日证券池、行业成员与数据版本的历史可得性。锚点选择时间须记录；本轮未核到 AVWAP 的输入代表价/成交额合同，留待数值对照。 | F07、F09、F11、F15 |

**OFI 留白**：本轮没有核到可直接认定为 Cont 定义且输入事件完整的内置实现。上表不据此断言产品缺少 OFI；后续须取得具体公式、输入字段与事件序列。Bookmap 的已核读不平衡公式与 003 的事件 OFI 对象不同，足以说明仅按功能名称对齐会出错。

## 3. 软件授权、数据权益与有限验收入口

此处只核功能授权形态，不作采购推荐或固定报价。软件可用、实时行情可用、历史逐笔/深度可下载、可导出重放是四项独立资格。账户地域、专业/非专业分类及 A 股许可均未实测。

| 产品 | 官方收费/数据信息及仍需确认之处 | 后续任务 |
|---|---|---|
| TradingView | [方案表](https://www.tradingview.com/pricing/) 区分免费/付费；Footprint 的 tick 级来源有方案限制。[交易所实时数据费用](https://www.tradingview.com/support/solutions/43000471705-how-to-purchase-additional-market-data/) 通常另计，付费软件方案不自动包含。 | INT02、INT05 |
| Sierra Chart | [服务套餐](https://www.sierrachart.com/index.php?page=doc/Packages.php) 将 Numbers Bars、TPO、历史深度图列为 Advanced 功能；外部连接、行情、历史深度需按套餐和数据源分别确认。 | INT02、INT03 |
| NinjaTrader | [官方 Footprint 说明](https://ninjatrader.com/futures/blogs/footprint-charts-guide/) 提及 Order Flow+ 的许可/附加订阅；账户权益另有变化，实际账户方案和历史 Bid/Ask-stamped tick 覆盖尚未确认。 | INT02、INT03、INT05 |
| Bookmap | [套餐表](https://bookmap.com/en/packages-comparison) 有免费 Digital 与收费层级；股票/期货实时行情费用另计，回补长度依数据源。回放输入可来自[实时录制](https://bookmap.com/knowledgebase/docs/KB-SettingUpAndOperating-HeatmapSupportingFeatures)。 | INT03 |
| ATAS | [价格/功能表](https://atas.net/pricing/) 有免费 Start 与付费层级；延迟/实时股票期货连接及回放权限分层，具体外部 feed 权益须核查。 | INT02、INT03 |
| Quantower | [功能许可表](https://www.quantower.com/pricing) 有免费功能与 Volume Analysis、TPO、DOM Surface 等付费扩展/组合；第三方行情费用不包含。动态页面未可靠提取金额，不记数值报价。 | INT02、INT03 |
| AmiBroker | [购买页](https://www.amibroker.com/order.html) 为付费永久许可并提供试用；Standard 与 Professional 的分钟/tick、秒级能力不同。数据接口和历史覆盖仍需单独确认。 | INT04、INT06 |
| MultiCharts | [购买页](https://www.multicharts.com/purchase/) 展示订阅/永久许可与试用入口；原文机制未补齐前，不把付费视为精细回测或组合测试已经通过。数据权益未核实。 | INT05、INT06，先补原文 |
| TradeStation | [官方价格页](https://www.tradestation.com/pricing/) 的索引（I）列出非经纪客户的软件技术订阅、Portfolio Maestro 与额外行情费；网页正文访问失败，实际账户减免及产品权益未知。 | INT05 |
| thinkorswim | [Schwab 官方页面](https://www.schwab.com/trading/thinkorswim) 将平台作为客户免费工具并提供 Guest Pass；实时行情仍受交易所协议/相关费用条件约束，开户适用性未核实。 | INT01 |
| MetaTrader 5 | [官方客户端下载](https://www.metatrader5.com/en/download) 免费；真实 tick、报价、证券品种和历史完整性依 broker/server。不能由免费客户端推出免费完整交易所数据；云计算服务费用本轮未核。 | INT05 |
| QuantConnect / LEAN | [LEAN 仓库](https://github.com/QuantConnect/Lean) 采用 Apache-2.0；[云平台](https://www.quantconnect.com/pricing/) 的计算、协作与数据服务另有方案。开源引擎许可不能代替数据使用/下载权。 | INT01、INT05、INT06 |
| StockCharts | [方案表](https://stockcharts.com/pricing/) 区分免费与会员层级，进阶扫描保存等能力分层，实时行情有附加数据方案；实际市场和历史权限未验证。 | INT01、INT04 |

**通用冻结项**：执行下列任一任务前记录客户端完整版本、连接器/数据源、市场与证券、交易时段、时区、单位、复权、请求范围、实际覆盖、数据哈希或可取得的导出快照，以及指标参数与计算截止时间。不能取得同一输入时，只比较工作流与功能合同，不计算跨产品“精度排名”。不能导入人工夹具的产品，用可合法取得的原生记录和独立手算；该替代样本的局限单列。

| 任务 | 有限操作与独立判断 | 对应功能族 / 门槛 |
|---|---|---|
| **INT01 · 均价定义** | 取一个短窗口的真实成交额、量及 OHLC。固定锚点、会话和截止柱，分别手算 `ΣA/ΣV` 与产品声明的代表价加权值；解释差异后才比误差。追加未来柱、缩放、重载各一次，记录闭合值变化及来源修订。LEAN 只测所读类；thinkorswim/StockCharts 先补代表价定义。 | F02、F04、F07、F17；数据单位/覆盖验收后 |
| **INT02 · 分布与方向** | 取含同价、价差内成交和稀疏成交的一小段记录，逐笔核对价格、量、报价与来源方向字段；将 up/down、报价推断、原生标记分列。对比分钟分配与逐笔分布，检查价位聚合、过滤后零值及闭合柱重载。另固定 TPO 时间块，手计价格出现次数，勿拿成交量作期望值。 | F02、F07、F08、F17；逐笔/报价证据不足则相关分支不执行 |
| **INT03 · 深度和事件回放** | 录制一个含无成交报价变化的 5 分钟片段；有明确事件类型时另核撤单。保留原件，在副本注入一次已知缺口；核对事件数、顺序、BBO/深度与缺口标记。ATAS 比三种模式；NinjaTrader 分开 Tick Replay 与 Market Replay；Bookmap/Quantower 固定可见范围及深度层数。只有快照时验收快照语义，不宣称恢复全部事件。 | F01、F02、F04、F08、F16、F17；G5 数据条件先满足 |
| **INT04 · 多周期与扫描时点** | 用一周内后段才出现新高的数据，保存周一截止与周末完整两份输入；核对 AmiBroker 展开模式和闭合规则。StockCharts 冻结候选证券池、扫描日期与参数，独立手算一个 AND/OR 规则；历史日期筛选不替代历史成分股证据。 | F03、F04、F09、F11、F15、F17；明确 available_at 和候选分母 |
| **INT05 · 柱内路径与模拟成交** | 先构造相同 OHLC、先后次序不同的两条 tick 路径，再取一个真实片段；冻结一个包含止损/止盈的简单订单情景，手记触发顺序。逐项比较默认柱、低周期与真实/生成 tick 模式，输出缺覆盖、生成比例、触发/填单差异。MT5 核对 Journal；LEAN 固定 fill/slippage/fee model。触发顺序正确只完成该项验收。 | F02、F12、F13、F17；不跳过市场规则、容量与成本实验 |
| **INT06 · Walk-forward 与组合账本** | 只选一组小参数网格，预先冻结一个 IS/OOS 切分和再平衡规则。核对训练只用 IS、参数生效时间、OOS 拼接、证券增删、持仓目标与实际模拟成交账本。记录所有试验及 OOS 被查看次数；AmiBroker 验证推进，LEAN 验证 Target/再平衡，MultiCharts 待补文档后纳入。 | F03、F12、F13、F14、F15、F16、F17；G6 组合验收另立任务 |

上述任务均为候选验收设计，**当前全部未执行**；不会扩大 G0 通过后已授权的编码范围。INT01–INT06 合起来也未覆盖 F01–F17 的全部叶子任务；F05 量价状态、F06 结构形态、F10 基本面事件等仍以 003、004 及后续专项研究为准。

## 4. 值得验证的差异，而非功能数量竞赛

1. **同名功能可能估计不同对象。** 已核到的例子包括 TradingView 的低周期方向、NinjaTrader 的分钟均分、Bookmap 的可见范围不平衡，以及 LEAN 指定类的 OHLC4 加权。项目可以先把“观测、分配、方向推断、生成数据”显示出来，再判断数值是否可比。软件存在这些模式本身不证明它质量较差。
2. **历史变化要按原因登记。** 未闭合柱更新、缩放改变计算范围、历史数据粒度替换、公司行动/源修订和真正未来信息泄露应分别记录。前缀不变性需固定输入版本、计算范围与方法；Bookmap 改可见窗口的读数变化不能直接判成未来泄露，TradingView 已声明的历史重算也不能隐去。
3. **回放逼真与回测有效分开验收。** NinjaTrader 的事件用途、ATAS 近似 BBO、MT5 缺 tick 回退说明模式名称不足以建立证据。细粒度输入改善可观察路径，仍要单独核验委托、填单、成本、容量和 A 股规则。
4. **自动滚动测试也会被研究选择污染。** AmiBroker 的 IS/OOS 工具、MultiCharts 的功能入口与 LEAN 的组合接口提供操作能力；只有冻结研究协议、保留全部试验和未查看测试集，才能支持相应样本外结论。依据见 004，无新增绩效推断。

| 可检验改进假设 | 最小衡量方式 | 失败/停止条件 |
|---|---|---|
| **来源与估计方式更容易审计**（F01、F02、F08、F16、F17） | 同一固定任务，统计未解释的数值差异、追溯到来源/参数所需操作数；保存对照证据。 | 无法取得可比输入时停止数值优劣比较；只报告工作流结果。 |
| **均价与日内参考量的定义更适合现有 A 股样本**（F03、F05、F07、F17） | 先通过真实单位、时段、量额覆盖与公司行动检查；对实际均价做独立手算，按 003 验证同时间槽基线与重新预热。 | 金额覆盖未知、股份口径不明或缺失被误记为零，阻断相应指标结论。精确计算不推出预测增量。 |
| **回放能明确暴露历史信息边界**（F04、F11、F12、F15、F17） | 相同数据版本截断/追加，比较闭合值、告警时间与扫描候选分母；差异逐项可解释。 | 后见锚点、周内未来高点或最终证券池进入早期决策，停止该实验。 |
| **策略研究结果更便于复现**（F12、F13、F14、F16、F17） | 固定输入、参数、成本与成交模型重跑，比较信号/订单/持仓账本；另测柱内路径与数据缺口敏感性。 | 只报净值、隐藏生成 tick 或调参次数时，不能签署样本外/交易价值结论。 |

以上均为待检验假设；现有产品也可能通过这些任务。当前没有实际产品对标结果，不能称为全面超越，也没有收益保证。

## 5. 来源访问与版本记录

- 官方页面仅核读表中所述相关段落。动态授权表只提取可靠可见的功能分层，不固定金额；任何后续购买/开通须重新核对当时方案。本轮没有用论坛或第三方宣传补齐未知机制。
- NinjaTrader 常规 helpGuides 链接访问重定向，本文使用其 `static.ninjatrader.com` 官方帮助镜像。另核读 [Playback Set Up](https://static.ninjatrader.com/support/helpGuides/nt8/set_up12.htm)：Market Replay 保存 Level I/II 的事件顺序，历史 tick 播放不带深度；录制深度还要求相应 Level II/SuperDOM/FX Pro 窗口接收数据。INT03 需验证实际版本和提供商覆盖。
- MultiCharts 购买页可访问；功能正文与 `.NET Programming Guide v1.1` PDF 未成功获取，直接 HTTP 请求还出现 DNS 解析失败。页 50 的 Bar Magnifier 信息仅来自官方 PDF 的搜索索引；不记作全文或页面图像阅读。TradeStation 价格页同样只保留官方索引级证据。
- LEAN 核读提交：`705b9551be1aaa821c7f77896a7eb8fcd07b92ee`。`EquityFillModel.cs` 阅读 MarketFill 及 private LimitFill 的相关路径（该副本约 124–178、406–474 行）；`VolumeWeightedAveragePriceIndicator.cs` 阅读加权构造、ComputeNextValue 与代表价实现（约 71、100–114 行）。文件 SHA256 分别为 `7f8c0e35eb538f5a63184c9b5ef4b32886e2c7779ccce1e773229a1a1ec18232`、`c4671282b17bfce9bc1cf85d6739dd732a7415b13ab73e340d277de699b0371d`。这些是源代码事实；未编译运行，不能推广到所有 fill model、VWAP 类或未来提交。
