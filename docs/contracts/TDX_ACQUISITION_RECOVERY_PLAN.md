# 客户端未知刷新恢复方案 v0.1

2026-10-08。用户要求持续免手工下载。此文仅提出恢复设计，不解冻产品代码、生产状态修改或新行情请求；须另经独立子 agent rebuttal、修订及根方决定。恢复通过后仍需正式日线任务、长期日历、工作台生命周期和全市场/自选分钟资格，不能把一次恢复称为持续自动更新完成。

## 当前只读事实

2026-10-08T10:20:58.0469597Z 通过 PowerShell 文件哈希、Get-NetTCPConnection、Get-Process 和本机 EXE/SDK 哈希只读观察，未调用行情、SDK、工作台或 acquire/due：

| 项目 | 观察 |
|---|---|
| current 与对应 receipt | SHA-256 均 `5fa6af4427152614838483704e9562c4200cdbb08c32e21ad0c7f2d7de1fb343` |
| 原运行 | `20dc43a410af406aa6ba099ce2015f1c`，`refresh_unknown`，purpose=`minute_source_observation` |
| 保存客户端身份 | `D:\tdx_64\TdxW.exe`，PID 25140，启动 UTC `2026-10-08T03:19:49.7815869Z` |
| 当前 127.0.0.1:17709 唯一监听及原 PID | 仍为同路径、同 PID、同启动时刻；原会话实际存活 |
| EXE / SDK | 分别 `4c822464613fabe4b4235edf171b031d8b209ef68bd7d06dea403e1cd54c1fad` / `241358919fd394751a46bb51d64374eb0216f7c22bfa47bc13c48418ba26b1b0`，匹配已验指纹 |
| 生产 dispatch.required / dispatch.json | 均不存在 |

**当前没有原客户端任务结束或会话结束证据，不能清除未知或追加刷新。** 观察程序已退出、U5 自建 Python 已终态、时钟超过盘后窗口、响应成功文字、空分钟数组和缓存缺失，都不证明 TdxW 的原后台刷新任务终结。原客户端仍活是当前具体阻断，未知文件本身不充当活跃进程句柄。

## 已有代码的能力与缺口

- `tdx_acquisition.acquire` 在同客户端锁中处理旧 preparing/refresh_unknown：相同 `_client_identity` 拒绝；身份对象有任何变化，则把旧记录写 failed / prior_listener_session_changed / client_task_cancelled=not_proven，随后**同一次调用**进入 `_collect_locked`。因此已有手工日线入口能利用监听会话变化，但没有独立、零 POST 的恢复动作。单纯身份对象不等也未独立证明旧 PID 的原进程已结束；同一客户端其它进程接管监听时，不能推定旧进程终态。
- `tdx_schedule.due` 对旧 preparing/refresh_unknown 保守直接阻断，**即使客户端身份改变也不恢复**；测试 `test_old_unknown_refresh_blocks_due_even_after_client_identity_changes` 锁定此行为。将普通 acquire 当成自动恢复入口，会引入同次新采集及绕过槽分母的问题。
- `_recover_locked` 仅用于 publication_unknown/committed 的原件、原工作台会话及发布核账，不能套用到分钟刷新未知。
- `_recover_active` 只接受严格匹配原 active 的 current/receipt。owner PID 消失不能证明已发送给客户端的请求取消。U5 的 reserved 私有样本证明确实阻断，但未授予生产清除资格。

依据：[U1/U2合同](TDX_DAILY_ACQUISITION_IMPLEMENTATION.md)、[U3真实观察](../qualification/tdx-minute-after-hours.md)、[U4实现合同](TDX_DAILY_SCHEDULE_IMPLEMENTATION.md)、[U5真实资格](../qualification/tdx-task-runtime.md)。上述源码与测试为本次读取事实，历史资格的时点/范围仍以原文为准。

## 最小安全路线

首切片仅恢复**无调度 active 的旧 preparing/refresh_unknown**，适用于当前真实分钟 unknown。不恢复 publication_unknown，不删除控制标记，不关闭 reserved/linked/dispatch_unknown，不自动终止/重启客户端，不增行情方法，不运行 SDK，不打开数据库。当前 client-global 锁、journal、原 run 证据目录和唯一写者保持。

新增显式 `recover-tdx --client-directory <绝对路径>`，不接收新的 root、股票或日期，不开始采集；旧目标完全从严格已验 journal 获取。恢复成功只封结旧运行，本次行情/工作台 HTTP 均为零。后续一次 due 才可保留并采集新的日线槽。正式自动任务应先执行同一恢复门禁：无法证明则返回具体阻断；证明后本次结束，下次调度才新派发，避免一次恢复混入新业务。

同一门禁也应在普通 acquire 的旧 unknown 分支复用，关闭当前“身份不等即封结并立即采集”的旁路；这属于有意收紧旧行为，需负例与反方批准，不能只给新命令增加严格检查而保留旧旁路。

