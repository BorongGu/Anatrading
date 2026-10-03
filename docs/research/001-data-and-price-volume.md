# 001 · 数据精度、量价描述与 K 线复盘

调研日期：2026-10-03。编码前研究记录；事实、设计选择、效果假设分别列出。原始数据的免费获取与软件源代码开放是不同维度，不能以一个推断另一个。

## 常用软件能力对照：首轮

“已查文档”仅表示官方公开资料支持相应描述，不表示已实测客户端、套餐或导出兼容性。矩阵持续扩展，尚未完成所有常用软件及全部高级功能的覆盖。

| 软件 | 文档可确认的能力 | 复现的数据前提 / 本项目任务 |
|---|---|---|
| 通达信 | 文本导出、区间统计、公式系统、条件选股、L2 函数 [S1][S2] | 优先本地文本与原生日线；公式口径逐项核对；L2 独立数据门槛 |
| 同花顺 | 行情中心、iFinD 专题数据导出 [S3] | 普通免费客户端与 iFinD 分开；真实普通客户端导出兼容待验证 |
| 东方财富 | 列表导出、公式选股、L2 资金流 [S4] | 表格适配；不能用普通成交量重建 L2 资金流 |
| 大智慧 | DDE、逐笔、委托队列、资金分析 [S5] | 区分行情快照分笔与真实逐笔 |
| 富途牛牛 | 筹码分布视图 [S6] | 作为成本分布模型研究，实际持仓分布不可从 OHLCV 唯一恢复 |
| Choice | 数据查询与 Excel 导出 [S7] | 作为研究能力参照，不计入免费数据保证 |
| TradingView | 成交量分布、足迹图、锚定工具、脚本 [S8][S9] | 明确低周期近似、方向归因与重绘；原始与估计结果分开 |
| Sierra Chart | Numbers Bars、Volume by Price [S10] | 逐价成交量/买卖价成交量需要对应底层数据 |
| NinjaTrader | Volumetric Bars、Volume Profile [S11] | 分笔精度和方向定义是验收条件 |
| AmiBroker | 自动 walk-forward 优化与验证 [S12] | 样本外拼接、参数选择记录、成本后基准 |
| MetaTrader 5 | 多精度回测、真实 tick、前向验证 [S13] | 区分生成 tick 与真实 tick，检查成交模拟假设 |
| QuantConnect/LEAN | 事件时点、复权、动态证券池与研究验证 [S14] | 时点数据、退市样本、参数与数据挖掘偏差 |
| StockCharts | 指标定义、扫描与图表 [S15][S16] | 指标公式、初始化和单位可审计 |

下一轮待调研：Wind、文华财经、博易大师、券商 QMT/PTrade、MultiCharts、TradeStation、thinkorswim、Bookmap、ATAS、Quantower。随后按量价、形态、订单流、选股、回测、组合、预警、数据导出等功能族核查，记录收费/免费边界及实际版本。

## 功能 A：导入与数据质量

**文档/代码事实**：通达信官方展示格式化文本导出 [S1]；pytdx 原生 `.day` 解析使用 32 字节小端记录 `<IIIIIfII`，含整数 OHLC、float32 金额和整数成交量 [S17]。pytdx 向使用者展示的股票成交量换算为手，本项目内部统一为股，因此需要原始整数，不能直接套用其显示值。

**设计**：保留文件哈希、原字节、源行、编码、证券、周期、价格复权、量/额单位。日期和数值解析失败、OHLC 不等式失败、冲突重复必须拒绝；乱序可排序并记录；完全重复可去重并记录。空金额表示缺失，不能变为零。单位不明须明确指定。复权价格与原始成交额混用会破坏成交均价含义，计算应受口径限制。

**精度边界**：CSV 的显示小数位和万/亿缩写会损失源精度；`.day` 金额本来只有 float32 精度。Decimal 能保存收到的值，不能恢复软件已舍入的数据。不把金额二进制编码误差描述为分币级精确。

**验收**：实际软件来源样本；独立解码器/原文本核对；GBK/UTF-8、价格小数、手股、万/元、缺失/零、NaN、冲突重复、顺序、损坏文件。样本构造与真实导出分别记录。

## 功能 B：可解释的量能与噪声描述

**前置阅读**：Lo & Wang [P2] 讨论交易量度量；StockCharts 的 ATR 博客指出 Wilder 平滑与简单滑动平均的差异 [B1]；Kaufman ER 文档提供方向位移与路径长度的比值 [S15]；Amihud/V-Lab 用收益绝对值与成交额构造流动性代理 [P3]。

**首批定义**：

- 相对量 = 当前成交量 / 前 N 根平均成交量；比较基线不包含当前柱。分钟周期先不把相邻分钟基线称作日内季节性校正。
- 量分位 = (前 N 根低于当前量的数量 + 0.5 × 相等数量) / N。平手用中位秩；分位代表历史相对位置。
- TR = max(H−L, |H−前收|, |L−前收|)；ATR 用 N 根 TR 均值初始化，再按 Wilder 递推。没有前收的首根用 H−L，并在方法版本中固定。
- ER = |C_t−C_(t−N)| / Σ|ΔC|；平坦路径定义为 0。它描述价格路径连续性，预测能力待验证。
- 成交均价 = 金额 / 股数，仅用于金额完整、单位一致、未复权数据；与典型价加权近似区分。
- Amihud 型单期代理 = |C_t/C_(t−1)−1| / (成交额/1,000,000 元)。仅日线，明确人民币百万缩放；它无法代替盘口价差和冲击成本。

