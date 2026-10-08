# 026：时段变化后的分钟观察合同反方

2026-10-08。独立阅读 `TDX_MINUTE_AFTER_HOURS_OBSERVATION.md` v0.1（SHA256 `a6f70396bef087574feffd62b2a7121dac472fe2c6e5d6fb3267c63849e6e586`）、实际 `src/anatrading/tdx_acquisition.py`、共享锁实现及025结果。只读查看当前全客户端 journal 的有限字段：root 为实际 `data/local`、symbol600059.SH、target_date2026-09-30、port8765、status committed。没有 TQ/工作台请求，没有 SDK、数据库或产品写入。

## 结论

**v0.1 尚不批准执行；以下两项 P1 修订后可重新核闭。** 新时点独立合同、最多2POST及分钟不晋级产品的方向成立，旧三次预算没有被重置重跑。15:45不能证明历史主站开放，合同已正确保留这一限制。

### P1：共享 journal 的兼容字段尚未定值

`_journal` 最后调用 `_parameters`：target_date 必须 ISO 日，port 必须1–65535且**不能17709**；run_id 必须32位小写hex；evidence_directory必须严格等于解析后 root/acquisition/run_id。合同只写固定 date/port 与 `<UUID>`，同时本轮 RPC 使用17709和14位截止。若将 RPC 参数直接写入 journal，下一次日线运行会得到 invalid_acquisition_journal，全客户端阻断无法按约定恢复。

最简修订：列出 journal 定值 `root=<已解析实际data/local>`、`data_root_id=data_root_id(root)`、`run_id=uuid.uuid4().hex`、`symbol=600059.SH`、`target_date=2026-09-30`、`port=8765`、`client_directory=<已解析D:/tdx_64>`；额外 `rpc_port=17709`、`rpc_end_time=20260930150000`、`purpose=minute_source_observation`、`period=1m`。明确8765只为兼容既有 journal，诊断不调用工作台、不授予发布资格。保存新 current 后立即复用 `_journal` 回读验证，离线覆盖 compact日期／17709／带连字符UUID的拒绝负例。

### P1：终态成立前尚缺明确共享兼容断言

合同通过后用共享 failed 表示诊断终结，日线 `_TERMINAL` 将允许下一次刷新，故不能仅证明本脚本执行结束。现有表述“同会话、完整关联成功响应、非空记录与缓存对应”方向正确，但执行验收应固定区分两条分支，并核成功终态 record 可被既有 `_journal` 接受。不能复用仅检查 refresh 响应形状的 `_refresh_result` 作为 get 的业务验证。

最简修订：缓存已有分支确认**没有发送 refresh**，只有 get 严格外层id/业务码及该股票内层 ErrorId/Value 验证后，才评估观察成功；缓存缺失分支还须保留关联 refresh 成功原响应，并完成同会话 get 与稳定缓存对应。任一 gate 未通过保留 refresh_unknown；成功终态明确不声称缓存完整或最新、不声称交易所真值。终态写后 `_journal` 回读核 failed、purpose及所有固定字段；离线验证该终态被日线视作终结，并证明非终结记录同会话挡住日线。不发实际日线请求做此测试。

## P2：执行脚本必须补齐的窄边界

- 缓存初检结果应为 absent／stable／unstable／oversize，只有 absent 允许 refresh；unstable、路径逃逸或超限停，不能当 absent。每次活路径读取前后复用 `_inside`，记录 size、mtime_ns、st_ino、st_dev；两次复制都须同源元信息稳定、实际读取长度有界且hash相同。
- get 的 `Value` 为数组、1–3条、Date8位／Time6位候选合法、全数值为有限字符串，内层股票关联正确；KlineTotal只作原字段。数值解析与OHLCV/Amount字符串原件分别保存，不使规范单位已知。零记录不得重试，只保存已知空与缓存状态。
- 全文件候选时间扫描须有序、有效，并对最多3条返回标签做唯一匹配；重复候选不能任取首条。端点匹配仍不证明14位 end_time 被服务端严格遵守。
- 超16MiB可流hash但不解码；全进程120秒守卫需覆盖这个流hash阶段。请求总量2POST、连接／绝对deadline及1MiB上限应从执行文件与日志另核；这次合同审查没有证明它们已经执行。

