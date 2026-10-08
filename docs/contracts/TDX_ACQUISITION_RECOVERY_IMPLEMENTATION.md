# 客户端未知刷新恢复实现合同 v0.1

2026-10-08。承接[恢复方案v0.2](TDX_ACQUISITION_RECOVERY_PLAN.md)和[036三P1](../reviews/036-tdx-acquisition-recovery-plan-review.md)。待独立复审、根方决定前不编码。原生API官方依据由根方[研究016](../research/016-client-session-recovery.md)核读；本合同列明拟冻结的机械规则，不能将设计当作当前已实现资格。

## 成功条件与限定文件

未关联调度的 preparing/refresh_unknown 可以在原进程确已终态、新客户端唯一监听就绪后，由 recover/acquire/due 同一个 early gate 安全封结旧 run；此次不采集，下次正常 due 可派发，recover 始终幂等。保持完整免手工下载目标，首切片不替代生产长期调度。

拟解冻仅新增 `src/anatrading/tdx_recovery.py`、纯时间/native小模块 `tdx_session.py`、新测试 `tests/test_tdx_recovery.py` / `tests/test_tdx_session.py`，以及 `tdx_acquisition.py` 的旧 unknown 门禁替换、`tdx_schedule.py` 的 early gate 接入、`cli.py` 的 recover-tdx 分支及对应必要既有测试。复用 AcquireError、data_root_id、_DirectoryLock、_remaining/_deadline、_client_identity 和 strict JSON 源实现；不得新增服务/依赖/数据库、修改行情方法/白名单、导入流程、格式/数值或 UI。CLI 分支在 EvidenceStore 生命周期前；无 HTTP/SDK/Store。native模块只暴露 creation_filetime(started) 与 process_observation(pid)，保持测试和句柄检查独立，避免通用探测框架。

覆盖旧 U1“身份变化即可封结后同次采集”和 U4“未关联 unknown 不核会话终态”的规则。scheduled active、publication_unknown 和 committed 的既有发布核账路径保持；首切片拒绝 scheduled unknown，不尝试 owner 死亡自动关闭原槽。

## 三入口的统一位置与返回

所有动作先取得现有 client-global `.operation.lock` 并严格 `_read_control`，损坏/单边 marker/control 拒绝。读恢复 gate 必须早于任何新 run/采集、due 初始化 marker/control、_observe 的持久时钟更新和 reserve。

1. **acquire**：参数校验与既有锁后，active 非空仍拒绝；执行 gate。gate 未完成/本次刚完成/阻断即返回或抛原安全错误，不进入 _collect_locked。gate 已验证此前完成或无恢复对象才继续既有发布核账/采集。
2. **due**：可先只读验当前 plan；锁内读已有 control。已有 control 与 plan 不符拒绝，不变更它。active 非空走既有 _recover_active 保护，不能套用本恢复。无 active 时先 gate；gate 当次返回则不创建 marker/control、不写 last_observed_utc、不改变任何槽。合法已有 control 保持 exact bytes。gate 已验证此前完成或无恢复对象才执行原控制初始化、_observe、到期选槽。
3. **recover-tdx --client-directory**：绝对规范客户端路径，沿用全局锁和 control 校验。active 非空拒绝。gate 无对象返回 `status=idle`；此前完成/当次完成返回 `status=recovered`；未就绪返回 `status=refresh_unknown` 与具体安全 error_code；畸形证据抛 typed error。始终不进入新采集。

gate 最小返回可用 None 表示“无恢复阻断，普通入口可继续”，安全恢复报告表示“当次结束”；另给 recover 专用幂等结果，避免把 completed 也一直提前返回。实现可选简单 tuple/小字典，禁止扩展通用状态框架。

恢复报告固定安全字段 `status,run_id,recovery_version,source_status,client_task_cancelled`，完成时分别 recovered/旧32hex/1/failed/not_proven；未就绪 status=refresh_unknown，附 error_code。不返回 checkpoint 原字节、token或服务错误正文。due 的恢复分支可附已验 plan_hash，不伪造已持久槽/成功日线。恢复成功 CLI exit0；未知/错误沿用 exit2。

## 原件读取、路径及来源对象

恢复专用 journal 限64KiB，checkpoint 限256KiB，读取上限+1。strict UTF-8 decode（本合同**拒绝 BOM**），所有层级重复键、NaN/Infinity、尾随垃圾、错误顶层类型拒绝；沿用既有 duplicate-hook 语义，恢复包装不得让 utf-8-sig 静默去 BOM。原件与checkpoint递归只接受JSON字典/列表/str/int/bool/null，非整数JSON数值由既有decode成为Decimal后统一typed拒绝，不能 float 强转或让json.dumps抛未处理异常。固定证据字段另外排除bool并验整数范围。

