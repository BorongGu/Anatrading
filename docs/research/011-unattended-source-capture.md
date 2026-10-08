# 011：自动获取、源版本与发布终态

2026-10-08。本轮是采集接入，无新增交易指标；沿用并重新阅读 [008 的供应商／博客／论文研究](008-acquisition-and-revisions.md)，以及 [003 量额可识别性](003-volume-microstructure.md)、[004 数据有效性](004-data-validity-and-evaluation.md)。不将自动化便利当作预测效力。

- 通达信官方 [refresh_kline](https://help.tdx.com.cn/quant/docs/markdown/ctx.stock.md/mindoc-1h10fh9m6recg.html) 与 [本机 HTTP](https://help.tdx.com.cn/quant/docs/markdown/mindoc-1hdhbmi50d038.html)：此前阅读与本机真实日线已证明可定向补缓存，本轮页面抓取超时，不能新增当前开放时间／费用承诺。固定安装 SDK 的源码和指纹继续约束兼容，不执行 SDK。方法没有日期参数，采集时间预算不能限制其内部下载量。
- 本轮重新检索并读取供应商作者 Dan Whitnable 的 [Stock Minute Bars（2022）](https://alpaca.markets/learn/stock-minute-bars) 与官方 [Real-time Stock Data](https://docs.alpaca.markets/us/v1.1/docs/real-time-stock-pricing-data)。它们明确迟到交易可能修订柱，各字段成交过滤可不同。推论：保存原件与不可变版本，完成时钟不能替代源完成/覆盖；其美国市场规则不迁移为通达信/A股定义。
- Croushore & Stark（1999）的 real-time vintage 数据研究及 FRED 时点文档已在008记录阅读页段；本轮引用已读研究，不声称重新复现论文。当前捕获时间只说明本地何时取得这一份，历史可得时间仍未知。
- 现有 `.day` 实测已显示 HTTP Volume 与原 UInt32 不同。沿用 raw bytes 与整数／精确 binary32 金额表示，不经 SDK DataFrame 转浮点，不混源修正。数据导出语义与经济单位仍待真实对账。
- 发布端现有 `asyncio.shield` 的源码事实：等待者断开不撤销写者；必须核账本/目录，网络错误不能当入库失败。采集仅走受控工作台的既有导入入口，绑定数据根，不自开另一个数据库。

落实到[U1/U2合同](../contracts/TDX_DAILY_ACQUISITION_IMPLEMENTATION.md)：单证券、有限请求、稳定原件、目标日期观察、唯一写者、回执未知停止。尚无分钟成功数据、连续日常更新/全部历史覆盖或新预测效果证据。
