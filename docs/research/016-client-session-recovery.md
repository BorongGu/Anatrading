# 016 · 客户端会话终态、PID复用与恢复证据

2026-10-08。为持续免手工采集的基础设施恢复研究；不引入新的行情/交易方法或分析公式。沿用[008采集与修订研究](008-acquisition-and-revisions.md)对源版本、异步成功与可得时点的限制。恢复不是分钟数据成功，也不能据客户端结束推定主站回滚。编码须等036三项P1、实现合同和独立复审闭合。

## 实际阅读的官方文档与作者文章

| 来源 | 资料事实 | 实现推论/最小验证 |
|---|---|---|
| [OpenProcess](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-openprocess)，参数/返回/remarks | 成功取得进程句柄；失败NULL，需GetLastError。明确举例PID0返回ERROR_INVALID_PARAMETER，System/CSRSS有访问限制；结束使用需CloseHandle | 单个87不能充当完整不存在证明。先拒绝bool/0/超DWORD PID，访问拒绝/未知错误保持unknown |
| [GetProcessTimes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes)，参数/返回/remarks；[File Times](https://learn.microsoft.com/en-us/windows/win32/sysinfo/file-times)，正文相关时间表示 | creation为FILETIME的两个DWORD组成64位100ns计数，从1601-01-01 UTC起算；进程尚未退出时exit time未定义 | 原journal的7位小数必须整数转换，不经float timestamp/微秒截断。creation绑定成功句柄，不能用exit_time非零作为终态测试 |
| [WaitForSingleObject](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-waitforsingleobject)，参数/返回/支持对象 | 0毫秒立即检查；进程对象可等待。WAIT_OBJECT_0、WAIT_TIMEOUT及WAIT_FAILED不同 | 同PID+creation下，0代表signaled；258代表仍未signaled。权限SYNCHRONIZE+PROCESS_QUERY_LIMITED_INFORMATION；任何未知返回/错误拒绝，不轮询等客户端自行结束 |
| [CreateToolhelp32Snapshot](https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/nf-tlhelp32-createtoolhelp32snapshot)，TH32CS_SNAPPROCESS/返回/remarks；[Process32FirstW](https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/nf-tlhelp32-process32firstw)、[Process32NextW](https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/nf-tlhelp32-process32nextw)、[PROCESSENTRY32W](https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/ns-tlhelp32-processentry32w)的签名/返回/成员 | 标志2产生全系统进程的只读快照；无效句柄表示失败。First/Next逐项读取，列表结束错误18；结构dwSize须初始化，ULONG_PTR随位宽变化 | 仅在OpenProcess返回87时补一次有界完整进程枚举，成功到18、至少1条且原PID不在才接受“缺失”。任何失败/项目上限超出都不证明终态。无SDK/HTTP/模块枚举 |
| [Process Handles and Identifiers](https://learn.microsoft.com/en-us/windows/win32/procthread/process-handles-and-identifiers)，正文；Raymond Chen [When does a process ID become available for reuse?](https://devblogs.microsoft.com/oldnewthing/20110107-00/?p=11803)，2011-01-07正文 | 句柄可在进程退出后继续有效；PID关联进程对象，对象释放后可供复用 | 必须以PID+完整creation识别原会话。PID相同、creation不同支持原会话已终结的推论；仍需另外核新监听的已验路径和指纹。不可把进程对象尚存/原观察Python结束混成TdxW状态 |

本次仅阅读上述正文/签名/相关段落，未通读Windows内核实现、权限策略或所有错误空间；OpenProcess87与枚举缺失的联合判断是项目保守策略，不能称为官方承诺87专指不存在。进程快照只证明该观测时刻的列表；PID+creation、新监听前后稳定及恢复记录共同保留检查时点，不保证客户端未来永不重启。

## 数据与失败边界

- 原journal/current/receipt有界读取、严格JSON、原字节及哈希保留，恢复不改源行情、时间/覆盖/单位。原run机械生成failed候选，只变冻结状态/错误/未证取消/恢复版本字段。
- 三入口先验同一恢复记录及current/receipt关系，后续才可创建新run或调度槽。原子恢复记录先落盘，receipt/current双写中止可重入；缺记录、第三种字节或错关联保持阻断。
- 共同核原进程终态、两次原厂监听身份及原生creation稳定，任何失败本次零POST；同会话无权威任务终态接口时持续保留unknown，不自动强停客户端。
- 调用使用现有deadline预算和不等待的native查询；内核调用无可声称的硬取消保证，资格阶段另有120秒/2GiB外部观测守卫。访问失败/超预算不转为“不存在”，不提升权限或重试。

## 最小验收

先异常用例：7位时间末位差、时区等价、非法时间、PID/bool/DWORD截断、访问拒绝、87但快照失败/旧PID仍在、空枚举、超项数、creation复用、Wait失败及每个句柄关闭。临时目录覆盖三入口所有落盘中止点、候选白名单、错run/root/path/关联字段、completed幂等及下一次due才派发。

原生资格可仅用自建无网络Python子进程证明alive/signaled/missing与100ns相等；当前真实TdxW必须只读核现场。若仍原会话alive，则记录真实阻断与生产字节不变，无行情请求。合成成功或自建进程终态不能授予当前分钟恢复成功或日常更新资格。
