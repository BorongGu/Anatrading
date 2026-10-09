# 当前来源池的日线条件筛选

2026-10-09。研究与数据算法反方已完成；沿用已有价格通道、前期源数量比与收盘路径效率，全部条件按 AND 连接。功能只定位可复查的图表，不生成收益评分或买入建议。

## 已阅读依据

- [StockCharts Planning Scans](https://help.stockcharts.com/scanning-and-alerts/scan-writing-resource-center/planning-scans)：证券池、技术条件章节；[Writing Scans](https://help.stockcharts.com/scanning-and-alerts/scan-writing-resource-center/writing-scans)：AND/OR；[Advanced Scan Workbench](https://help.stockcharts.com/scanning-and-alerts/technical-scans/advanced-scan-workbench)：历史日期选择、运行。单次指定日期，盘中日量尚未完整；历史日期选项不证明历史证券池资格。
- [TradingView RVOL](https://www.tradingview.com/support/solutions/43000635874-how-do-we-calculate-relative-volume-and-relative-volume-at-time/)全文与公式：普通量比排除当前柱、默认前10柱；同槽版本用前10日同5分钟槽。本功能采用已有模块及显式N，不声称产品口径完全一致。
- [Sullivan、Timmermann、White 1999](https://www.kevinsheppard.com/files/teaching/mfe/advanced-econometrics/Sullivan_Timmermann_White.pdf)：引言、§I、§III部分、§IV样本划分。全规则集合的检验需考虑选择和依赖；看结果后修改参数不能获得独立验证资格。
- [Brown等1992](https://terpconnect.umd.edu/~wermers/ftpsite/FAME/Brown_Goetzmann_Ibbotson_Ross.pdf)：§1及§2模拟、Table5，PDF9—18页。生存筛选可在无原始持续性的模拟中制造表面持续性；其数值不迁移为A股偏差估计。
- [Harvey、Liu、Zhu 2016](https://people.duke.edu/~charvey/Research/Published_Papers/P118_and_the_cross.PDF)：§3.2—3.3、Table2、FWER/FDR，PDF7—11页。未来有效性研究需完整记录尝试集合；当前描述性筛选不计算显著性。

## 实现口径与反方修正

1. 明确选定采集run，相同源pool哈希且处理范围不重叠；每只证券绑定原outcome的snapshot和raw哈希。保留全pool、已处理、缺缓存、未处理等分母，部分采集不冒充完整覆盖。
2. 显式source_date，目标日恰有一条日期记录；缺日、同日重复分别不可评价，不用较早末日替代。当前pool的历史回顾可能有幸存者和样本选择偏差，PIT未知。
3. 先按不同源日期选槽，再检字段；保留槽内重复/坏值。通道和量比排除当前日；ER含当前日，需要N+1日期。扫描全文件日期，再只解码所需记录，恢复原ordinal；用完整Store查询作等价验证。
4. 通道筛选用close_relation，盘中high越界不等于收盘above。量比与ER按精确Fraction比较，四位显示不参与判断。ER无方向信息，另设up/down/flat条件；平坦路径按已有明确0约定处理。
5. 启用条件缺值标不可评价，保留每项true/false/null；未启用指标缺值不阻其他条件。无条件结果明确标“无条件数据记录”。价格坏值不阻仅需数量的规则。
6. 可读日期在目标日之后的记录先排除，未来价格坏值不影响过去。不可读日期无法确认在窗口外，保守标date_set_integrity_unknown；不对无日期追加承诺前缀不变性。
7. 同源日期不等于同步捕获；复权、数量单位、股本口径、闭合、历史可得时间仍未知。跨日指标保留同尺度/同口径条件资格，不据筛选通过宣称预测价值。

验收：独立手算、精确阈值边界、独立字段缺失、目标日不替代、重复槽、可读未来追加、真实三市场原件与完整查询等价，以及完整5579源池的独立整数/Fraction核查。