旧 run 必须通过 `_validate_journal` 的非终态身份检查，并额外冻结：

- status 仅 preparing/refresh_unknown；run 32位 lowercase hex；无 recovery_version 字段；无 dispatch_id/plan_hash/slot_id 任一字段（即使 null 也拒绝）；identity 完整，不允许 scheduled 空 identity。
- root/client_directory/evidence_directory 文本必须 absolute 且等于 Path.resolve() 规范文本；client_directory 等于入口规范路径；data_root_id=root 路径 casefold SHA；evidence_directory 精确 `root/acquisition/run_id`，解析后仍在规范 root 内。
- state 精确等于现有 `_state_directory(client_directory)` 的规范路径，basename 必须为 data_root_id(client_directory)，父路径为规范 LOCALAPPDATA/Anatrading/acquisition。测试替身可注入 state resolver，但生产不接受 CLI state 参数。
- current.json 位于该 state；receipt.json/recovery.json 及临时文件解析后在原 run 目录，当前与 receipt 必须均存在。对每个实际读/写/replace 目标重验绑定与目录，拒绝 symlink/reparse 导致越界。原 run 目录必须已存在，不创建新目录。
- 原身份 PID 非 bool 正 DWORD（1—4294967295）；path 精确规范 client/TdxW.exe；EXE/SDK 为已验哈希；started 满足下述100ns语法。其它旧字段、额外来源诊断字段原样保存。

初次恢复两份 journal **原始 bytes 完全相同**，strict解码对象也一致。checkpoint 已存在则按其 old/new 字节判据；损坏 current 不能通过新 root 绕过。仅从 current 的已验 run 定位 checkpoint，不扫描历史目录。current 带 recovery_version 但 checkpoint 缺失/损坏时，普通入口也拒绝。

故障模型覆盖本程序原子replace的中止；该动作不会留下final current不存在。下面“缺失拒绝”限于已由合法current定位原run后的receipt、必要checkpoint或该流程已确认存在的final文件丢失。若current整份被外部删除、无dispatch且无全局anchor，无法与从未采集区分；此切片不声称检测所有外部删除，不额外增加anchor或扫描旧run。recover在完全无current时返回idle，普通入口按既有首次采集路径处理；这项边界不把反复手工下载纳入产品流程。

## Checkpoint schema 与机械 new

immutable `recovery.json` 顶层恰为：

`schema, client_directory, state_directory, run_id, root, evidence_directory, old_bytes_base64, old_sha256, new_sha256, observations`。

schema 为非 bool 整数1；路径/run 绑定原 journal。old_bytes_base64 为 canonical RFC4648 字符串（validate=True，解码再编码相等），解码最多64KiB，sha匹配64位lowercase hex。完整原始 bytes 留存，不能拿重序列化数据冒充旧原件。strict解码 old 必须满足完整旧 unknown 校验。new 从 old 浅/深复制后只机械写：

```
status = "failed"
error_code = "prior_listener_session_ended"
client_task_cancelled = "not_proven"
recovery_version = 1
```

任何其它字段/嵌套对象不变；原 error_code/client_task_cancelled 可覆盖为固定新值，旧值仍在原bytes。新tag仅此整数1。new bytes 固定使用现有 `_save` 序列化规则 `json.dumps(ensure_ascii=False,allow_nan=False,indent=2).encode("utf-8")`，不加末尾换行；最大64KiB，new_sha256 精确匹配。严格验证机械生成结果，不独立信任终态 validator。checkpoint 不保存可随意修改的 new 对象，不保存 new base64，减少重复数据与不一致组合。

observations 恰两项，每项恰 `observed_at_utc, prior, listener`。UTC必须有明确Z/+00:00，合法且首项≤末项，不用时间距证明任务终态。prior 恰 `pid, expected_started_filetime, observation`；observation为下述process_observation固定五键。missing必须有完整枚举计数、census_complete=true和open_error=87；creation与expected不同支持PID重用；相同creation仅ended可通过，alive拒绝。listener 恰现有 identity 五字段加 `started_filetime`；pid为DWORD、指纹固定、path绑定、started精确转换等于native tick。两项 listener 的 pid/tick/path/hash必须相同且不同于 old pid/tick。prior pid/tick必须绑定 old。checkpoint 所有未列键拒绝，不把任意 JSON 提示当作原生证据。

