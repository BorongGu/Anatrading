# 036：客户端未知刷新恢复方案反方

2026-10-08。独立只读核读[方案v0.1](../contracts/TDX_ACQUISITION_RECOVERY_PLAN.md)、U1/U4实现合同、`tdx_acquisition.py`、`tdx_schedule.py`及对应测试。仅新增此评审；未调用SDK、行情或工作台，未读取/修改生产journal、注册任务或操作客户端进程。本评审的现场结论来自方案中已列明的只读观察，未另做当前现场核验。

## 结论

**路线可保留，三项P1须在修订方案和实现合同中闭合；当前不解冻实现。无已证P0。** 原客户端终态与新监听资格分开核证、恢复单次零HTTP、保留旧run并关闭手工旁路，是必要方向。新增命令本身不能解除真实未知，更不能证明持续全自动更新已经完成。

## 实际源码与已有合同

- `tdx_acquisition.py:436–460`：`acquire`先验dispatch；旧preparing/refresh_unknown只比较完整identity对象，相同则阻断，任意不同则写failed并在同次调用进入`_collect_locked`。这允许旧进程仍活但监听接管时追加刷新；现有`test_refresh_identity_change_stops_then_allows_proven_new_session`只注入identity变化，没有证明旧进程终态。
- `tdx_schedule.py:287–320`：due保守阻断上述未知；`test_old_unknown_refresh_blocks_due_even_after_client_identity_changes`验证无POST及原current不变。`_recover_active`只处理匹配原active的current/receipt，owner死亡不会自动关闭reserved。该保护需继续成立。
- `tdx_acquisition.py:248–253`：`_save`先receipt、后current，分别临时写入/fsync/replace；两次replace中间存在中止窗口。现在普通入口不核receipt，due无active时也不核receipt，不能仅靠新recover命令处理断点。
- `tdx_acquisition.py:381–413`：通用journal检查run、root哈希与证据目录；非终态身份的started用`datetime.fromisoformat`验合法。它未保留100ns用于等同性，且终态跳过完整身份核验。不能直接用它证明恢复候选与原unknown一一对应。
- [U1](../contracts/TDX_DAILY_ACQUISITION_IMPLEMENTATION.md)允许经会话变化恢复；[U4](../contracts/TDX_DAILY_SCHEDULE_IMPLEMENTATION.md)明确due不恢复unknown、普通手工规则保持。此次收紧须明列覆盖这两条旧规则；不能留下相互矛盾的有效合同和测试。

## P1-R01：三入口与双写断点尚无完整状态转换

方案第53–58行给出checkpoint和两份old/new记录的方向，但未规定acquire/due是否在看到终态current前检查checkpoint。例：recovery已持久，receipt成为拟封结failed而current仍unknown，随后普通acquire只因新identity不等走现有旁路，会覆盖收据并同次采集；例：两journal已终态而第二监听核证失败/尚未完成，下一次due只看终态就可新建槽。新recover自己严格校验不足以覆盖其它入口。

最小修订：

1. 明列recover/acquire/due共用的锁内恢复检查位置，早于“旧current终态→可新采集”与任何新run/槽reserve。无active旧unknown及属于当前run的recovery检查点均走同一门禁；本次发现需恢复时，无论完成、未就绪、异常都立即返回，不落入新采集。普通入口携带的新root/symbol/date/port不能改旧run或消费新槽。
2. 冻结checkpoint创建、两次稳定监听核验、两journal写入的顺序，列出每个中止点的下次三入口行为。可把两次监听核验及独立原进程终态证据在任何journal修改前全部固化到原run检查点，随后单纯完成相同封结；重复进入仍按方案重核。若坚持写journal后才做第二核验，必须有明确未完成门禁，不能把terminal journal当完成标志。
3. recovery只建立一次，原子保存且不得覆盖已有checkpoint；两文件各自只允许原记录/拟封结记录，缺失、第三种对象、损坏均保守阻断。恢复检查点已关联其它旧run时，不可把它套到新current。
4. due现有初始化会建立完整pending分母并更新last_observed_utc；明确这是否允许在阻断/恢复触发中保留。恢复必须无reserve、无新run、原槽状态/关联不变，不能用“零POST”代替这些断言。

需要故障负例：每次持久写入/replace前后中止，分别从三个入口恢复；terminal current+不完整checkpoint；旧receipt/new current的反常组合；恢复后同次不得POST，下一次due才可按正常计划新派发。

