# 公司行动源记录的区间标记

2026-10-09。数据层反方评审已完成。目的：在日线复查旁显示原始权息记录，帮助识别跨日价格、数量比较可能受到的口径影响；本功能不改价量、不复权、不推断收益归因。

## 阅读依据

- [通达信get_divid_factors](https://help.tdx.com.cn/quant/docs/markdown/mindoc-1ctuhthaq5qmg/mindoc-1h10hsiat36k4.html)：研究agent读取完整接口页。Type1除权除息、11扩缩股、15重新调整；四数值字段与源Date保留。Type11/15具体经济含义、单位和各类Date解释未提供完整合同。
- [StockCharts价格调整](https://help.stockcharts.com/data-and-ticker-symbols/data-availability/price-data-adjustments)：完整阅读。拆分会同时影响历史价量尺度，分红调整与实际成交价不同；该软件的unadjusted仍校正拆股，分钟数据始终复权，不能与本地未核复权原件直接视为相同口径。
- [QuantStart Understanding Equities Data](https://www.quantstart.com/articles/understanding-equities-data/)：本轮正文获取失败，仅阅读搜索可见的拆分、股息调整段落，不记为全文阅读。这里只采用保留动作记录、显式区分原价与调整价的数据原则，未照搬海外现金/股份规则。
- [MacKinlay1997](https://www.bu.edu/econ/files/2011/01/MacKinlay-1996-Event-Studies-in-Economics-and-Finance.pdf)原先已读取刊页14—18；[Kothari/Warner2006-05-19稿](https://www.bu.edu/econ/files/2011/01/KothariWarner2.pdf)本轮重新读取§3.1—3.3。标注源日期本身不构成异常收益模型、经济归因或有效统计推断。
- 发行人实施公告：研究agent已读[600059的2026-06-24除息](https://stockmc.xueqiu.com/202606/600059_20260616_P40E.pdf)、[000001的2026-06-12除息](https://disc.static.szse.cn/disc/disk03/finalpage/2026-06-05/bde1eece-e914-4a31-a51d-5de619feb208.PDF)、[920002万达轴承的2026-05-27派息转增](https://static.cninfo.com.cn/finalpage/2026-05-19/1225316970.PDF)公告全文；主agent再次读取万达轴承公告全部3页。只用相应Type1原记录逐条核对日期和值，不外推Type11/15。

## 最小实现与反方修正

1. 用户选一个已保存的capture及显式两日期d<e，严格取d<sourceDate≤e。原d日收盘已处于d日价格状态；本区间排除d日记录。
2. 从原request/response重新解析并验SHA，固定capture、query_id及d/e为报告身份。旧report.json不作真值；不取文件自述的任意路径。
3. 未知Type、同日多条事件、重复日线均保留源ordinal。只将同日期关联到当前查询已有记录，不挑替代值；未出现对应日期记not_returned_by_query，不能据此称原来源缺日。
4. 事件Date晚于query.cutoff标outside_query_cutoff，不附到此前日线。全部标签为事后源记录，采集时点不能替代公告可得时点或PIT。
5. 区间超出capture请求范围，标range_not_requested，仍可展示原件中实测返回的记录；覆盖一直unknown。空数组只能表述未返回记录。
6. 沿用已验reference解析合同：任何坏Date、数组错位、坏数值使整份报告拒绝，并显示错误；不把错误折成无事件，不丢坏行后发布完整性结论。

验收：d/e边界手算；未知Type与同日多记录；查询重复日、ordinal缩窗与cutoff；空/坏响应；原件哈希变化；证券不匹配；三市场原始Type1记录与实施公告逐字段核对。既有查询与指标保持原结果，动作记录不能改变筛选分组。
