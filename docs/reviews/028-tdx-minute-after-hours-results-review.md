# 028：时段变化后分钟真实结果反方

2026-10-08。按[观察合同v0.2](../contracts/TDX_MINUTE_AFTER_HOURS_OBSERVATION.md)及[026](026-tdx-minute-after-hours-contract-review.md)，独立只读复核实际保存字节。没有行情/工作台RPC、SDK执行、数据库访问或共享journal清理。另以临时内存脚本核资源与记录等价，并调用既有只读 `_journal` 验证当前结构，没有运行采集脚本。

## 结论

**本轮有界诊断已终结，分钟来源未通过；无新增需要扩大请求的P1。** 实际600059.SH返回0条，指定分钟缓存不存在。保持共享 `refresh_unknown` 正确，不能因成功业务码或查询进程结束解除未知。未证历史分钟主站具体开放时点、账户/收费限制、免费接口能力或14位截止参数语义；此前GUI时段拒绝与本次空数组的因果仍未证明。

## 原始请求和响应

私有目录 `data/local/acquisition/20dc43a410af406aa6ba099ce2015f1c`，独立重算四份原始字节SHA与资格报告一致：

| 原件 | SHA256 |
|---|---|
| refresh请求 | `9f6b28891701dde3cb77ebdf1ec3258e6c63777fd173e0de020662e3dcb0b028` |
| refresh响应 | `1b01a0ea9ed6c9d3030370465071af290841f6a0ee00b39c0e2a6135dea05360` |
| minute请求 | `7fd59e1f1a9915eb8a32470b83a010d2cfc2e9648d6da8c69da31e0ed3789ecc` |
| minute响应 | `0bb5fe94dd6ac359d26c650cd969b2ddb6f75957892c4b0c9f21bd138b28ce19` |

refresh仅id301、600059.SH、1m；响应id关联，字符串ErrorId0、Msg `refresh kline cache success.`、run_id字符串0。minute仅id302、相同股票/周期、end_time20260930150000、count3、none、fill_data=false。响应外层及证券层字符串ErrorId0，证券Value空数组；KlineTotal在外层映射报告该股1，实际记录仍0。没有Date/Time/数值数组，不能验证时间标签、位型精度、量额单位或缓存候选布局。

响应HTTP status未独立保存到receipt；受审执行文件检查非200即停。本轮达到 market 与 match 空记录分支，构成HTTP闸门通过的代码路径证据，不将原始响应内容单独当HTTP状态日志。请求预算2及无retry/其他方法由实际请求文件、requests_attempted2与已核执行逻辑共同支持；这不是全机网络流量捕获证明。

## 共享状态、身份及原件保留

receipt明确 `cache_before.exists=false`、`cache_after.exists=false`、returned_rows空、error_code=no_effective_minute_data、qualification=stopped_without_retry、client_task_cancelled=not_proven。不存在不是从缺文件列表间接猜测，而是本次捕获分支保存的观察；反方没有重查当时活缓存。

五个请求前后及捕获后identity观察均相同：PID25140、启动UTC03:19:49.7815869Z、D:/tdx_64/TdxW.exe及固定exe/SDK SHA。UTC08:16:44.343142至08:16:48.398939，对应上海16:16；旧时间不能证明当前仍在运行。

独立调用既有 `_journal` 读取实际客户端全局current成功；它与本轮receipt全对象及全部bytes一致，SHA `5fa6af4427152614838483704e9562c4200cdbb08c32e21ad0c7f2d7de1fb343`。固定实际root/data_root_id、uuid.hex、ISO日、port8765及identity均兼容，status确为refresh_unknown。`previous-current.json`与原日线 `41545e9d1a8a407483212050203d56ee/receipt.json`逐字节一致，旧日线收据未被改写。

根方报告随后实际日线CLI被 `client_task_unresolved` 阻止，未追加POST；后来保存 `day-guard-terminal-observation.json`（SHA `7060312207334fd73a94c48923c59a9bc3c96ccf41079a51f6128034bc031aea`）。反方已读其原字节：明确为从本会话已完成工具结果复制，stdout为对应类型错误JSON，PowerShell/tool退出1；不是直接redirect的进程原生日志。逻辑CLI退出2只有源码映射，未独立捕获原生进程退出码。类型拒绝加源码同会话非终结分支支持刷新前停止，没有网络包捕获。因此实际CLI执行归属根方保存的终端观察，反方不声称独立重跑了客户端身份、该CLI或独立审阅原工具结果。

## 执行文件与资源

执行后读取脚本hash仍与026批准版本相同：audit_import.py `17765b38c6ddbcf9e4513d02bd279862034ae1adfa23b8dd05a68cd35804636b`，guard `5350dc54c1cd097676324897870f49e2dde6790be1dca55f86281adf058e04ad`。这结合根方实际启动及保存输出支持已审文件执行；反方未观测进程启动，不能将事后hash当独立加载跟踪。

直接读取 `audit-observe-resources.json` 全部59样本，时间严格递增；PID11364、实际Python314 executable、精确FILETIME整数 `134359210018050447`，status failed/exit2、总6.334571秒。各原生计数独立最大值：

| 计数 | 最大B |
|---|---:|
| working_set | 63,188,992 |
| private_usage | 545,193,984 |
| system_peak_working_set | 64,192,512 |
| system_peak_pagefile_usage | 546,193,408 |

全部小于2GiB及120秒；属于逻辑来源观察失败，没有资源杀停状态。资源终态证明采集进程已结束，**不证明客户端内部任务终结**；不构成HTTP500ms性能或客户端资源上界。守卫及采集代码未终止用户客户端或工作台，没有进入产品发布/数据库分支。

本轮最多2POST预算已经耗尽。后续采集需新的可审外部状态或任务终结证据，不能等待后清journal、自动重试或换时间输入。现存日线快照的数据处理与调度设计可继续，分钟正式来源/格式资格仍冻结。
