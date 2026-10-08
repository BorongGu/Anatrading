# 工作台正常关闭与未注册Task实现合同 v0.1

2026-10-08。承接[方案](WORKBENCH_LIFECYCLE_PLAN.md)及[研究017](../research/017-workbench-lifecycle.md)。独立反方、修订和根方决定前冻结产品。仅解冻可测试的应用接缝和纯XML生成；不授权真实serve/pythonw启动、生产stop、任务登记/停止/删除或行情请求。无需交易效力主张，完整持续采集/分析目标保留。

## 目标与文件

最小路径：WindowsTask直接pythonw运行现有单写者，应用自管正常退出；不建PID文件、daemon/service、重启journal、数据库或新第三方依赖。

拟解冻：`src/anatrading/workbench.py` 的shutdown route/私有响应；`cli.py` 的serve/stop薄命令接缝与退出码；新增小模块 `workbench_lifecycle.py` 的serve/stop和纯task_xml；`tdx_acquisition.py` 仅_config增加兼容budget参数；新增 `tests/test_workbench_lifecycle.py` / `tests/test_workbench_stop.py` 及必要既有workbench/CLI测试；使用说明另按根方定案限定。不增通用进程框架。不改tdx_schedule控制、来源journal、Store/schema、numeric、格式、分析或UI。

模块入口冻结为 `serve(root,*,port=8765)`、`stop(root,*,port=8765)`、`task_xml(root,port,python,working_directory,user_sid)`；由CLI薄接入，serve内部创建app/Server，stop复用既有HTTP。

成功条件分别是：认证关闭立即拒绝新Store工作、已accepted工作正常drain；stop准确绑定root/会话且未知不重试；显式Server可无stdio配置且启动失败非成功；生成符合固定设置的未注册LogonTaskXML。后台启动、进程/锁终态和持续自动更新属于另封真实资格，不能由上述本地成功替代。

## shutdown endpoint 固定协议

`create_app(..., on_shutdown=None)` 仅接收CLI内部同步无参callback，生产callback只设置本Server.should_exit=True；无可选PID/命令/路径/signal。构造时非None且非callable、inspect.iscoroutinefunction(on_shutdown)或其__call__为协程形式，均ValueError(`invalid_shutdown_callback`)；不接受callable却返回未await协程的async callback，不支持用户自定义执行动作。

POST `/api/shutdown` 复用 `_LocalBoundary`：精确Host=127.0.0.1:port；POST必须有精确Origin与一项正确X-Anatrading-Token；重复Host/Origin/token均拒绝。token不进URL、日志或落盘。参数集合为空，重复/未知query拒绝；请求体严格空，读流遇任何非空chunk或ClientDisconnect均不动作。无JSON解析或content-type扩展；Content-Length的语法由现有HTTP协议处理，应用以实际body为准。

callback未配置时503 `{error:shutdown_unavailable}`，不得改变owner.accepting。其它鉴权/请求失败沿用现有安全error响应，没有callback、关闭或新线程副作用。

所有校验完成后，在同一event-loop同步设置owner.accepting=False、shutdown_requested=True；返回202，JSON固定且恰为 `{status:"shutdown_requested", data_root_id:<当前root64lowerhex>}`，Cache-Control:no-store。重复合格请求仍202同ack；不重新接受Store工作。

使用一个私有JSONResponse子类：`__call__` 的try中await普通JSONResponse发送start/body，finally调用app内同步request_exit闭包。正常callback发生在body发送后；send-start/send-body异常或CancelledError也执行。闭包先将callback_called置True，再调用一次同步setter；重复响应不能再次callback。不得使用会跳到threadpool的普通同步BackgroundTask、call_soon、force_exit或操作系统signal；不另起close线程。内部callback不执行IO/await，不处理不受信任动作。即使客户端回执未知，owned正常退出仍已请求，避免owner已False却Server一直不退出的半关闭状态。

202只证明接收停止意图。Server.shutdown按固定uvicorn路径停止listener/连接、等HTTP任务，再lifespan.close；任何网络断连均不保证客户端收到ack。实际释放锁、database close与进程终态须另核。

## accepted 与 drain

accepted定义为 `_StoreThread.submit` 成功，不按连接/开始上传/进入route定义。已有单线程FIFO、asyncio.shield及lifespan owner.close保持；close排队在先前accepted操作后并shutdown(wait=True)。新query/export/import的submit一律503 service_closing，不取消正在提交的attempt，也不因HTTP waiter取消而终止已acceptedfuture。

关停前开始但body关停后才传完的import尚未accepted，submit必须503；upload_busy按既有finally解除，不入库、不自动重传。对已经accepted但HTTP等待取消的慢import，关闭仍等待其真实Store操作完成与记账；不能把请求task取消等同于写操作取消。

