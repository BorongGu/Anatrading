# 单事件六槽原价核对

2026-10-13。基线 70f68ef1dcb33fe45e895b01ea8861446d648bc9。编码前 r2 独立设计审查 GO 已获接受，准入仅覆盖本地最小 UI。实现和独立代码验收仍待完成。

## 研究依据与实际阅读

前置调研实际阅读 TradingView 官方 Strategy Report: How to start（https://www.tradingview.com/support/solutions/43000764138-tradingview-strategy-report-how-to-start/）的 Metrics、Performance analysis、Trades analysis、List of trades，以及 Date and price range drawing tools（https://www.tradingview.com/support/solutions/43000516996-date-and-price-range-drawing-tools/）的 Application/样式范围段。本实现阶段读取该调研记录，不冒称重新阅读或复现论文。竞品已有路径/交易明细，六槽收盘不能替代执行模型。

实际源码阅读：SingleResearch、research-types、research-model、event_study、group-endpoint-model 价格规则与现有测试；设计阶段另核 App/adjacent-source 只读消费。没有新估计公式；只按既有事件 index 提取 i..i+5 原值，比较字符串与原账本整数计数，不计算价格变化。

B0 为原事件表、原图、原记录和相邻详情；B1 为仅连接原图。B1 不能完整提供六槽和原统计归属，且原图查询范围与研究前缀不同。本项仅省去手工关联，未证明效率或金融增量。

## 规格与审查

详见同编号 design、concepts、acceptance、design-review。概念卡不是完整 DTO；测试须构造并通过未修改的 shared validator。R1 收敛到只读发布报告＋每次接受新令牌＋独占六槽冻结投影；R2 重叠案例移至合法 index21；R3 明确估计重置及注入/畸形分类。最终 r2 已关闭三项问题。

## 不变项与停止线

仅 h5、最近100事件、一次一条。无新增数据请求、Store、后端修改、源定位回调、完整账本分页、极值、百分比或价格运算。原 selected、partition、label、evaluation、统计、基线与 shared validator 均保持。日期组步数不代表交易日，响应保留价不认证 OHLC/复权/历史可得性/成交。

实现验证待记录；真实浏览器、Windows、真实来源与金融效果不视为通过。

## 首轮实现与验证（2026-10-13，待独立代码验收）

- 已实现单事件六槽的独占冻结投影；源报告保持可写属性描述符，不在产品内原地修改。每次接受独立令牌，选择随参数/请求/上下文失效。只读约定见 `single-event-path.ts` 与 `SingleResearch.tsx`。
- 独立构造的 34 份完整合成响应使用未修改的 Python `signal_report`，正常案例包括实际产生的所有事件与计数。Kalman 案例明确为一次估计故障注入；畸形用例另行变更字段。全部先通过未修改的 `assertResearchReply`，没有类型断言绕过。测试 fixture 用基准 JSON＋字段补丁减少重复，恢复后仍是完整 DTO。
- RED：产品模块存在前，冻结词法测试因缺失模块失败。之后补完整 DTO、畸形、投影/身份与服务端静态渲染回归。首次静态渲染断言错误地要求 React 文本注释分隔，修正测试为实际纯文本后通过，未改产品掩盖失败。
- 受影响 Node 82/82 通过；最终完整 Node 849/849 通过（包含 graphQ/request-cutoff 回归）。TypeScript＋生产 build 通过，保留既有大 chunk 告警；`git diff --check` 通过。
- 本阶段没有执行真实浏览器或本地服务，未宣称布局/真实键盘浏览器验收。独立 jsdom 中断/迟到/重试/同对象接收/关闭焦点/分段/原 DOM golden 验收仍待最终不可变提交执行。jsdom 通过也不等于真实浏览器通过。
- 后端与共享 validator 零改动。独立纯合成 API/内核 golden 对照仍待审；本实现者未跑 Python 全量测试，不将“未修改”写成“已通过”。Windows、真实来源、性能与金融效果未验收；不存在源数据或预测资格升级。
- 本地提交仅用于独立审查，未推送、建 PR、合并或部署。
