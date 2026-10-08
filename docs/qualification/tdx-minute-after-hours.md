# U3 时段变化后一分钟实测

2026-10-08。依据[观察合同v0.2](../contracts/TDX_MINUTE_AFTER_HOURS_OBSERVATION.md)及[026复审](../reviews/026-tdx-minute-after-hours-contract-review.md)，25项离线边界检查通过后执行。产品格式和schema未改变。

**结果：上海16:16之后仍未取得600059.SH分钟记录，指定缓存也不存在。** 不能用15:45提示保证历史分钟开放；不能据此认定免费接口不支持、收费、未登录、券商权限不足或14位时间参数一定错误。此前GUI时段拒绝与本次API空结果仍没有已证因果。

| 观察 | 真实证据 |
|---|---|
| 刷新 | id301，只有600059.SH／1m；完整响应ErrorId字符串0、Msg为成功文字、run_id字符串0；不作为下载完成证据 |
| 查询 | id302，1m/end_time20260930150000/count3/none/fill_data=false；外层及股票内层ErrorId字符串0，Value=[]；KlineTotal报告1，不能当实际行数 |
| 实际分钟数 | 0；没有Date/Time数组，候选截止语义仍未验证 |
| 指定cache | `vipdoc/sh/minline/sh600059.lc1` 初检及终检均明确exists=false；没有候选位型/金额/量的实际记录可审 |
| 身份 | 五次请求前后/终检观察UTC08:16:44—48，均PID25140、启动UTC03:19:49.7815869Z、同exe/SDK固定指纹 |
| 请求预算 | 2次POST终结，无重试/换时刻/换19位参数/账户/订单/SDK执行/订阅；没有产品数据库访问 |

请求/响应SHA-256：

- refresh：`9f6b28891701dde3cb77ebdf1ec3258e6c63777fd173e0de020662e3dcb0b028` / `1b01a0ea9ed6c9d3030370465071af290841f6a0ee00b39c0e2a6135dea05360`。
- minute：`7fd59e1f1a9915eb8a32470b83a010d2cfc2e9648d6da8c69da31e0ed3789ecc` / `0bb5fe94dd6ac359d26c650cd969b2ddb6f75957892c4b0c9f21bd138b28ce19`。

私有运行目录 `data/local/acquisition/20dc43a410af406aa6ba099ce2015f1c`，资格资源/脚本/测试在 `artifacts/qualification/tdx-minute-after-hours/20261008-u3`；实际脚本SHA `17765b38c6ddbcf9e4513d02bd279862034ae1adfa23b8dd05a68cd35804636b`，guard SHA `5350dc54c1cd097676324897870f49e2dde6790be1dca55f86281adf058e04ad`。这些原件均不进公开git。

共享client-global current journal写成 `refresh_unknown`，purpose明确minute_source_observation，保存前一日线current副本。既有_journal可读，ISO日期、8765产品端口和UUID路径兼容。随后实际调用日线CLI得到 `client_task_unresolved`，在同客户端身份核后停止，未追加行情POST。此为保护状态；不能把诊断成功码空返回写成已完成下载后清除。已有日线快照仍可查询，恢复新采集须新增可审的客户端任务终结／会话变化证据。

后台HTTP观察进程已终结，守卫记录逻辑exit2/failed；这是来源观察未通过，没有触发资源杀停。原生Python进程PID11364及FILETIME `134359210018050447`逐样保存，100ms观测；59样本、6.334571秒，最大原生内存计数546,193,408字节，低于120秒/2GiB。没有声称停止用户客户端任务。纯合成12.1的binary32负例仅证明既有DECIMAL(38,18)可遇scale阻断，不能当实际分钟格式已合格。

根方向用户请求当前客户端下载窗口／错误提示文字，以区分可观察外部状态，未要求重新下载、换券商或付费。等待该状态时仍可推进调度设计和既有快照的数据处理。

独立结果复核：[028](../reviews/028-tdx-minute-after-hours-results-review.md)。本轮请求诊断完成、分钟来源未通过；U4另行具体合同，整体完整目标保持active。