新checkpoint只创建一次：锁内确认不存在，写同目录 recovery.tmp，flush/fsync，重新核final不存在，再使用**不覆盖已存在目标**的 Windows原子 rename（Path.rename，在Windows已存在目标拒绝）；不能用replace覆盖旧checkpoint。临时文件存在不代表已封存；可在锁内重新生成后覆盖自己此run同目录recovery.tmp，final已有则只读取验证。读取 final 才能修改两个 journal。

## 原生进程与100ns证据

不得依据 Get-Process 无输出、Python观察进程退出、时钟/超时、监听变化单项判终态。调用不杀进程、不等待外部刷新。root 官方核读后确认下列拟冻结API与错误映射：

- `OpenProcess(SYNCHRONIZE 0x00100000 | PROCESS_QUERY_LIMITED_INFORMATION 0x1000, FALSE, DWORD(pid))`。先类型/范围验证，避免截断。NULL且 GetLastError=87 **不直接记 absent**；官方文档仅明确PID0场景，本合同已拒绝PID0。此时另调用 CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS=2,0)，成功后 Process32FirstW/Process32NextW 完整枚举到 ERROR_NO_MORE_FILES=18，1—16384项且未包含原PID才记 absent。任意失败/空枚举/原PID仍在/超限均 `prior_process_unverified`；OpenProcess 5/0/其它错误直接拒绝。Windows required。
- PROCESSENTRY32W 按官方 DWORD/ULONG_PTR/LONG/WCHAR[260] 字段声明，dwSize=sizeof结构；在当前64位Python预期sizeof568，实际sizeof或指针位宽不符拒绝，不硬塞错误dwSize。snapshot 失败值 INVALID_HANDLE_VALUE，须按pointer宽度比较；所有成功snapshot每路径CloseHandle。枚举前后各核_remaining，禁止超限后继续扫描。
- 非NULL：`GetProcessTimes`读取 creation FILETIME，高/低DWORD拼整数，再 `WaitForSingleObject(handle,0)`：WAIT_OBJECT_0=0返回ended；WAIT_TIMEOUT=258返回alive；WAIT_FAILED=0xFFFFFFFF及其它值拒绝。persistent恢复门禁将creation与原expected比较：不同支持PID重用，相同仅ended通过，相同alive记 `client_task_unresolved`。不能把路径变化、文件变更判PID重用。
- 每个非NULL句柄 finally CloseHandle。Close失败也记typed未验证，不进入落盘；不能漏handle。新监听原生tick也通过相同查询读取，要求WAIT_TIMEOUT证明当前活；signaled/absent/错误拒绝。GetProcessTimes失败拒绝。
- started语法固定 `YYYY-MM-DDTHH:MM:SS[.1至7位数字](Z|±HH:MM)`；拒绝空时区、小数超过7位、日期/时分秒不合法、24:00/leap-second、无规范offset。creation_filetime先regex分出小数，再仅对整秒部分用datetime.fromisoformat核日期/offset；换算至UTC，与1601-01-01整数timedelta days/seconds算整秒×10^7，再加小数右补7位整数。严格positive且≤2^64−1，不用float timestamp/total_seconds，也不将7位小数先交给datetime截断。等价UTC偏移产生同tick。
- process_observation(pid) 输出恰 `state,creation_filetime,census_count,census_complete,open_error`：state仅alive/ended/missing；alive/ended具有正整数有效tick且后三项全null；missing具有creation_filetime=null、1—16384非bool完整枚举计数、census_complete严格true、open_error为非bool整数87。计数>0保证First失败18不能充当完整成功列表；最后一次Next只有ERROR_NO_MORE_FILES18才填true。输出与checkpoint都机械校验这些组合及prior PID/expectedtick等于old身份。打开成功时native小模块统一Wait0给出alive/ended，recovery负责将creation与old比较；即使alive，只要tick确实不同也证明原PID已重用。新监听必须alive且native tick精确等于其started，不能用missing授权。
- 一次观察：核原进程终态，再 `_client_identity` 核唯一监听/path/AMD64/双hash，再对该监听PID读native tick并与其started完全相等。紧接第二次观察执行同顺序，比较两新监听核心身份；两次证据通过且尚有剩余预算，才封存checkpoint/改journal。

这是设计证据而非当前现场结论。原 PID 25140 保存会话仍活时应稳定拒绝，禁止为了跑通方案主动强停客户端。

## 预算与持久顺序

