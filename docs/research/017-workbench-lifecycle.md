# 017 · 本地工作台登录启动与正常退出

2026-10-08。只读研究，未注册/启动/停止 Task、服务、工作台、SDK 或行情，未改产品。限微软、Python、Uvicorn 官方资料及本机固定版本源码。承接 [008 的源版本与覆盖](008-acquisition-and-revisions.md)、[011 的采集与发布终态](011-unattended-source-capture.md)：生命周期便利不增加行情覆盖或预测效力；服务正常退出和在途发布完成须分别证明。方案、独立反方与根方决定关闭前继续冻结产品。

## 官方事实及设计边界

以下阅读范围为各页正文、属性/返回和 Remarks；未审计 Windows 调度器内核实现。网站说明当前可见，具体本机行为仍需另做真实资格。

| 官方原始来源 | 已读事实 | 项目推论与未证明事项 |
|---|---|---|
| [TaskSettings.ExecutionTimeLimit](https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-executiontimelimit)；[Trigger.ExecutionTimeLimit](https://learn.microsoft.com/en-us/windows/win32/taskschd/trigger-executiontimelimit) | task 默认运行限72小时；task settings 的 PT0S 表示无限。trigger 另有同名属性 | 长期工作台可拟用 Settings/PT0S；须同时检查触发器同名设置，避免额外有限值。无限是调度时限设置，无法保证进程不崩溃、机器不休眠或资源无限可用 |
| [AllowHardTerminate](https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-allowhardterminate)；[IRegisteredTask.Stop](https://learn.microsoft.com/en-us/windows/win32/api/taskschd/nf-taskschd-iregisteredtask-stop)；[IRunningTask.Stop](https://learn.microsoft.com/en-us/windows/win32/api/taskschd/nf-taskschd-irunningtask-stop) | 调度器先尝试 WM_CLOSE；未响应时只有 AllowHardTerminate=true 才可用 TerminateProcess。RegisteredTask.Stop 涉及该任务全部实例；RunningTask.Stop 限该实例；前者区分 S_OK/S_FALSE | false 限制调度器强制终止，不构成 Python/Uvicorn 正常退出证明。Stop 成功、Task 非 Running、进程已退出也不证明 ASGI lifespan 或数据库清理完成。上述页面未承诺 WM_CLOSE 如何映射 Python ASGI，组合真实行为本轮未测；产品正常停止需独立 owned 机制 |
| [MultipleInstances](https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-multipleinstances) | IgnoreNew 在该任务已有运行实例时不启动新实例；另有 Parallel/Queue/StopExisting | 作用域为同一 Task，不能阻止另一任务名或手工 serve。数据根 OS 锁与已绑定进程身份仍须独立核验；不能因端口被占就停止占用者 |
| [LogonTrigger.UserId](https://learn.microsoft.com/en-us/windows/win32/taskschd/logontrigger-userid)；[Principal.UserId](https://learn.microsoft.com/en-us/windows/win32/taskschd/principal-userid)；[LogonType](https://learn.microsoft.com/en-us/windows/win32/taskschd/principal-logontype)；[RunLevel](https://learn.microsoft.com/en-us/windows/win32/taskschd/principal-runlevel) | LogonTrigger 可指定用户名/SID，空值会响应任意用户登录。InteractiveToken 限已有交互会话；LUA 为最低权限。Builtin Administrator/System/Local Service 或 UAC关闭时 RunLevel 有忽略边界 | 拟将 trigger 与 principal 同时绑定当前普通用户 SID，InteractiveToken、LeastPrivilege，无密码/S4U。模板声明与实际 SID/会话/令牌权限须分别核验；不声称注销后、用户未登录时仍服务。保持现有提升权限终端工作方式，不要求另开终端 |
| [StartWhenAvailable](https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-startwhenavailable)；[LogonTrigger XML](https://learn.microsoft.com/en-us/windows/win32/taskschd/taskschedulerschema-logontrigger-triggergroup-element) | StartWhenAvailable 仅适用于带 EndBoundary 或无限重复的 time-based task；补运行会排队，默认延迟10分钟。LogonTrigger 响应登录，XML子项有规定顺序 | 不将 StartWhenAvailable 当作补发错过的登录事件或立即自愈。单次用户登录模板可取 false；启动成功之后进程崩溃不自动重新制造登录事件。实际登录触发需要真实事件证据，COM手工 Run 不能替代 |
| [RestartOnFailure XML](https://learn.microsoft.com/en-us/windows/win32/taskschd/taskschedulerschema-restartonfailure-settingstype-element)；[ExecAction.Path](https://learn.microsoft.com/en-us/windows/win32/taskschd/execaction-path)；[WorkingDirectory](https://learn.microsoft.com/en-us/windows/win32/taskschd/execaction-workingdirectory) | RestartOnFailure 指定失败重试，Count/Interval 都须设置；动作指定可执行文件与工作目录，环境变量可在任务引擎启动时缓存 | 首切片不设 RestartOnFailure/重复触发，避免错误状态触发重启。固定绝对 pythonw、项目 cwd、参数及数据根，读取注册后实际 XML 再核。模板只生成定义，不构成后台常驻或启动成功证据 |
| [Hidden](https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-hidden)；[GetConsoleWindow](https://learn.microsoft.com/en-us/windows/console/getconsolewindow)；[CREATE_NO_WINDOW](https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags) | Hidden 控制任务界面可见性。GetConsoleWindow 的 NULL 表示调用进程无关联 console；pseudoconsole 的 HWND可只用于消息队列。CREATE_NO_WINDOW 适用于 console app，若非console或与新console/detached组合则忽略 | Hidden=true、前台 serve 测试或 CREATE_NO_WINDOW 声明都不能替代实际 pythonw/exe/PID/creation/SID/console 检查。资格绑定真正 Python worker，避免只观测 venv 启动器。GetConsoleWindow用于本机资格记录，不用来推断交易客户端终态 |

[DisallowStartIfOnBatteries](https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-disallowstartifonbatteries) 与 [StopIfGoingOnBatteries](https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-stopifgoingonbatteries) 分别影响电池启动和切换电池时停止。持续本地工作台模板可明确取 false；这是拟议配置，本轮未验证电源切换。休眠/断电仍可造成服务空档，不补成数据覆盖。

## pythonw 与固定 Uvicorn 源码

Python [sys 标准流](https://docs.python.org/3/library/sys.html#sys.__stderr__)明确指出 Windows GUI/pythonw 下 sys.stdin/stdout/stderr 及原始对应项可为 None。[StreamHandler](https://docs.python.org/3/library/logging.handlers.html#streamhandler)未指定流时使用 sys.stderr，输出对象须提供 write/flush。推论：关闭颜色探测只解决 formatter 构造；后台诊断仍需显式可靠输出，不以 print、控制台错误或日志缺席判成功。

本机 `pyproject.toml:10` 与 `.venv/Lib/site-packages/uvicorn-0.54.0.dist-info/METADATA:3` 均为 **0.54.0**，本轮只读这些文件及下表片段。线上官方文档为当前文档，内部字段行为以本机封定源码为准，不声称为所有版本稳定API。

| 本机文件及阅读位置 | 源码事实 | SHA-256 |
|---|---|---|
| `uvicorn/config.py:83–115,214–217,236,388–398` | 默认 formatter use_colors=None；handlers 绑定 sys.stderr/stdout。显式 use_colors=false 会覆盖两个 formatter 后再 dictConfig；默认 graceful timeout=None | `cf91c6ffae283a2b2020da954b4cc4ed47d3246cb062afd09fb77d98e4c5ca87` |
| `uvicorn/logging.py:32–43` | 未显式 True/False 时直接 sys.stdout.isatty()；None 无该方法。access_log=false 或 warning 级别不跳过 formatter 构造 | `9020759f8e41e4ee794920298afdb1e94406dcb9c5a8d946bdca211b20306e55` |
| `uvicorn/server.py:73–74,86–118,178–207,271–327,329–357` | should_exit 使主循环结束；startup 的 lifespan.should_exit 或端口绑定失败会 exit3，绑定成功后才 started=true。shutdown 先停止接入、要求连接退出、等待任务。有限 timeout 到期会取消请求任务，随后在 force_exit=false 时 await lifespan.shutdown；该 await 位于前述 wait_for 之外 | `c1be9d133467a42ab88d7168e408ef5a90257661a901899426214a3d1fc2d026` |
| `uvicorn/main.py:613–640` | 当前 uvicorn.run 对单worker/not started 也 exit STARTUP_FAILURE；config.py:81 定义为3。当前 CLI main 未捕获 SystemExit，不能称现有启动失败会回 stopped/0 | `ecb83544b48126d700e803d1d558ef158346961a82d0fc5fd5fe77d8befa85df` |

根方先报告的**纯本地配置构造探针**只有工具stdout，无独立文件。获准后作者在 UTC `2026-10-08T11:27:36.159574+00:00` 独立重跑纯构造模拟：实际Python3.14.0、将 sys.stdout/sys.stderr 设为 None，`uvicorn.Config(lambda...,use_colors=None,log_level="warning",access_log=false)` 得 ValueError “Unable to configure formatter 'default'”，cause为None无isatty的AttributeError；use_colors=false 构造成功。各次使用deepcopy默认配置，避免False污染下一次；print在stdout=None时无异常、返回None。私有 `artifacts/research/workbench-lifecycle-20261008/stdio-probe.json` SHA `684ccebef45c23c5ff46e9934571d7ef194797560950fd1e96a9a343533e5f88`。

该模拟没有调用app/server、创建socket/DB或运行pythonw；不授无窗口服务资格。当前 `src/anatrading/cli.py:82–90` serve 仍用 uvicorn.run，未指定 use_colors，其 access_log=false/log_level=warning 不能避开上述路径。必要窄修或预先可靠重定向需经方案/反方后决定。未来owned Server包装须检查started及失败终态并输出typed启动失败；这是未来接口建议，现有run自身的exit3拒绝行为应保留，不能把LastTaskResult0当HTTP ready。

本机 Python314 `Lib/logging/__init__.py:1072,1139–1157` 的输出尝试 stream.write，异常由 handleError 处理，stderr缺席时诊断可缺失。研究结论限源码：后台失败可能没有可见文本，因此要有独立、有限、安全的启动/停止回执；此处未做真实日志输出测试。

Uvicorn 官方 [Settings](https://uvicorn.dev/settings/)核读 logging/timeout 项，显式 use-colors覆盖自动识别，graceful timeout到期开始终止请求。[Server Behavior](https://uvicorn.dev/server-behavior/)的正常退出段核读等待连接/后台任务；[Lifespan](https://uvicorn.dev/concepts/lifespan/)核读启动、shutdown及每 worker独立实例；[Deployment](https://uvicorn.dev/deployment/)核读 programmatic/manager 段，workers会引入进程管理/重启，部分信号操作不支持Windows。项目单写者须保持 workers=1/reload=false，不直接照搬多worker部署建议。

## 正常 owned 停止的证据需求

本机 `workbench.py:114–122,263–268` 在 lifespan finally 中关闭单 owner：停止受理、shield 等待 Store.close、executor.shutdown(wait=True)。这提供正常路径，不能把 Uvicorn请求等待的 timeout 扩写为线程、数据库或整个进程的硬停止上限。受控停止应让当前实例走 should_exit/正常 lifespan，force_exit/TerminateProcess/Task.Stop 不充当完成判据。

应先绑定 root/data_root_id、端口、workbench_session_id、实际 PID/100ns creation/exe 与当前调用资格，再向已认证的 owned 实例请求退出。控制请求被接受只证明意图；须另外核主程序正常返回、Store/锁关闭、同 PID/tick 已终态及必要发布账本。遇身份不符、端口属于别的实例或完成超时，保持未证实，不自动停止外来进程或重启。具体控制通道由待审合同选定，此研究没有新增API。

微软 [GenerateConsoleCtrlEvent](https://learn.microsoft.com/en-us/windows/console/generateconsolectrlevent)仅向共享 console 的组发送控制事件；指定组的 CTRL_C不能按该组限发。推论：前台 Ctrl+C正常退出与 pythonw 的退出路径需分别资格，不能拿前台信号测试替代后台 owned 停止。

## 最小验收分层

1. **静态模板**：官方结构与顺序、固定SID/InteractiveToken/LeastPrivilege、PT0S、IgnoreNew、无RestartOnFailure、不假定StartWhenAvailable补登录；未注册阶段只证明序列化/解析。
2. **本地逻辑**：None-stream异常先复现；身份/根/令牌不符拒绝停止；已有实例与端口冲突拒绝抢占；正常停止仍走单写者清理，在途导入单独核账，全部零行情/SDK。
3. **实际后台**：真实 task action/触发事件与真正 worker PID/creation/exe/SID/console绑定；完成 HTTP readiness、一个正常查询、owned graceful stop、进程终态与锁释放。不用 Config 构造、Task Running、前台测试或 LastTaskResult 单项替代。
4. **真实登录事件与长期运行**：手工 Task.Run 的后台资格与真实 LogonTrigger资格分别记录；持续数日/休眠恢复/故障说明仍独立未完成，不以一次后台启动宣称无人值守闭环。

公开产物仅此研究文件，另有获准的私有纯构造探针及JSON。没有新的交易指标、效力论文或交易效果主张；旧008/011的资料沿用其已记录阅读范围，不宣称重新复现。

## 根方与独立反方补核

根方另读微软 [Settings schema](https://learn.microsoft.com/en-us/windows/win32/taskschd/taskschedulerschema-settingstype-complextype)：Settings 使用 xs:all；电池启动/停止和 AllowHardTerminate 默认均为 true，拟议 false 必须显式写入。上述 LogonTrigger 页的序列要求 Enabled、ExecutionTimeLimit、UserId 按此顺序；本切片同时显式设置 trigger 与 task 的 PT0S。此为定义核查，未注册或触发任务。

独立反方与根方实际读取固定 0.54 的 `lifespan/on.py:65–104`、`server.py:309–312`：关闭异常可被记录为 shutdown_failed/error_occurred，Server.run 仍可能正常返回；force_exit 会跳过 lifespan.shutdown。推论：started 单项不足以证明正常关闭，新包装还须核完成事件与全部失败标志。具体门禁见实现合同；本轮未启动服务器。

独立反方核查 Starlette Response 发送路径：发送 start/body 失败或取消时，普通 BackgroundTask 可能没有执行；同步 BackgroundTask 另在线程池运行。关闭协议采用私有响应的同步 finally 回调，避免服务已停止受理却没有请求 Server 退出。未完成请求体仍可能延迟 graceful=None 的退出；主动结束接收阶段保留后续架构与真实验收。