**限制（按架构预评审 PRE-01 修订）**：经来源确认的真实零成交，在非零历史参考分母下相对量为 0，量能分位仍可计算；金额/量均价在零量时无定义。缺失、停牌/非交易、源补值、零分母、预热不足分开处理，空值附原因；不裁剪真实放量；不以红绿 K 线量命名主动买卖量。原始价格的公司行动可能产生跳变，尚无因子时显式提示。分钟量能的同时间槽对照将单独研究。

**验收**：独立手算、量纲核对、平价/零量/缺失、异常值保留；任一历史前缀与完整序列计算结果相同。

## 功能 C：K 线几何与回放

**前置阅读**：Lo、Mamaysky、Wang [P1] 将图形识别形式化并在特定美国历史样本检验条件分布。其摘要不构成 A 股有效性证据。TradingView 官方披露部分足迹计算存在重绘 [S9]；QuantStart [B2] 讨论索引和参数估计产生的前视偏差。

**设计**：从 OHLCV 构建图表，精确给出实体、上下影线、区间和前收跳空。零振幅比例为空值。先做确定的几何量，复杂形态及其预测价值后续独立检验。回放截止点后的 K 线、指标、卡片及事件都应隐藏；展示已完成柱的统计，不声称可按同一根收盘成交。

**验收**：几何分解守恒、十字/平价/缺口边界、回放截止与当前卡片一致、原始十进制值可查、浏览器实际操作。

## “超越”的可检验假设

先以来源审计、口径显式化、禁止伪精度、历史前缀不变性提升研究可靠性。是否比基准更有决策价值，需要冻结研究协议后进行滚动样本外实验，纳入成本、可交易性、失效区间和多重试验。Bailey 等 [P4] 表明反复搜索策略会产生回测过拟合；单次漂亮收益曲线不足以作证。

## 来源

- [S1] [通达信功能演示](https://help.tdx.com.cn/function.html)，已读导出与区间统计说明。
- [S2] [通达信函数表](https://help.tdx.com.cn/gspt/docs/markdown/redword/functionlist.html)，已读复权/L2 字段摘录。
- [S3] [同花顺行情中心](https://q.10jqka.com.cn/)；[iFinD 版本说明](https://fthzcnc.10jqka.com.cn/thsft/iFindService/index/index/show?SEQ=62885&file=example.doc&type=noteall)，普通客户端导出仍需实证。
- [S4] [东方财富官方 FAQ](https://emdesk.eastmoney.com/pc_activity/Pages/VIPTrade/pages/answer.html)，导出及选股条目。
- [S5] [大智慧 L2 文档](https://help123.gw.com.cn/help123/index.php?_url=%2Findex%2Fsingle&post_id=10025&tree_path=0-10020)。营销预测不作为有效性证据。
- [S6] [富途筹码分布](https://support.futunn.com/topic585?from_platform=1&lang=zh-cn)。
- [S7] [Choice 使用指南](https://choice.eastmoney.com/FileDownLoad/CFTG20220217.pdf)，已查导出相关摘录，旧版指南。
- [S8] [TradingView Volume Profile](https://www.tradingview.com/support/solutions/43000502040-volume-profile-indicators-basic-concepts/)。
- [S9] [TradingView Footprint](https://www.tradingview.com/support/solutions/43000726164-volume-footprint-charts-a-complete-guide/)。
- [S10] [Sierra Numbers Bars](https://www.sierrachart.com/index.php?page=doc/NumbersBars.php)。
- [S11] [NinjaTrader Volumetric Bars](https://ninjatrader.com/support/helpGuides/nt8/order_flow_volumetric_bars.htm)。
- [S12] [AmiBroker Walk-forward](https://www.amibroker.com/guide/h_walkforward.html)。
- [S13] [MetaTrader 5 Strategy Testing](https://www.metatrader5.com/en/terminal/help/algotrading/testing)。
- [S14] [QuantConnect Research Guide](https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/research-guide)。
- [S15] [StockCharts KAMA / ER](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/kaufmans-adaptive-moving-average-kama)。
- [S16] [StockCharts True Range](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/true-range)。
- [S17] [pytdx 原生日线解析源码](https://github.com/rainx/pytdx/blob/master/pytdx/reader/daily_bar_reader.py)，仅作协议参考，未复制实现。
- [P1] [Lo et al. (2000), Foundations of Technical Analysis](https://www.nber.org/papers/w7613)，已读公开摘要；网页直连 403，全文尚待补读。
- [P2] [Lo & Wang (2000), Trading Volume](https://www.nber.org/papers/w7625)，已查摘要与出版信息；全文尚待补读。
- [P3] [NYU V-Lab, Amihud Historical ILLIQ](https://vlab.stern.nyu.edu/docs/liquidity/ILLIQ-HIST)，已读公式说明；原始论文列于页面参考文献。
- [P4] [Bailey et al., The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)，已读摘要及导言，多重试验与样本外问题。
- [B1] [StockCharts ATR 计算比较博客](https://articles.stockcharts.com/article/articles-chartwatchers-2011-12-average-true-range-comparison-shows-stockcharts-is-above-average/)，已读公式与初始化讨论。
- [B2] [QuantStart: Should You Build Your Own Backtester?](https://www.quantstart.com/articles/Should-You-Build-Your-Own-Backtester/)，已读前视、非平稳和成本讨论。

本文为研究摘记与独立设计，没有复制第三方产品代码或宣称发现可盈利策略。