每次 recovery gate最多60秒，与due既有150秒业务deadline取较早者，复用 `_deadline` ContextVar并finally reset。无需恢复的快速读检查不能重置/延长已有deadline。每阶段和每次持久前/后 `_remaining()`；每次 `_client_identity` 既有PowerShell timeout取8秒与剩余较小值，EXE≤32MiB/SDK≤1MiB，文件读/hash分块也重核剩余预算。原生Wait严格0；原生query前后核剩余。同步磁盘/本机syscall超时不能强行取消，不能声称60秒硬强停，但到期不新增探测或写入阶段，无重试、无HTTP。

**所有外部证据检查都在journal修改前完成。** 初次及未完成重入均：验证old/new绑定→两次原生终态+新监听→必要时原子创建checkpoint→读回严格核checkpoint→receipt.tmp/fsync/replace→current.tmp/fsync/replace→读回两final判N/N。只有未完成时才重新进行实时证据检查；completed快速校验不用要求新监听再次出现，它已封结的是旧进程，之后采集仍由既有采集流程核当前身份。

既有 `_save` 的同样序列化/双replace可复用或提取薄helper；须在每次write/replace边界核预算和路径，不能一次无门禁调用后假设无中止。改动不得影响普通发布流程的既有语义。

## 完成判据与全部断点

O=checkpoint中exact old bytes，N=机械生成exact new bytes；判据先验严格checkpoint/schema/path/old/hash/new/observations，随后两个 journal 各≤64KiB且exact O/N。

| final checkpoint | receipt/current final | 三入口结果 |
|---|---|---|
| 无 | O/O，unknown且无tag | 初次候选；重新核证后才创建checkpoint；同次结束 |
| 无，仅recovery.tmp | O/O | tmp不授权；重新核证并原子创建final；同次结束 |
| 有且有效 | O/O | 未完成；重新核证，只补旧run；同次结束 |
| 有且有效 | N/O | receipt已replace、current未replace；未完成，同上 |
| 有且有效 | O/N | 反常但仍只含已冻结O/N；未完成，同上，不能因current已terminal派新槽 |
| 有且有效 | N/N | 已完成：recover幂等recovered；acquire/due可走正常路径 |
| 无/损坏 | terminal带recovery_version | checkpoint丢失，拒绝所有入口，不新采集 |
| 任意 | 已由合法current定位的receipt缺失/已确认final丢失，或超限/第三种bytes/不匹配tag/错run | 拒绝，不删除/覆盖恢复证据 |

checkpoint atomic rename前中止只会留下tmp且journal未改；rename后中止为O/O。receipt.tmp的write/fsync/replace前中止仍O/O，replace后为N/O。current.tmp的write/fsync/replace前仍N/O，replace后N/N。反常O/N同样先完整核证再机械补齐。after-current-replace预算检查/读回失败可报告未知，但下一次N/N是已封存证据+两final字节独立判据，不依赖上一Python正常返回。无需额外mutable done flag，避免第三次完成标记写入断点。

当次 newly-completed或unfinished一律early return，不init控制/新run/槽；**下一次** completed ordinary gate允许正常派发。新run把current替换为新record后，只在新record目录查checkpoint，历史恢复文件保留且不阻断；禁止全盘历史扫描。completed缺少checkpoint/tag或checkpoint与current错run继续拒绝。

## 测试与真实资格

先写失败用例，再实现校验。临时目录和注入native结果覆盖全部036负例及上述表格，三个入口分别对checkpoint rename、receipt/current write/fsync/replace每个前后中止验证；断言零HTTP、Store、SDK、新run/reserve、控制bytes变化。补completed下次due真实ASGI单写者派发、recover重复零请求、历史checkpoint不阻断新run、completed缺checkpoint仍拒绝和普通acquire旧旁路关闭。

100ns日期手算测试包括末位相同/差1tick、7位小数与等价offset、非法日期/offset/超长小数、DWORD截断/bool、ERROR87不可单独授权、snapshot/first/next各错误、枚举空/原PID仍在/超16384项/完整到18、ERROR5/未知、同creation WAIT_TIMEOUT、reused/signaled、process与snapshot CloseHandle各分支。native函数只能做process身份/零等待；离线注入不证明真实客户端恢复。

focused恢复/采集/定时/CLI检查通过后跑完整Python回归和独立代码反方；未改UI不新建图形验收。对已打开的当前PID进行只读native同creation/live资格，可另设极短自建进程验证终态/创建FILETIME，但须另审私有helper范围，不能强停用户客户端。真实生产journal改动、下一次行情刷新和正式任务登记另需封定具体动作/预算/产物并独立审阅；当前原会话仍活，真实恢复继续阻断。所有账户/状态/原件/观察产物不进公开git。