### 允许的会话终态证据

锁内先核 marker/dispatch 合法且无 active，current/receipt 严格相同、原目录合法且同 run、原身份与已验指纹有效。再检查原 PID 与当前唯一监听：

1. 通过有界原生进程查询独立证明**保存 PID/启动时刻对应的原进程已终态**。可接受成功查询的原进程句柄 signaled；或明确的进程不存在；或保存 PID 已重用且原生 creation FILETIME 对应另一启动时刻。拒绝仅 Get-Process 无输出、权限不足、观测异常、超时或路径变化等不明确情况。对保存的 UTC 时刻保留 100ns 精度转换，禁止浮点/微秒截断把同进程误判为 PID 重用。
2. 当前监听必须是已验路径、EXE/SDK 指纹、AMD64 的唯一 127.0.0.1:17709 拥有者，且与原会话不同；恢复前后两次核其 PID/原生启动 FILETIME/路径与指纹一致。新监听缺失、原进程仍活、多个监听或身份变化一律保留未知。
3. 保存本次原进程终态证据和新监听身份、UTC 观测时间、旧 current/receipt 哈希。仅将旧 run 置 failed，建议 error_code=`prior_listener_session_ended`，保留 `client_task_cancelled="not_proven"`；含义是旧客户端进程终态后不再由该原进程继续任务，**不证明分钟下载完成、已成功取消请求或外部结果回滚**。原分钟响应、缓存观察、coverage 和单位原样保留。

没有新监听时可只报告“原进程已终态、客户端尚未就绪”，本切片不修改生产状态；在下次自然登录后重新核证。持续使用时仅需通常的首次/失效登录，不能把反复手工下载、每周编辑计划或重启客户端列为长期自动化流程。

### 同会话任务终结路线暂未取得证据

U3 已审接口没有任务状态查询、取消确认或可关联到 run 的权威终态回执。客户端页面上无下载窗口、成功文字或空数组不够。若未来发现官方任务查询能力，须先核真实 API 合同、唯一任务关联与终态语义，再单独提交方案和资格；本切片不编造 status RPC，不通过 SDK 探测交易方法。原会话一直存活时，当前可推进恢复代码/异常测试/定时生命周期设计，真实再次采集仍保持阻断。

## 落盘、崩溃与重复调用

复用 `_save` 的 receipt→current 顺序，必须正视两文件之间中止。方案建议先在**原 run 证据目录**持久一个有界 `recovery.json`，包含完整原 unknown 记录、其原字节哈希、完整拟封结记录和终态观察；一次只关联该 run，不建新全局状态库。具体字段与大小须在实现合同冻结。

- 写 recovery 前 current/receipt 必须字节哈希和严格解码记录相符。先 fsync recovery，再写原 receipt/current；不创建新 run 或槽。
- 重复调用有 recovery 时，仅接受两份记录各自等于已保存的原记录或拟封结记录；重新核原进程已终态及新监听就绪，再完成同一封结。其它差异、缺失、损坏或关联错误拒绝，绝不覆盖成新的任务。
- 两文件均为拟封结记录时返回同一恢复结果，零 POST。旧记录/原字节留在 recovery 中，旧运行编号、证据和失败语义保留。
- 不允许单独靠 recovery 文件存在解锁；缺少当前独立终态证据仍停止。恢复文件损坏不得删除重试。

该检查点是建议，独立反方需重点审查是否可进一步直接复用既有收据且仍覆盖双写中止。root 决定前不增加文件或修改状态。

## 验收与后续真实执行门禁

先写异常输入与故障用例，至少覆盖：同 PID/时刻仍活、旧进程活而监听已转移、PID 重用、原进程 query 权限拒绝/超时、100ns 启动精度、监听重复/消失/前后变化、指纹/路径错误、current/receipt 损坏或不一致、active/单边 marker、跨 run 伪关联、recovery 写入及两次 journal 写入各断点、重复恢复零请求、旧字段不改、恢复不消耗新槽，普通 acquire 无旧旁路。所有注入用临时目录，不修改当前生产 state。

独立代码反方通过后，真实恢复资格先只读重新核现场。仍为原活跃会话就明确阻断，不能为取得绿色结果强停客户端。只有自然会话更换或之后获授权并有独立终态证据的确切操作，才能在已审预算下执行一次恢复；前后检查全部原件、旧记录与零 HTTP 计数。再另审生产计划精确注册及一次日线新采集；U1/U2 的历史成功不能替代这次实际资格。

仍需并行完成：自动启动/正常关闭工作台、正式系统任务精确注册注销及生产 pythonw 动作、长期日历更新和有限计划安全续期、积压/去重、全市场日线、自选分钟真实样本和同花顺路线。当前最可推进的动作是独立反方审本方案并冻结实现合同；当前真实采集阻断为**原会话仍活且无后台任务终态接口证据**。