此503保证限于body已经完成或断连后到达门禁。首切片不主动中止仍卡在receive的连接；其HTTP task可使graceful=None无限等待，故202与server.should_exit不证明最终闭合，不授无条件限时退出资格。观察超时须保留未关闭、不kill/restart、不抢锁；仅完成或断连的未accepted上传纳入本地停止测试。receive与stop事件竞争及慢连接治理另写架构/反方后实现，保留为完整系统必需后续，不能从原用户目标永久删除。

Config固定 `timeout_graceful_shutdown=None`，不添加短graceful自动cancel，不force_exit，不通过Task.Stop/Stop-Process完成资格。正常drain可超客户端10秒；此时只能报告停止未知或已请求，禁止抢锁、删除.operation.lock或自动另起root写者。强停/断电的事务恢复仍沿用既有Store合同，此切片不授任意电源故障下的正常drain保证。

## 显式Server与stdio

serve使用 `uvicorn.Config(app,host="127.0.0.1",port=...,workers=1,loop="asyncio",http="h11",reload=False,access_log=False,log_level="warning",use_colors=False,lifespan="on",timeout_graceful_shutdown=None)`；保留已有本机范围。serve构造app/server并绑定专有setter，运行Server.run。callback运行前Server已构造；不得将外部端口的server对象注入。

证据纠正：固定0.54现有Server.startup失败以及现有uvicorn.run的未started单worker路径已exit3；无已证false stopped/0缺陷。新增包装为owned关闭与安全CLI接口：启动SystemExit或正常run返回但not server.started均typed StoreError(`workbench_start_failed`)，main exit2；SystemExit0与3都不能转成功。已started后异常终止typed `workbench_shutdown_failed`；初始化/绑定/生命周期异常不得吞为stopped/0。不捕获普通KeyboardInterrupt并伪称正常drain；沿用CLI interrupted语义，不能据取消码证明已关闭。

固定源码LifespanOn.shutdown/main会把失败记录到startup_failed/shutdown_failed/error_occurred，并可能让Server.run正常返回；force_exit会跳过lifespan。因此正常返回后必须同时：server.started严格True；server.force_exit严格False；server.lifespan存在；life.startup_failed/shutdown_failed/error_occurred逐项严格False；life.shutdown_event存在且is_set()严格True。状态缺失、无法读取、event未set或任一失败都typed workbench_shutdown_failed；只有全部通过才 `{status:"stopped"}`。这一封定源码状态检查也不替代真实PID/锁/Store重开资格。未配置lifespan="on"的自动fallback不接受为成功依据。

use_colors=False避开默认formatter的sys.stdout.isatty；sys.stdout/stderr可能None，reconfigure/print/错误报告不得假定流有write/flush/isatty。无stdio测试使用独立默认logging配置副本，避免一次False污染下一次None负例。当前Python print在stdout=None时无异常；不可根据无输出称任务成功。default StreamHandler缺stderr可能没有可见日志，首切片不创建无限log/PID状态；typed退出码、HTTP/root、真实Task身份及私有资格记录共同验收，持久诊断日志另审。

## stop-workbench CLI 与预算

`--root <目标根> stop-workbench --port <端口>` 在EvidenceStore分支前；不构造Store、查PID、读/改采集state、加载SDK或注册Task。规范root仅用于data_root_id；port非bool整数1—65535且不为客户端17709。参数/root编码异常AcquireError(`invalid_workbench_control`)，防止未处理UnicodeError。不得将退出名为stopped/process_closed。

复用acquisition._config/_request/_decode_json/data_root_id/_remaining/_deadline。_config新增仅keyword budget=15，原调用保持15秒默认，stop显式5；不放宽原config语义。stop窄补csrf_token恰43位ASCII `[A-Za-z0-9_-]{43}`，对应本机token_urlsafe(32)，不符AcquireError(`workbench_identity_mismatch`)。_config仍验200、指定rootID、现有格式/retrospective/upload预算，畸形/重复JSON/超正文拒绝。

总预算：monotonic+10秒与继承_deadline取较早；阶段之间不重设。作用域_post_guard=None，避免停止POST运行任何继承的行情guard；无论成功/拒绝/异常，finally复原两个ContextVar。每请求budget取5秒与总剩余较小，原_http连接至多2秒、正文至多1MiB、零重试/代理/重定向。POST前重核_remaining；若已耗尽则不开始停止POST。HTTP同步call不承诺进程硬强停。

一次GET `/api/config`：失败/root不符/token畸形/预算耗尽直接typed拒绝，零POST。成功后内存持有该token/root，发一次POST `/api/shutdown`、body=b""、精确Origin与X-Anatrading-Token；不再GET换token。服务A替换成同root的B时，B新token拒绝旧请求；不能把root相同当作同一会话重新鉴权重投。

