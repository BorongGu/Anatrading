# 工作台自动启动与正常关闭方案 v0.1

2026-10-08。用户持续免手工下载目标需要工作台在 Windows 登录后可用，并能正常释放唯一写者。此文先审架构；独立子 agent rebuttal、实现合同及根方决定闭合前不编码、不启动工作台或注册任务。当前客户端 minute refresh_unknown 保持，不改变它、不发送行情、SDK或委托请求。

## 选择与范围

| 路线 | 成本与失败边界 | 决定 |
|---|---|---|
| 新 PID 文件、应用守护进程/Windows Service | 新增 PID复用与会话绑定、启动/崩溃journal、守护进程和应用双层重启、服务权限/账户、锁接管及卸载生命周期 | 本切片不引入；没有现存服务需要迁移 |
| 系统 Task 直接运行 pythonw serve，复用 root OS 锁 | Windows负责触发和同任务 IgnoreNew；应用只有已有 _StoreThread/Store 生命周期；重复实例由root真实OS锁拒绝；退出由认证HTTP请求与Uvicorn正常关闭负责 | **采用此最简路线**，不新增runtime PID状态或daemon |

首切片仅工作台应用的正常关闭接口、stop命令、显式Server绑定及无stdio启动适配，以及可审系统Task定义。正式持久登记、真实Task启动和关闭必须另有精确动作/清理合同及独立资格。应用 serve/import/due 不自动注册任务。全市场日线、自选分钟、长期日历/计划续期、正式dailyTask、停机积压和界面失效呈现仍属于完整目标。

## 当前源码事实

- `workbench._StoreThread` 用 max_workers=1 的 ThreadPoolExecutor，Store open/call/close 都在同一线程。submit先验accepting与32项pending预算；call及已提交import用 asyncio.shield。close先accepting=False，再将Store.close排在已提交操作之后，最后executor.shutdown(wait=True)。
- `create_app` lifespan正常结束会await owner.close。现有测试分别覆盖已接受import的HTTP等待取消后仍提交、关闭等待其完成、关闭期间503、最终锁可重开，以及启动取消时同线程关闭。
- `/api/import` 收请求体时尚未提交；**accepted工作定义为owner.submit已成功**。关闭开始后，新submit必须503，包括关停前已开始上传但关停后才传完的请求；不能将所有已打开连接称为必须入库的接受任务。
- `_LocalBoundary` 已核精确 Host=127.0.0.1:port、Origin、POST单一CSRF token；`/api/config` 提供当前token与data_root_id。每个app创建新随机token，现有采集不会把工作台会话变化当作发布失败后可重投。
- Store持有root `.operation.lock` 的Windows非阻塞OS锁，关闭数据库后释放；第二进程无权删除锁文件或换PID journal抢占。IgnoreNew只防同一个Task并发，跨任务/手工入口仍由此锁保护。
- CLI当前serve调用uvicorn.run，无Server引用、无shutdown callback，且未显式use_colors；尚不适合直接声称pythonw系统启动兼容。

## 固定版本依赖证据

本次只读安装源码：pyproject锁定 `uvicorn==0.54.0`，安装 `uvicorn.__version__`一致。

| 本机源文件 | SHA-256 | 读取结论 |
|---|---|---|
| `.venv/Lib/site-packages/uvicorn/server.py` | `c1be9d133467a42ab88d7168e408ef5a90257661a901899426214a3d1fc2d026` | should_exit被main_loop检查；shutdown先停止新listener/连接，再等待已有connection/task，再发送lifespan.shutdown；graceful超时才cancel任务 |
| `uvicorn/config.py` | `cf91c6ffae283a2b2020da954b4cc4ed47d3246cb062afd09fb77d98e4c5ca87` | timeout_graceful_shutdown默认None；use_colors显式bool会覆盖两个formatter；默认handler绑定sys.stderr/stdout |
| `uvicorn/logging.py` | `9020759f8e41e4ee794920298afdb1e94406dcb9c5a8d946bdca211b20306e55` | formatter use_colors=None会直接sys.stdout.isatty；False绕过该访问 |

实际读取Server.run/serve/startup/main_loop/shutdown/capture_signals、Config日志配置及lifespan/on.py。None超时表示正常drain没有应用设置的自动取消期限；二次SIGINT会设置force_exit，应避免把强制信号或系统Task Stop当正常关闭。

## 应用正常关闭最小接缝

CLIserve改用 `uvicorn.Config` + `uvicorn.Server`，仍127.0.0.1、one worker、asyncio/h11、无access log；明确 `use_colors=False`、`lifespan="on"`、`timeout_graceful_shutdown=None`。create_app只接受CLI构造的内部on_shutdown callback；callback只设置该Server.should_exit=True，HTTP不能传PID、root路径、命令、signal或外部程序。

