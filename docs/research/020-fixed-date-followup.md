# 固定筛选日的后续源收盘观察

2026-10-09。研究与数据算法反方已完成。目的：在冻结条件、来源池、快照与两日期后，观察匹配组和其余可评价组的分布差异，为后续预定日期研究提供输入。

## 阅读依据

- [MacKinlay 1997](https://www.bu.edu/econ/files/2011/01/MacKinlay-1996-Event-Studies-in-Economics-and-Finance.pdf)：扫描正文已渲染目视读取刊页14—18，§2、§3与§4部分。先定义事件、窗口及纳入标准，报告样本选择；异常收益需要正常收益模型，本功能没有该模型。
- [Kothari/Warner 2006-05-19稿](https://www.bu.edu/econ/files/2011/01/KothariWarner2.pdf)：§3.1—3.6、§4.4.2；未通读全文或声称读过2007出版版。样本特征、共同日历冲击和横截面相关性影响推断。同池其余证券没有自动成为随机或反事实对照。
- [AmiBroker Exploration](https://amibroker.com/guide/h_exploration.html)、[Ref](https://amibroker.com/guide/afl/ref.html)：报告筛选与观察列分开；正向Ref读取未来柱，不得进入原日筛选。未核得成套官方forward-return流程。
- [StockCharts Performance View](https://help.stockcharts.com/charts-and-tools/sharpcharts/chartlists/performance-view)：名单后续价格表现与基准比较，未保证以原扫描日作为统一起点。
- [Adam Grimes 2023](https://www.adamhgrimes.com/how-i-trade-part-1-of-2/)全文：统一样本识别、观察起点及基线比较；属于作者方法观点，未提供A股验证。
- [R quantile官方文档](https://stat.ethz.ch/R-manual/R-devel/library/stats/html/quantile.html)全文：本产品固定Type7，排序后h=1+(n−1)p，以相邻值线性插值。原Hyndman/Fan论文正文未读，不称Type7为该论文推荐方法。

## 口径与反方修正

1. 原d日screen_values确定eligible和matched；e>d只增加后续观察。组为matched与eligible减matched。e缺失、重复或坏值不能删除或重分原成员。
2. 两个显式日期都需唯一源Close，d的Close必须正；e的0保留为源数学变化−100%。沿用收盘独立校验，不让无关的金额、数量或开盘值阻断合法Close。
3. 变化为(C(e)−C(d))/C(d)，精确Fraction；较早末日不代替e。未复权、公司行动、历史可得、闭合与实际成交未知，不能解释为总回报或可成交策略收益。
4. 每组先保留N个成员，再报告可观察k、缺失N−k及原因。分位数、正/负/零比例的分母为k，另报k/N覆盖率。空组统计null，单值组三个分位数相同。
5. Type7插值用精确Fraction。负数显示按绝对值整数半偶舍入后加负号，舍入到0不留负零；符号计数依原分数。旧非负量比显示函数不能直接拼接负数。
6. 不计算均值、显著性、收益评分或交易成本账本；当前池历史选择、条件组非随机分配和终点缺失仍影响解释。重复日期验证须预先固定，观察后调参不构成独立确认。

验收：独立分位数手算、负数与半偶边界、空/单值组、终点缺失/重复/零、无未来值影响原分组、真实三市场完整查询对照及全源池独立整数/Fraction核查。