## P1-R02：原进程终态和100ns身份需要可执行证据合同

方案第41–42行指出正确原则，但当前`_client_identity`通过PowerShell字符串与对象等同性获取身份；旧journal的started合法性检查经Python datetime会把7位小数截到微秒。若复用这一解析来比较原生FILETIME，仅末位不同就可能误判PID重用。原PID查询失败也必须区分不存在、拒绝、超时及其它错误。

最小修订：冻结原生查询API、权限、PID/FILETIME范围、句柄生命周期、允许的明确不存在错误码及全部其它错误的拒绝映射。对原started用严格有时区、至多7位小数的整数日期/时区偏移转换；绝不由浮点timestamp或datetime微秒构造完整tick。匹配同一PID+FILETIME且未signaled即原会话仍活；路径改变、监听转移、同进程exe文件改变均不能替代终态。

“不存在”仅来自成功完成且错误码符合冻结语义的原生查询；PID须先验证非bool正整数及Windows DWORD可表示范围，避免类型转换截断查询另一个进程。PID重用必须保存实际creation FILETIME；signaled句柄须与已核creation绑定，句柄每路径关闭。新监听两次均保存原生FILETIME；固定监听IP/端口/唯一owner、路径、AMD64和EXE/SDK双指纹都需通过，两次PID/tick/路径/指纹一致。

冻结每查询和总预算，超时不重复探测、不杀客户端；未获得确切终态就零HTTP返回具体阻断。补7位末位相同/相差1tick、等价UTC偏移、非法/过长时间、PID重用/截断、ERROR_ACCESS_DENIED/未知错误、句柄非signaled与关闭的负例。不能用原采集owner的PID/FILETIME证明TdxW终态。

## P1-R03：checkpoint原件、目录与候选记录绑定不足

方案称“严格已验journal”，但通用validator允许root文本未强制绝对规范，并对failed终态不核完整旧身份。若仅验`proposed.status=failed`和通用终态合法，就可能接纳改root/symbol/date/identity或错run的候选；恢复文件位于某目录不自动证明其内容属于该run。

最小修订：固定检查点schema、键集、独立大小上限和严格JSON解码；保存可重取的**原始字节**及其SHA，不能只保留重序列化对象并声称保留原件。原bytes严格解码必须恰等保存old对象，old必须通过非终态原身份验证。current/receipt分别有界读取及哈希，初次二者bytes相同，重入只接纳被冻结的old/new对象组合。

核已解析绝对root、data_root_id、客户端state目录哈希、client_directory、run32hex、`root/acquisition/run_id`及所有receipt/recovery读取写入路径；重新解析须位于这一原run，不能仅核字符串前缀。old/new的run、root、target、port、source观察、原identity、coverage/units、purpose及其它旧字段完全保持；只允许合同列明的status/error_code/client_task_cancelled变更及必要固定恢复关联。new须由已验old机械生成并逐项相等，不靠终态validator推定。

首切片除active为空，还需明确拒绝带dispatch_id/plan_hash/slot_id的旧unknown以及scheduled空identity preparing；不能把原计划关联的未知运行当作未关联手工运行封结。无active合法dispatch可保留，单边marker/control仍必须停止。

需要负例：错run/目录/根哈希、relative root、路径跳出、原字节hash不符、duplicate keys/NaN/超限、old/new非白名单差异、terminal身份缺损、关联字段残留、current/receipt不一致且无有效检查点。旧请求/响应和before/after原件全部保持，不新建数据库。

## 保留的边界与用户目标

原PID/启动会话仍活且没有可关联任务终态接口时，必须保持unknown；客户端无窗口、响应成功文字、空分钟数组、时钟已盘后或观察Python结束均无法解除。旧进程终态仅支持旧进程不再执行该任务，`client_task_cancelled=not_proven`应保留，不能宣称分钟下载完成或服务器请求已取消。

due缓存无变化或目标缺失按现有not_covered/unknown处理，不因连续触发、重启调度或下次同日期自动retry旧未知；新槽请求仍受原有限日历与预算。正常使用不应要求反复手工导出、下载或每周编辑计划。恢复后任务生命周期、自动登录失效呈现、长期日历/计划续期和全市场/分钟来源资格仍需后续切片；这份方案不能用恢复命令取代它们。

当前可推进修订合同和临时故障测试，真实采集继续按方案现场证据阻断；本评审未授权或执行生产清除、强停客户端、新POST。根方在上述P1闭合及独立复审后才可解冻限定实现。