固定0.54源码中，Server.startup遇lifespan.should_exit会sys.exit(STARTUP_FAILURE=3)，现有uvicorn.run也在未started时exit3；本轮没有证明现有路径错误返回stopped/0。新增显式Server的目的为绑定owned关闭callback与统一安全退出接口。wrapper捕获启动SystemExit并typed `workbench_start_failed`、exit2；Server.run若正常返回但未started也拒绝。**started=True也不能独自证明正常关闭**：LifespanOn可能记录shutdown_failed/error_occurred后让run返回，force_exit还会跳过lifespan。仅started=True、force_exit=False、startup_failed/shutdown_failed/error_occurred均False且shutdown_event.is_set()才stopped；状态缺失或失败typed workbench_shutdown_failed。SystemExit0/3及启动后异常均不转成功。Task运行/退出码只是一项观测，ready/close资格须HTTP root、实际进程与锁/库证据，不能仅凭LastTaskResult=0。

新增 POST `/api/shutdown`：沿用现有Host/Origin/CSRF；拒绝query参数、非空请求体、重复/无效鉴权，空流通过才动作。未绑定callback的直接create_app实例应返回503 shutdown_unavailable且不改accepting，避免接受关闭但无法退出的半关闭服务。

通过校验后，同一event-loop中立即owner.accepting=False，返回HTTP202、固定 `status=shutdown_requested` 和当前data_root_id。采用一个私有JSONResponse子类，在发送响应的try/finally中调用app内同步request_exit闭包：正常发送后调用，send异常/取消也调用；闭包先标callback_called再执行Server.should_exit setter，至多一次。避开普通BackgroundTask在send异常后不运行、同步callback另进threadpool的路径。客户端可能收到shutdown_unknown，服务仍正常走退出，不能半关闭。不能把HTTP202称为数据库已关闭。重复认证请求如仍能到达，幂等确认同一请求；不能取消已accepted future、上传提交或跳过lifespan.close。

界面新请求可能在Server检查退出前短窗口到达；owner门禁保证不再接受新Store工作，返回service_closing。已accepted操作与提交临界段继续完成；生命周期正常关闭排队在其后。已接收body但尚未submit的上传到门禁时被拒绝，不能挂起队列或自动重传。无需新Store实例、后台close线程或持久停止标记。

可用性边界必须保留：上述body未完成上传只有在body完成/断连、route走到submit门禁后才拒绝；当前接收阶段没有与stop事件竞争的主动中止机制。卡住的连接可能使graceful=None无限等待，202不证明最终闭合，也不承诺无条件限时退出。观察超时保留未关闭、不kill/restart；接收阶段结束与慢连接治理仍为完整系统后续必验项，不能永久排除。此切片不静默加入receive/stop事件竞争架构。

正常drain可能长于stop客户端等待；不会把超时推定为写者终态。不设置短graceful超时、不Stop-Process、不删除锁或自动另起实例。系统注销/停电/他人强停并非此正常关闭路径的资格，继续由既有原件/事务/attempt恢复机制处理；不声称在任意系统断电中都能完成接受任务。

## stop-workbench 命令与身份

新增 `--root <指定根> stop-workbench --port <指定端口>`，不打开EvidenceStore，不查询/操作PID，也不接触客户端采集journal。复用已有采集 `_config`、`_request` / `_deadline` 有界本地HTTP接缝；_config仅增加可选budget=15参数，stop传5，原采集默认行为不变。本命令总预算10秒与继承deadline取较早，单请求至多5秒、连接至多2秒、正文至多1MiB，无代理/重定向/自动retry。该作用域将_post_guard置None，避免运行继承的采集guard；finally恢复两个ContextVar。不因GET耗时重设POST总预算。

先GET该端口config，严格校验data_root_id等于指定规范root的ID、当前token为当前token_urlsafe(32)产生的43位ASCII urlsafe形状及必要字段；窄校验只加在stop入口。只有匹配才POST空body，Host/Origin和token准确绑定此端口/会话。GET预检网络/配置异常、root不符或预算耗尽时typed拒绝且零shutdown POST。若GET后工作台替换，新随机token将使旧POST拒绝；不得更新token再重试关闭另一个会话。POST202及固定ack/root ID须完整校验；只能输出shutdown_requested，不能输出process_closed或stop_success。已尝试POST后的断连/超时/无法校验回执记shutdown_unknown，不称已失败或已关闭，不抢锁、不再POST、不杀进程；明确鉴权等拒绝可记安全typed拒绝。即使服务随后关闭也不能改写这次网络回执结论。

token只在内存，不写日志、Task参数或publicgit。此CSRF边界阻止跨源页面意外操作，不承诺抵御能GET本机config的恶意本地进程；根身份用于误投防护，不能宣称密码级服务认证。

