# 程序化交易接入设计决定

2026-10-08。采用[接入方案 v0.1](PROGRAMMATIC_TRADING_ACCESS_PLAN.md)作为候选路线与阶段门槛，依据[独立反方评审 014](../reviews/014-programmatic-trading-access-review.md)。本决定接受设计文档，交易产品代码继续冻结。

审查身份固定：方案 SHA-256 `6cd1d76b32923833084c73c3e89a2df762ca77012a177ce8fc008054cf16ca91`；[研究记录 010](../research/010-programmatic-trading-access.md) SHA-256 `9a773f5b478753b96142defd78ac21f088b2b165ac4d62e93801f3bc495401fe`。不改动已冻结的总体架构和既有数据合同。

优先保留 Anatrading 独立运行目标。GWT 客户端内 Python 策略是待用户选择的候选；独立交易 API 仍需长城证券正式确认。阶段 B 尚缺运行位置选择、账户测试权限及可运行版本。当前不创建交易 adapter 或两端通信桥，不进行资金绑定、协议确认、柜台转换或订单操作。

反方两项 P2 纳入下一份具体实现合同：区分券商测试回报与本地故障注入；固定接口确认日期、客户端／SDK／Python 版本、运行位置、测试环境和账户权限。证据齐备后，明确可改文件、模拟闭环及失败案例，再经独立反方评审后编码。

阶段 A 的后续证据见[本机验收记录](../qualification/tdx-installed-client.md)：AMD64 程序与监听归属已核，本地 HTTP 两次真实请求可达，但实际日线为空。文件／传输通过不能提升为数据或交易验收通过。