## 已成立的设计边界

复用同客户端 `_state_directory` 与 OS `_DirectoryLock`，锁涵盖旧journal核查、全部RPC、缓存捕获、终态写入。旧非终结记录不能覆盖，已有committed收据由 previous-current.json保留；新数据不进入 EvidenceStore。readonly get 没有追加 retry，未知结果按保守共享标志处理，后续定时设计不能绕过。

候选 `<HH5f2I`、日期位解释、分钟标签、HTTP/缓存差异均仅为来源观察。五个float字段保存位型和独立精确Fraction；超 DECIMAL(38,18)作为表示阻断保留，不偷偷舍入。真实导出语义、量额单位、时间定义及正式分钟格式仍需另审，本次即使成功也不解冻它们。

## v0.2 核闭

独立重读 v0.2，SHA256 `4ebe289d03190e464c3655e5cce64221e66c779acd29333cd34ff51b0aa43fc2`；产品 `tdx_acquisition.py` SHA仍为 `3a9206aa7f40e468f0590d998b74cc38c8a256dfba3c6a20c237b35acfef3e2b`。两项P1已闭合：合同列出完整兼容journal定值、RPC参数另存；get外层与股票内层严格闸门、两分支终态资格、每次保存后的既有journal回读均明确。未知仍阻断，观察成功使用可识别failed终态且没有发布资格。

**批准撰写私有资格脚本和离线负例；离线检查通过后仅按本合同最多2POST。** 本批准属于设计核闭，没有批准产品分钟格式、全市场、重试或追加时间格式试探。上述P2仍为执行验收要求，尤其活路径 containment、四元元信息、有限复制、唯一候选匹配及原生进程守卫，须在实际脚本／负例／收据中核实。没有进行实际请求。

## 私有执行文件核闭

独立只读核 `artifacts/qualification/tdx-minute-after-hours/20261008-u3` 三文件：

- `audit_import.py` SHA `17765b38c6ddbcf9e4513d02bd279862034ae1adfa23b8dd05a68cd35804636b`。
- `test_probe.py` SHA `fe9de212565816c5d502bfec6800a964554c67f8bf5d7200f72d2a7894902dab`。
- `guarded_stage.py` SHA `5350dc54c1cd097676324897870f49e2dde6790be1dca55f86281adf058e04ad`。

实际root路径计算指向repo/data/local。脚本仅经产品HTTP与journal辅助函数，未导入厂商SDK、未构造Store或发工作台发布；共享锁覆盖全部观察，未知同会话拒绝；RPC计数上限2，缓存存在不发refresh，缺失才一次refresh及一次get；无循环重试。HTTP1MiB/绝对deadline复用已核代码。稳定缓存比较四元元信息及两次bytes，超16MiB不复制，仅hash后停；资源guard监测当前实际Python进程，120秒/2GiB只终止自身。

首次代码核查指出全文件标签有效有序与离线证明遗漏；修订后 `match` 已拒绝任何非法或不严格递增的候选标签，且目标标签各须唯一。新增真journal ISO/8765保存回读、14位日期拒绝、超限不复制及全文件非法/倒序负例源码已读；**25pass为根方执行结果，本反方没有重跑测试或请求。** 浮点独立位型Fraction/精确Decimal保存与表示资格分开，超scale没有舍入或改schema。

**在根方25项离线检查通过前提下，放行上述已核执行文件经guard `audit-observe` 发本轮最多2POST。** 执行文件变化需重新核相应差异；实际分钟来源结果仍须独立证据审核。本核闭没有声称已取得实际分钟数据。