## pythonw、stdio 与日志

实际本机 Python314/pythonw.exe SHA `d278b258a6d565aa014a4cab0731134facdec77e9b25d97d0c235922353464b3`，PE machine=AMD64/subsystem=2已只读核验。它证明GUI子系统二进制身份，不能单凭PE断言每种Task环境下sys.stdout/stderr都为None。

本次未启动pythonw。U5真实helper确有GetConsoleWindow=0，但helper在自身开头把stdout/stderr改为StringIO，所以原资格没有保留默认stdio。纯本地模拟sys.stdout/sys.stderr=None时，当前DefaultFormatter(use_colors=None)确抛AttributeError（isatty）；False成功。root另有Config构造模拟证据。**实际系统Task默认stdio仍须首次真运行前观察记录，不能用模拟代替。**

CLI/main已有hasattr(stream,reconfigure)检查，可接受None；serve启动和main末尾输出不得假定存在write/flush/isatty。显式False只解决formatter初始化；默认StreamHandler(None)回退stderr仍可能为空，错误日志不能被声称已持久保存。首切片不建立无限日志、PIDdaemon或新状态库；将无stdio下Config/Server启动失败处理与安全退出码纳入先行异常测试，Task资格另用封定私有观察文件捕获真实身份、stdio初始状态、Task结果和进程终态。若需要产品持久日志，另在实现合同选择有界最小落盘策略，不能临时假设console日志已足够验收。

## 系统Task定义与操作边界

直接绝对 `.venv/Scripts/pythonw.exe -X utf8 -m anatrading.cli --root <规范root> serve --port <固定port>`，固定项目工作目录与当前交互用户SID。一个精确名称的Task，LogonTrigger针对该用户；资格另允许一个封定的一次TimeTrigger，不把两种触发与生产登记混为已通过。

拟设置 InteractiveToken/LeastPrivilege、IgnoreNew、无RestartOnFailure/Repeat、AllowHardTerminate=false，Settings及LogonTrigger两层ExecutionTimeLimit=PT0S。两项电池开关显式false；RunOnlyIfIdle/RunOnlyIfNetworkAvailable/WakeToRun/StartWhenAvailable=false，无强停时限；普通关闭只走认证endpoint。LogonTrigger按Enabled→ExecutionTimeLimit→UserId顺序；Settings为官方xs:all，无固定子项次序要求。Hidden不证明无窗口，窗口资格须真实pythonw身份及GetConsoleWindow独立核验。明确读回实际有效属性，不能只看提交XML。跨用户或未登录不承诺运行，失效呈现及自然登录后的工作台恢复保留后续验收。

首次登记前核精确Task不存在；不Force覆盖，不更新/停/删除不匹配任务。登记、导出XML、动作/SID/root/port/解释器指纹回读和正常停机/禁用/注销范围必须另封manifest审核。应用不管理登记，资格清理只针对自建精确Task；Task注册成功不证明workbench成功，LastTaskResult单项不证明数据库已正常关闭。

## 先测后实现与真实资格

先异常/故障用例，再解冻必要文件：缺callback、非法Host/Origin/token/重复鉴权、query/body/未知字段、重复shutdown；shutdown开始后新submit/import拒绝，已accepted慢import及HTTP取消仍完成；body未完成上传不算accepted，root/session变化、超时/断连不重投、不抢锁。stdioNone/formatter颜色、Config/Server callback与gracefulNone先用no-network构造测试。保持已有cancel/owner队列/源JSON与Parquet导出回归。

真实资格单独审一份自建Task动作和有限观察预算：系统时钟启动pythonw真实CLI，核实际原生进程exe/PID/creationFILETIME/SID/console/defaultstdio、Task有效配置；GET config确认指定root及会话，旧source query/JSON/Parquet/raw hash稳定。观察窗口不会发刷新/导入；旧快照只读无市场请求。

正常stop资格：认证POST先得202；独立观察该原生PID/creation终态、Task不再Running，再用指定root正常打开Store并关闭，证明OS锁释放和库可读；重开既有快照/原件及完整源export字节仍一致。另用合成ASGI接受慢write证明drain，不能用真实只读场景替代在途提交安全。若超观察预算而进程仍活，明确未完成正常关闭；不通过Task Stop/强杀让资格变绿。重复启动同root/不同port需拒绝且原运行不变，重复Task触发IgnoreNew须实核。精确注销自建Task及残留检查仍独立记录。

正式工作台Task可用之后，才能串联dailyTask/日历续期/到期积压；工作台就绪应由config/root核证，无任意sleep假装ready。原客户端refresh_unknown继续受已审恢复门禁，工作台启动成功也不能授权新行情。完整系统目标active。
