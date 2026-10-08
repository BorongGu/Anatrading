# 客户端未知刷新恢复方案 v0.2

2026-10-08。用户要求持续免手工下载。根据[036反方](../reviews/036-tdx-acquisition-recovery-plan-review.md)三项 P1 修订；具体状态、原生证据和大小/路径边界见[实现合同](TDX_ACQUISITION_RECOVERY_IMPLEMENTATION.md)。两份文档待独立复审与根方决定，不解冻产品代码、生产状态修改或新行情请求。恢复通过后仍需正式日线任务、长期日历、工作台生命周期和全市场/自选分钟资格，不能把一次恢复称为持续自动更新完成。

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

首切片仅恢复**无调度 active、无 dispatch_id/plan_hash/slot_id 字段的旧 preparing/refresh_unknown**，适用于当前真实分钟 unknown。原身份必须完整；scheduled 空 identity preparing 拒绝。不恢复 publication_unknown，不删除控制标记，不关闭 reserved/linked/dispatch_unknown，不自动终止/重启客户端，不增行情方法，不运行 SDK，不打开数据库。当前 client-global 锁、journal、原 run 证据目录和唯一写者保持。

新增显式 `recover-tdx --client-directory <绝对路径>`，不接收新的 root、股票或日期，不开始采集；旧目标完全从严格已验 journal 获取。三入口共用锁内 early gate，早于 acquire 新 run，以及 due 初始化控制、更新时钟、reserve 槽。发现未完成恢复时，本次无论完成/未就绪/异常立即结束，行情/工作台 HTTP、新 run、新槽和 control 写入均为零。已有合法无 active control 原样保留。

恢复已完成时，recover 幂等返回；acquire/due 通过完整 checkpoint/tag 验证后可继续原正常路径。检查点只属于 current 引用的 run；新 run 替换 current 后不扫描历史恢复文件。这样下一次 due 可以采集，不形成每次恢复均提前返回的永久零请求循环。

关闭普通 acquire 当前“身份不等即封结并立即采集”的旁路。此合同获准后覆盖 U1 的这一宽松规则和 U4 的“due 永远不核会话终态”规则；scheduled active 和发布核账保护保持。变化须经负例及反方批准。

### 允许的会话终态证据

锁内先核 marker/dispatch 合法且无 active，current/receipt 严格相同、原目录合法且同 run、原身份与已验指纹有效。再检查原 PID 与当前唯一监听：

1. 通过有界原生查询独立证明**保存 PID/启动时刻对应的原进程已终态**。PID 须为正 DWORD 整数；OpenProcess 使用 SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION，GetProcessTimes、WaitForSingleObject(0)，每路径 CloseHandle。OpenProcess 错误87单独不证明不存在，须再成功创建 Toolhelp 全进程快照并完整枚举至 ERROR_NO_MORE_FILES=18，1—16384项且不含原PID，才接受 absence。成功打开且 creation FILETIME 不同支持 PID 重用；相同 creation 且 WAIT_OBJECT_0 支持终态；其它错误停止。原 started 按整数日期/时区/最多7位小数转换为 100ns FILETIME，禁止浮点 timestamp 或微秒截断。
2. 当前监听必须是已验路径、EXE/SDK 指纹、AMD64 的唯一 127.0.0.1:17709 拥有者，且与原会话不同；**修改 journal 前**两次核其 PID/原生启动 FILETIME/路径与指纹一致。两次各独立核原会话终态，新监听缺失、原进程仍活、多个监听或身份变化一律保留未知。两份证据先封存 checkpoint，才可写 journal；没有 journal 已终态但第二核证尚未完成的路径。
3. 保存本次原进程终态证据和新监听身份、UTC 观测时间、旧 current/receipt 哈希。仅将旧 run 置 failed，建议 error_code=`prior_listener_session_ended`，保留 `client_task_cancelled="not_proven"`；含义是旧客户端进程终态后不再由该原进程继续任务，**不证明分钟下载完成、已成功取消请求或外部结果回滚**。原分钟响应、缓存观察、coverage 和单位原样保留。

没有新监听时可只报告“原进程已终态、客户端尚未就绪”，本切片不修改生产状态；在下次自然登录后重新核证。持续使用时仅需通常的首次/失效登录，不能把反复手工下载、每周编辑计划或重启客户端列为长期自动化流程。

### 同会话任务终结路线暂未取得证据

U3 已审接口没有任务状态查询、取消确认或可关联到 run 的权威终态回执。客户端页面上无下载窗口、成功文字或空数组不够。若未来发现官方任务查询能力，须先核真实 API 合同、唯一任务关联与终态语义，再单独提交方案和资格；本切片不编造 status RPC，不通过 SDK 探测交易方法。原会话一直存活时，当前可推进恢复代码/异常测试/定时生命周期设计，真实再次采集仍保持阻断。

## 落盘、崩溃与重复调用

先在**原 run 证据目录**原子封存一个 immutable `recovery.json`，再按 receipt→current 顺序分别临时写入/fsync/replace。journal 各最大64KiB，checkpoint 最大256KiB；保存原始字节 base64/SHA、新字节 SHA 和两次原生证据。strict UTF-8、所有层级重复键和非有限数拒绝。原始字节严格解码及非终态旧身份有效；new 机械生成，只允许 status/error_code/client_task_cancelled/recovery_version 四字段变更。root/run/client/state/全部证据路径均须规范绝对并严格绑定。

检查点已存在不得覆盖。重新进入时两个 journal 必须分别为 exact old 或机械生成的 exact new；O/O、N/O、O/N 为未完成，三入口重新核原终态/新监听，只完成原 run，并立即返回。N/N 为完成，不额外写完成标记；recover 幂等，acquire/due 下次可正常继续。缺失/第三种字节/损坏拒绝；terminal 带 recovery_version 但丢 checkpoint 仍阻断。候选 new 必须精确等于由已验 old 机械生成结果，不能依赖终态 validator 放宽旧身份。

checkpoint 临时写入中止、receipt/current 两次 replace 前后中止、期限耗尽的全部状态与三入口行为在实现合同列明。只保存临时文件不会完成恢复；不按超时推定外部任务终结。不改旧来源字段、原件或记录编号，不建状态数据库。

## 验收与后续真实执行门禁

先写异常输入与故障用例，覆盖036全部三P1：三入口各持久断点、missing checkpoint+terminal tag、old/new各组合、root/run/state绑定、非白名单差异、scheduled 字段残留、严格字节/JSON大小、PID/DWORD/100ns/原生错误、句柄释放和总60秒恢复预算；再验恢复当次零HTTP/新run/槽/control修改，以及下次due可派发、recover幂等、历史checkpoint不阻断新run。所有注入用临时目录，不修改当前生产 state。

独立代码反方通过后，真实恢复资格先只读重新核现场。仍为原活跃会话就明确阻断，不能为取得绿色结果强停客户端。只有自然会话更换或之后获授权并有独立终态证据的确切操作，才能在已审预算下执行一次恢复；前后检查全部原件、旧记录与零 HTTP 计数。再另审生产计划精确注册及一次日线新采集；U1/U2 的历史成功不能替代这次实际资格。

仍需并行完成：自动启动/正常关闭工作台、正式系统任务精确注册注销及生产 pythonw 动作、长期日历更新和有限计划安全续期、积压/去重、全市场日线、自选分钟真实样本和同花顺路线。当前最可推进的动作是独立反方审本方案并冻结实现合同；当前真实采集阻断为**原会话仍活且无后台任务终态接口证据**。