POST202响应须strict JSON，恰status/data_root_id两个字段、匹配固定ack/root；成功输出同ack，仅shutdown_requested。允许403且safe JSON error恰为invalid_host/invalid_origin/invalid_token，或503 shutdown_unavailable时typed安全拒绝（不可回显原服务正文）。已开始POST后的连接错误/超时/不完整/畸形JSON/其它status/回执root不匹配均返回 `{status:"shutdown_unknown", error_code:"shutdown_ack_unverified"}`，CLI exit2；无retry/新会话POST/抢锁/杀进程。GET错误沿用安全typed错误；完整202不声称已关闭，即使随后立即断开也保留请求已接受的准确语义。

## 未注册Task XML

小模块纯 `task_xml(root,port,python,working_directory,user_sid)`，python参数为绝对pythonw.exe，只返回Unicode XML文本，xml_declaration=False；不注册、query/change Task或启动进程。root/python/cwd必须absolute规范文本；port如stop有效且非17709；SID沿用已审当前普通用户 `S-1-5-21-...` 严格形状。NUL/控制字符、无法规范编码或不合法参数均AcquireError(`invalid_workbench_task`)，XML值由ElementTree escaping；Arguments用subprocess.list2cmdline，不能拼shell命令。

命名空间TaskScheduler2004、version1.2。一个LogonTrigger，按官方已核Enabled=true→ExecutionTimeLimit=PT0S→UserId=<同Principal SID>顺序；不加Repetition、EndBoundary或资格TimeTrigger。Principal为同一用户InteractiveToken/LeastPrivilege。Settings明确：MultipleInstancesPolicy=IgnoreNew；AllowHardTerminate=false；ExecutionTimeLimit=PT0S；DisallowStartIfOnBatteries=false；StopIfGoingOnBatteries=false；RunOnlyIfIdle=false；RunOnlyIfNetworkAvailable=false；WakeToRun=false；StartWhenAvailable=false；Enabled=true；Hidden=true；无RestartOnFailure。Settings官方xs:all，不把子节点排序误当业务资格。两个PT0S均须验证，避免trigger限时遗漏。

动作Command为绝对pythonw.exe，Arguments固定 `-X utf8 -m anatrading.cli --root <root> serve --port <port>`，WorkingDirectory精确项目目录。Task名称、实际EXE/runtime指纹、XML哈希和注册操作放在后续sealed资格manifest；此函数不生成/覆盖名字或授予已登录/ready状态。Hidden仅为Task可见性，不授无console资格。IgnoreNew仅限制同Task；跨任务和手工重复仍依赖root OS锁，端口或锁冲突不得停止已有占用者。

正式持久登记与一次TimeTrigger资格另合同审，首次精确名称不存在才CREATE、不Force；更新/禁用/删除仅自己manifest与回读动作/SID完全一致的Task。应用不会偷偷登记或把未注册XML称无人值守已启用。可另审纯COM NewTask.XmlText解析，不调用Register/Run/Stop。

## 先行异常测试与分层验收

先负例再代码：shutdown缺callback、非callable、鉴权/重复header/query/非空body/disconnect，失败后仍可query；202幂等callback一次；send-start/send-body异常/CancelledError仍request_exit一次。已accepted慢import/HTTP waiter取消/queuedquery的正常drain，以及未完成body在停止后拒绝；Storeclose同线程、锁可重开及账本终态。

stop测试stub真实边界：wrong root、csrf长度/ASCII、错误/重复/超限JSON、GET超预算零POST、继承guard不调用/两个ContextVar复原、POST明确拒绝与断连/错误ack不重试、同root新tokenB不被关停；assert无Store/SDK/client-state/PID/Task操作。stdioNone先重现默认Config错误，再验False与显式Server参数；fake Server覆盖SystemExit0/3/notstarted、started后shutdown_failed/error_occurred/force_exit、shutdown_event未set及字段缺失全部非success，全部正常状态才stopped。XML路径/SID/port/escaping/顺序/两层PT0S及所有固定开关；无side effect。APIaccepted-write用合成私有root，不上传真实新行情。

本地focused测试、完整Python回归及独立代码反方关闭后，才写真实pythonw资格合同。实际资格封定自建精确Task、有限TimeTrigger/观察、实际runtimePID/creationFILETIME/exe/SID/console/defaultstdio；GET/root/query/full源JSON/Parquet/raw哈希核ready，202后另核同原进程终态、Task非Running、Store正常重开/关闭与旧快照/export不变。超观察期限不是进程终态，不Stop强杀使资格变绿；残留任务/进程需身份绑定及明确清理记录。

TimeTrigger真启动、生产LogonTrigger事件、正式任务持续运行分别验；此合同不执行任何一个。原minute refresh_unknown不因workbench ready解除，正式dailyTask和长期日历/计划续期另验。完整系统目标active。
