# 分钟标签聚合与高周期复盘

2026-10-09。编码前研究及数据算法反方结论；只聚合已有源值，保留完整目标中的多周期、采样敏感性与决策效果验收。

## 定义与实际阅读

- [通达信成交均价（分钟）示例](https://help.tdx.com.cn/gspt/docs/markdown/tdxgs-1d1k7biu16p6s/tdxgs-1d1oq8nmgnm20.html)：研究子agent全文核读。首1/5/15/30/60分钟标签分别为09:31/09:35/09:45/10:00/10:30，支持开市锚定的末端标签候选。示例不能证明每条源记录实际交易区间。
- [TradingView跨周期](https://www.tradingview.com/pine-script-docs/concepts/other-timeframes-and-data/)：主方与研究agent读lookahead、历史/实时行为及避免重绘段；agent另读[Time](https://www.tradingview.com/pine-script-docs/concepts/time/)的time/time_close与尾柱例子。高周期形成值与确认值须分开，不能将最终高周期值回填给更早分钟。
- [LEAN时间聚合](https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/consolidator-types/time-period-consolidators)：主方及agent读TradeBar的锚点和交付；agent另读[Market-hour-aware](https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/consolidator-types/market-hour-aware-consolidators)主体。普通小时默认整点、可显式改锚点；开市锚定与闭市排除不能直接证明午休处理。
- Backtrader作者[Resampling博客](https://www.backtrader.com/blog/posts/2015-08-23-data-resampling/data-resampling/)及[Replay博客](https://www.backtrader.com/blog/posts/2015-08-25-data-replay/data-replay/)：agent读前者主体/代码，主方读后者主体与形成柱例子；agent读resamplerfilter.py的参数、last和调用路径。形成中的高周期可随低周期追加变化，数据结束输出的柱也不证明网格完整。
- [Sampling论文](https://swh.princeton.edu/~yacine/sampling.pdf)，Aït-Sahalia、Mykland、Zhang (2005)：agent本轮重新取得原文，读PDF5–6、8–11页的观测模型与方法；[Two Time Scales](https://www.princeton.edu/~yacine/twoscales.pdf)，Zhang等 (2005)：读§1.2、PDF4–6页§2.1–2.3及§4开头。粗采样有噪声与离散误差权衡，估计对象是积分波动率；未验证本工具方向预测或最优周期。既有003的论文边界仍保留。

## 数据算法定案

一个快照、一个所选查询；仅1m。目标5/15/30/60分钟。固定已有600059真实来源模板09:31～11:30、13:01～15:00，两个120标签段独立重置。每M个固定时钟标签一桶，首5分钟为09:31～09:35；窗口从09:33开始也不重新锚定。

仅所选源行参与，不补上下文；每个观察日期在最早至最晚所选模板槽之间保留空桶，午休与不存在的日期不造桶。缺槽写“不在所选记录”，不能推断原件缺失。段外与无法定位行独立保留。截止点只允许所选标签及显式cutoff之前的成员；未到名义右端的桶仅为部分观察，不进入完整聚合图。

每桶保留固定期待标签、全部原ordinal/label、缺槽/重复与逐字段失败原因。OHLC首开、最高、最低、末收；数量用整数相加，金额用精确Decimal相加。没有成员时返回空值；完整真实零值相加为零。缺金额仅关闭金额，不关闭合格价格或数量。重复标签不自动去重。未知时钟但可定位日期的行使该日期成员覆盖未知；日期也未知时影响全部桶。保留已定位子集描述，完整值不授予。

派生桶有自己的稳定ID（方法、快照、周期、名义末端标签），报告绑定query_id；不伪造原行或Store Query。网格齐全仅表示固定快照内所选模板成员齐备，交易覆盖、实际闭合、时点可得、价格/量口径及竞价归属仍独立未知。不得把图更平滑或波动减少称为去噪成功。

## 验收

先写缺槽、重复、部分窗口、未来截止、非法数值和全零等用例；独立手算首末/极值/守恒，低Decimal上下文不得损精度。固定快照已齐备桶的内容与坐标ID在追加未来可定位行后不变；部分桶按当时观察更新，完整报告ID绑定所选查询。界面显示精确字段与原始成员，并导出JSON；图中空桶保留间隔，未来名义结束桶不提前显示。

真实验证使用冻结720条1m原响应，独立Fraction Oracle核四种周期、每行唯一归属、上午/下午量额守恒、午休和裁剪截止；另验证真实HTTP工作台查询与原数据未变。2026-10-09直接5m读取HTTP200/ErrorId0但返回Value=[]，本地LC5不存在；本轮无法证明供应商5m一致性，保留后续真实高周期对账。研究与数据反方均无须新增工程审核文档。

## 当前实现证据

新增核心/API测试19项通过；相关后端185项、全部前端55项及TypeScript/Vite构建通过。真实来源720条按5/15/30/60分钟分别形成144/48/24/12桶，源数量总和325909500、源金额377847.25在各周期及上午/下午段守恒。独立反方按原始HHMMSS和各段起点重新构造桶键，核标签、成员、首末/极值与全部字段；已将独立标签与60分钟固定右端断言加入真实用例。

实际运行HTTP验了全窗口、09:33/11:30/13:01截止及源ordinal3～5裁剪，成员不借未来、完整桶不重锚、原查询全部保持不变。私有证据在D盘`artifacts/qualification/unit-reconciliation/minute-aggregation-workbench-check.json`。前端真实数据模型和组件SSR另核精确表值、成员链接及未来名义桶不入图；这不代替浏览器点击、下载与视觉布局验收，当前IAB浏览器不可用。高周期厂商比对及去噪/决策效果继续未完成。
