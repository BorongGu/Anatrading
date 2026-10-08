# 015 · 单根 K 线几何、精确表示与可识别边界

研究日期：2026-10-08。用途：为单快照、单根源 OHLC 的确定性描述提供编码前依据；本文件不解冻业务代码。后续合同须经过独立反方审查与决策记录。真实数据、数学正确性、预测效力分别验收。

## 当前数据能回答什么

现有 [通达信真实日线验收](../qualification/tdx-daily-acquisition.md)记录 7,068 根日线与全字段精确对账。它证明保存/解码的源值一致；价格解释、复权、完整交易日覆盖、永久证券身份和历史可得时点仍有 unknown/assumed 项。该快照资格是 `source_evidence_retrospective_only`。

可以据同一根、同一源版本四个数计算几何，名称应为“源价差”“源收盘位置”。本功能不使用份额量、成交额、公司行动因子或跨日基线，因此它们的未知状态不妨碍这个局部描述。结果保留全部来源限定，不能据几何推定完整收盘、主动买卖方向、资金流、持仓成本、趋势或交易信号。分钟兼容需另有真实数据验收，当前日线证据不扩展为分钟证据。

## 官方文档和原作者博客

| 来源与实际阅读范围 | 资料事实 | 项目推论 |
|---|---|---|
| [StockCharts Introduction to Candlesticks](https://chartschool.stockcharts.com/table-of-contents/chart-analysis/candlestick-charts/introduction-to-candlesticks)，阅读 Formation、Long/Short Bodies、Shadows、What Candlesticks Don't Tell You、Hammer/Hanging Man 相关正文 | 实体连接 O、C，影线延伸至 H、L；同一 OHLC 可由不同高低发生顺序产生；形态解释涉及前期趋势及后续确认 | 核心输出四段几何与精确比值。单根不识别日内路径；后续确认不能回填成当时已知信号 |
| [TradingView Hollow candle charts explained](https://www.tradingview.com/support/solutions/43000745270-hollow-candle-charts-explained/)，正文全文，未观看嵌入视频 | 空心/实心依 O、C，空心柱颜色还依前一收盘 | 单根方向只比较 C、O。颜色不充当数学字段，前收盘、涨跌幅和颜色规则属于另一合同 |
| [TradingView Bar Magnifier](https://www.tradingview.com/support/solutions/43000669285-what-is-bar-magnifier-backtesting-mode/)，正文及官方示例 | 历史 OHLC 回测有柱内路径假设；更细周期数据可改变同根成交模拟 | 单根 OHLC 不承担订单先后/止盈止损可成交性证明。未来分钟复盘须明示柱内剩余不可识别性 |
| Greg Morris 本人 [Candlestick Analysis — Pattern Identification](https://articles.stockcharts.com/article/articles-dancing-2016-03-candlestick-analysis--pattern-identification/)，2016-03-02，正文全文 | “长实体”可按价格、当根 H−L、过去平均实体定义；Doji/相等判断和影线关系需要容差 | 不偷选一种阈值。首切片不输出长/短、Hammer、Hanging Man、Doji 概率；未来分类须公开公式、阈值、训练时点和定义版本 |

文档中买卖力量、反转、积累/派发等叙述属于作者解释。本项目仅采用可从 OHLC 唯一复算的部分，未验证这些叙述的 A 股决策效力。

## 3 篇 primary 论文：阅读范围与限制

### P1 · Lo, Mamaysky & Wang (2000)

[NBER 工作稿 7613](https://www.nber.org/papers/w7613)，[原 PDF](https://www.nber.org/papers/w7613.pdf)，DOI `10.3386/w7613`。实际阅读 PDF 页 2–5、14–20、24–28：摘要/导言、识别算法、检验与数据、结果正文、结论与脚注；未通读核回归证明、全表与全部图。本稿和 Journal of Finance 正式版本未逐页比对。

- **论文事实**：美国 1962–1996 数据，核回归平滑后识别多日形态；采用滚动窗口，并把识别延迟纳入未来收益起点。条件/无条件收益分布在部分市场/形态下有差异；正文明确有信息量不保证可盈利，IID 假设亦有限制。
- **项目推论**：本轮纯几何无需平滑；平滑不能改原 OHLC。未来多日识别同时记录形态完成与实际识别时刻，冻结数据版本、窗口和参数，检验样本外增量与净成本。论文没有验证本项目单根字段或 A 股策略。

### P2 · Marshall, Young & Rose (2006)

[出版社论文页](https://www.sciencedirect.com/science/article/pii/S0378426605002116)，Journal of Banking & Finance 30(8), 2303–2323，DOI `10.1016/j.jbankfin.2005.08.001`。实际只读出版社检索提供的摘要与书目；直接打开全文页面失败，未取得正文/方法附录。不能声称复核其全部 bootstrap 设计。

- **摘要事实**：扩展 bootstrap 以生成随机 OHLC，作者报告所测 DJIA 蜡烛交易策略缺乏价值。
- **项目推论**：形态流行程度与收益资格须分开；这份摘要同时不能证明所有 K 线描述均无用，也不能证明 A 股存在或缺少同样效果。本轮不照抄其交易参数。

### P3 · Goo, Chen & Chang (2007)

[出版社论文页](https://businessperspectives.org/journals/investment-management-and-financial-innovations/issue-67/the-application-of-japanese-candlestick-trading-strategies-in-taiwan)，[出版社 PDF](https://www.businessperspectives.org/images/pdf/applications/publishing/templates/article/assets/1934/imfi_en_2007_04_1_Goo.pdf)，Investment Management and Financial Innovations 4(4)。实际阅读 PDF 页 2、4–8、18–19、21–24：摘要、数据/定义/检验、结论、样本名单与形态附录；未逐项复算全表、全部止损过程或附录 C。2026 封面版权字样不视为论文结果修订。

- **论文事实**：25 只台湾股票 1997–2006 日线，使用相对实体阈值、过去趋势、次日开盘进场及 1–10 日持有；报告部分策略正收益。样本筛选要求长期存在。阈值正文写取整个 1997–2006 分布，紧接一句又称检验前样本外；本轮无法消除这一时点矛盾。
- **项目推论**：长期存续选择、阈值时点、形态/持有期多次检验、成本和止损实际路径须独立审计。该正面结论与 P2 摘要的不同样本结论不能投票合成 A 股买卖评分；不导入其阈值或停损收益。

两份成功下载的 primary PDF 仅保存于被 git 忽略的 `artifacts/research/candle-geometry-20261008/`；SHA256：Lo `9d77565a9eecebc63075dd445062e85e7e215ecbbdbd1cbb34a8553d8cb8d3f2`，Goo `f1c123f7c958f70285e4bb712ceee92d097f05621d7065c3d752194875061dd9`。抽取文本仅供上述阅读范围核对，未将论文或行情原件提交公开仓库。

## 建议数学合同

记同根四个有限十进制数为 `O,H,L,C`，先要求 `L <= O <= H`、`L <= C <= H`、`L <= H`。不通过时整根不给几何值，返回可定位的异常；禁止交换 H/L、截断负影线、把缺失补零。价格为正、停牌、涨跌停或 tick 大小均不能只凭几何确认；是否拒绝零/负价由既有来源/品类合同决定，不新增猜测。

| 描述字段 | 公式 | 可证明范围 |
|---|---|---|
| `range` 源高低价差 R | `H-L` | `R >= 0` |
| `body` 源实体长度 B | `abs(C-O)` | `0 <= B <= R` |
| `upper_shadow` 上影长度 U | `H-max(O,C)` | `0 <= U <= R` |
| `lower_shadow` 下影长度 D | `min(O,C)-L` | `0 <= D <= R` |
| `body_direction` | `C>O: up; C<O: down; C=O: equal` | equal 只证明实体长度零，价格仍可能波动 |
| 实体/上影/下影占比 | `B/R, U/R, D/R` | R>0 时各在 `[0,1]`，三者和为 1 |
| `close_location` 源收盘位置 | `(C-L)/R` | R>0 时在 `[0,1]`，表示几何位置 |

必须验证恒等式 `R=B+U+D`。`range` 不称振幅百分比，`body_direction` 不称对昨收的涨跌方向。收盘位置不称买压/资金流；若将来需要 `2*close_location-1` 的传统 Close Location Value，应以另一明确字段定义，避免同名异式。

**零 range**：合法 OHLC 顺序与 `H=L` 联合推出 `O=H=L=C`；四个长度都为 0，方向 equal。所有除 R 的比值为空，原因 `zero_range`，不返回 0、0.5、1 或 NaN。零实体且 R>0 时，实体比值可以为 0，其余比值正常。

**不可识别性独立反例**：`O=10,H=12,L=9,C=11` 可来自 `10→12→9→11` 或 `10→9→12→11`。相同几何对应不同的高低先后，无法判定 11.5 限价/止价与 9.5 止损的发生顺序。OHLC 更无法给出各价格成交量、全部往返次数和主动方向。展示高低连接线时不补造柱内轨迹。

## 建议精确表示合同

[Python Decimal 官方文档](https://docs.python.org/3/library/decimal.html)，实际阅读概述、构造精度、`as_tuple`/`as_integer_ratio`、Contexts、round-off 与 FAQ 相关段落。Decimal 字符串构造可保留输入，算术仍受精度/舍入/指数上下文约束；例如循环比值 `1/3` 没有有限的精确十进制表示。把数据类型写成 Decimal 不能自动保证派生值精确。

1. 输入采用既有源 Decimal/十进制字符串，拒绝 NaN/Infinity、缺项及浮点中转。维持现有输入长度/精度/规模上限；极端指数不得直接制造无限大的对齐整数。
2. 长度建议将已限定输入的 Decimal tuple 对齐到同一十进制指数，以整数做减法/绝对值/比较，再构造精确十进制字符串；不依赖调用者的全局 Decimal context。若改用局部 context，须由输入位数与指数跨度推导足够精度，并开启 Inexact 等检查，不能随意固定 28/38/50 位或使用无限精度。
3. 比例权威值采用约分有理数 `{numerator: "整数", denominator: "正整数"}`；分母不能为零，零分子规范为 `0/1`。字符串避免 JS Number 大整数损失。整数分子/分母可从相同对齐尺度的长度直接取得，经济单位无需猜测。
4. 百分比小数若仅用于显示，单独声明显示位数、舍入规则与“近似显示”；不替代权威比值，不写回原值/规范 Decimal 列。首 CLI 可以直接输出分数，避免新显示层。
5. 字段证据绑定快照、raw hash、源行定位、OHLC 原 token、源解释与方法版本。固定来源版本时逐根函数不得读取后续行；追加未来行不改变旧结果，修订原件产生新版本。

上述是研究建议，最终 JSON 结构、异常输出、输入边界与解冻文件以经反方闭环的实施合同为准。

## 独立验收预期

- 手算 `O=10,H=12,L=9,C=11`：R=3、B=1、U=1、D=1、方向 up；三个占比各 `1/3`，收盘位置 `2/3`。交换 O/C 后方向 down、收盘位置 `1/3`，各长度不变。
- 手算 `O=C=10,H=12,L=9`：R=3、B=0、U=2、D=1；比例 `0/1,2/3,1/3`，收盘位置 `1/3`；零实体不等同零 range。
- `O=H=L=C=10`：四长度 0、比例空并说明 zero_range；H<L、O/C 越界、缺项/非有限数分别拒绝。真实异常不删除原行。
- 混合小数位、高位整数、循环比值和外部低精度 Decimal context 下，结果与独立有理数手算一致；不允许发生静默舍入。
- 正比例共同缩放保持比例，四个价格共同平移保持价差/比例；此数学不变性不授予供应商复权一致性资格。
- 原快照真实 7,068 根应独立逐根核 OHLC/定位、几何恒等式和比值；失败可定位且不改原件。重复执行、追加未来行及替换来源版本测试分别验证确定性、前缀不变性和版本隔离。

本轮没有开展 A 股净收益实验。未来形态、趋势、量价、波动率与去噪分析继续保留独立研究/数据时点/样本外验收，不以此局部数学切片宣称已经超越竞品。
