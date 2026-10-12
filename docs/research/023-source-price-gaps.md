# 源 K 线缺口与后续边界观察

2026-10-09。研究及数据算法反方闭环，无未关闭阻断。该功能帮助复盘跨柱价域空档；输出来源数值描述，不提供买卖评分或默认回补概率。

## 编码前阅读

- 主 agent 完整读取 [AmiBroker GapUp](https://www.amibroker.com/guide/afl/gapup.html)、[GapDown](https://www.amibroker.com/guide/afl/gapdown.html)：严格使用当前最低价大于前柱最高价、当前最高价小于前柱最低价。
- 主 agent 和研究 agent 读取 [TradingView Gaps](https://www.tradingview.com/support/solutions/43000675999-gaps/) Definition、Inputs 全文。其默认包含宽度过滤，且关闭 partial 选项时，稍微进入缺口即可结束整个绘图区域；绘图关闭不能充当本项目远端达到的定义。
- 主 agent 读取 [StockCharts Gap Analysis](https://chartschool.stockcharts.com/table-of-contents/chart-analysis/gaps-and-gap-analysis) 定义、时间尺度、四类及回补正文；研究 agent 另读 [Gap Trading Strategies](https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/gap-trading-strategies) 定义与 Full/Partial 部分。前页使用整柱价域，后页 Full Gap 使用开盘越过前高/低，不能混用。除息、低流动性可能影响图形；事后突破/持续/衰竭分类不得回填为形成时已知属性。
- 研究 agent 读取 [通达信公式实例](https://help.tdx.com.cn/gspt/docs/markdown/tdxgs-1d1olc9o6k8n8/tdxgs-1d1om6jqglcas.html) 的高低开、跳空、两天未回补三节。实例的高开、向上跳空及后续低价保持采用不同字段比较。
- 研究 agent 读取 Adam Grimes [Managing Gap Openings](https://www.adamhgrimes.com/managing-gap-openings/) 主体全文。背景与交易时段值得分别观察；文中没有完整数据和统计设计，不能认证回补概率。
- Aiche/Cohen/Griskin，[Stocks Opening Price Gaps and Adjustments to New Information](https://pmc.ncbi.nlm.nih.gov/articles/PMC10017064/)，DOI 10.1007/s10614-023-10363-w：研究 agent 经 PMC/Europe PMC 取得正文，读引言定义、Research Design and Data、Results 表1–4及结论。2010–2019约2600只美股，按开盘相对前高低/前收盘定义，研究开到收漂移。没有核定本项目 A 股整柱缺口的成本后预测价值或时点证券池。
- Abidou 2019，[Filling Open Price Gap on Intraday Timeframe](https://www.iosrjournals.org/iosr-jef/papers/Vol10-Issue5/Series-2/C1005021418.pdf)，DOI 10.9790/5933-1005021418：研究 agent 取得5页，读pp.15–17方法、公式、结果、结论及p.18引用。首分钟高低与前日高低的定义不同于全天价域；正文总体与分桶回补比例存在未解释的不一致，不采纳其比例及阈值。
- Gu等，[订单簿 price gaps](https://arxiv.org/html/1405.1247)：研究 agent 读§1–2及式(1)。26只深市股票的订单簿相邻占用价位对数差需要订单流数据，不能由本功能日线或分钟 OHLC 还原。
- 研究 agent 读取 [TradingView strategy broker emulator](https://www.tradingview.com/pine-script-docs/concepts/strategies/) 柱内路径假设部分；本功能不采用假设高低先后，不推定触及秒数、逐价成交或订单执行。另查中国指数缺口论文10.1007/s10690-024-09461-y仅有摘要，不用于实施结论。

## 冻结算法

1. 支持现有1d/1m快照，按可定位标签排序并保留所有源序号。p是上一可定位标签组。重复标签、缺失或无效OHLC不挑行、不跨过；下一 valid-valid 配对可以恢复形成观察。
2. 开盘差独立计算 `O(d)-C(p)`。严格上缺口 `L(d)>H(p)`，边界 `[H(p),L(d)]`；下缺口 `H(d)<L(p)`，边界 `[H(d),L(p)]`；相等无正宽缺口。所有严格正宽保留，不偷偷套软件过滤阈值。
3. 形成记录仅来自当前所选源行；缩窗前一柱由同快照上下文提供。后续观察使用完整来源上下文，终点是所选最大标签与cutoff的较早者，排除形成柱本身；ordinal_end之外更晚标签不得参与。
4. 上缺口 near/far分别为后续 `L<=upper / L<=lower`；下缺口为 `H>=lower / H>=upper`。分别保存所见首次的标签、源序号、极值、等于/越过以及是否包含该边界。两事件可同柱，柱内先后未知。
5. 后柱整段跳到区间之外标 `passed_without_overlap`。即使范围重叠，也只证明源极值达到/越过阈值，不能证明区间每个价位成交。界面使用“源极值近端/远端达到”，不把这类记录称完整成交回补。
6. bad/dup中断所有待观察事件；已经发生的事件保留，未发生部分不再从后续填成首次。无定位记录保持原序号；存在时显式标相邻可定位源柱/所见首次的完整覆盖未知，不能认证全量时间序列首次。
7. 价差用既有 exact_sum 和 Decimal 字符串；堆排序用 copy_negate，避免全局 Decimal context 对负号运算舍入。4个堆分别记录方向与near/far，每事件最多弹一次，整体O(n log n)。形成身份绑定快照和源配对，后续可追加事件；固定cutoff结果稳定。

价格尺度、复权可比性是假设；日历、覆盖、闭合、历史可得时点及柱内路径未知。原始价缺口可能受到公司行动影响；现有公司行动区间标记供形成段(p,d]、观察段(d,asof]单独核对，不改变价量或完成归因。

## 开盘分界的来源价差与论文测量边界（2026-10-12）

本轮静态查重确认：在唯一、完整 OHLC 合格且同一来源配对下，既有开盘差 `O(d)-C(p)` 与实体长度加方向，已经能区分相同收盘净变下的两段方向和源价差；本轮不新增重复入口、字段或算法。仍需跨既有区域核对，并按实体方向恢复第二段符号；没有据此宣称同屏分解或交互效率已验收。

令 `P=C(p)`，`O=O(d)`，`C=C(d)`，同一配对的精确源价差满足 `(O-P)+(C-O)=C-P`。三端点为正时，各段按自身起点计算的相对变化须按 `(O/P)*(C/O)=C/P` 合成，不能直接把两段百分比相加。`source_gaps` 的 p 是前一可定位标签组；日线 `research_series` 还保留源日期可读的 unlocated 坏组，两者实际前序和计算资格可能不同。联合核对须确认同一来源版本、可见查询绑定及各自合法上下文、截止、实际 p/d 日期和源序号；不能拼接不同端点的非空值。gap 已披露 unlocated 覆盖未知，本轮记录该边界，未修改其配对规则。

原研究的分界价也不等同于来源日线 open。本轮定向阅读以下原研究相关定义，未完整复现数据、估计或预测结果：

- [Lou、Polk、Skouras 的 2018-02 作者稿](https://ifr.hkust.edu.hk/uploads/upload/files/20250212/445bce5ab83ffca69c4fe4b56c8055e1.pdf)，重点为 §3 正文页7–8：分界用 9:30–10:00 的成交量加权均价（VWAP），再由含公司行动调整的全日回报和日内回报反推另一段。该前段包含开盘后的交易，不能解释为纯非交易时段；缺开盘时延持至下一可得开盘改变了持有区间，本项目不得把该未来端点回填为原日已知 open。
- [Berkman 等（2012）期刊原文 PDF 镜像](https://scispace.com/pdf/paying-attention-overnight-returns-and-the-hidden-cost-of-52o3bohkjq.pdf)，定向读取刊页719–720及相关脚注：分界用 9:30 后首个有效买卖报价中点，收盘用 16:00 前最后有效中点，并处理公司行动。其包含随后收盘与全期覆盖的回顾性筛选，不能当作开盘时已知资格。
- [Qiao、Dam（2020）高校库正式出版 PDF](https://pure.rug.nl/ws/portalfiles/portal/132141807/1_s2.0_S1386418120300033_main.pdf)，定向读取摘要、§1–2和表1定义：主分析为大陆上证综指、深证成指日频样本。美国个股研究与大陆指数研究均不直接证明本项目 A 股个股的预测或交易效果，也不补齐逐股公司行动、来源分界定义和历史可得性证据。

纸面反例：两套成交均每笔1000股。A 为 09:30@100、09:45@104、11:00@98、16:00@101；B 只交换 09:45 与 11:00 的价格。两者日线均为 `O=100,H=104,L=98,C=101`，总量4000股、总额403000，前30分钟 VWAP 却分别为102和99。若另假定无公司行动、前收盘100、全日回报1%，以这两个 VWAP 分界的论文式两段方向也相反。日线 OHLC 连同总量、总额仍不能还原该 VWAP；完整成交序列也不唯一决定买卖报价中点。此为纸面算术与可识别性反例，未运行实验。

来源邻接不自动等于上一交易日或真实隔夜。缺少日历、覆盖、分界定义、价格口径和历史可得性证据时，只解释来源价差，不升级为经济归因、行为主体识别或预测信号。本次补充仅做静态核对与定向文献阅读，未运行产品、测试、浏览器或真实行情验收；下节保留原功能的历史验收记录。

## 验收

严格/相等边界、独立开盘差、形成柱排除、近端仅触碰、部分进入、近远同柱、整柱跳过、bad/dup中断、无定位限定、缩窗前一柱、cutoff与ordinal_end不借未来、低精度context和稳定形成身份。真实沪深京原始.day以UInt32分字段独立扫描对照；实际分钟接口十进制token以Fraction独立扫描对照。新增功能仅作为复盘描述发布，预测价值仍待冻结样本外实验。

已执行：120项相关后端回归、43项前端用例和TS/Vite构建通过。实际HTTP逐项对照600059.SH的7069根日线（195个缺口）、000001.SZ的8465根（452个）、920000.BJ的1254根（38个），以及600059.SH的720根分钟（14个）；全部源字段、首次near/far位置、跳过区间分类与独立原件扫描一致。缩窗保持前序来源与事件，2026-09-04截止排除了后来的9月14日观察；原查询未变化。4份真实HTTP报告通过前端身份/范围校验，服务资源字节与本次构建一致。私有证明保存在D盘artifacts/qualification/unit-reconciliation/source-gaps-workbench-check.json，未提交行情。GUI点击/下载交互尚未验证，不以HTTP和构建结果替代。
