# 工作台后台启动与正常关闭真实资格合同 v0.2

2026-10-08。根据042初读的direct任务归属、越过触发时刻后清理两项P1修订。源码基准 HEAD `96657d72ef8efd76d034b9dfe1662d8cea94458b`；[生命周期本地资格](../qualification/workbench-lifecycle.md)记录828项回归及[041代码反方](../reviews/041-workbench-lifecycle-implementation-review.md)。承接[研究017](../research/017-workbench-lifecycle.md)、[实现合同](WORKBENCH_LIFECYCLE_IMPLEMENTATION.md)及[U5旧系统资格](../qualification/tdx-task-runtime.md)。本合同须独立反方和根方决定，再写私有helper/测试/controller；再次独立审helper与sealed动作后才登记。此文不启动进程/服务、不生成helper、不注册/更新/停止Task、不修改产品或生产状态。

## 两层资格与最少必要执行

采用**两次顺序的一次TimeTrigger**，每层一个全新随机精确Task名称、各只CREATE。第一层正常终态、数据重开与精确清理均通过后才允许第二层；不把wrapped动作换成direct再UPDATE同名任务。最多两个已封定Task、两个serve运行，每层最多一次停止POST；无手工Task.Run、重复触发、失败重启或行情刷新。

| 层 | 实际动作与可取得证据 | 不能据此声称 |
|---|---|---|
| wrapped | pythonw私有helper保存原生自身份和**最初**stdin/stdout/stderr状态，然后调用产品 `cli.main` 固定serve argv；其main返回码、HTTP/root、正常终态和锁重开组成wrapped CLI后台资格 | 生产direct动作已通过、自然Logon、长期运行；不伪造cli内部stopped返回字典 |
| direct | 另一个新Task动作精确 `pythonw -X utf8 -m anatrading.cli --root <data/local> serve --port 8791`；外部核真实listener worker身份、HTTP与Task退出及重开 | 内部stdio/GetConsoleWindow自报：本层标not_observed，不能沿用wrapped结果；PE GUI只提供静态关联 |

direct同轮执行是必要的最小动作资格，避免helper改变模块加载/调用方式后就宣布真实生产动作可用。本轮仍用TimeTrigger替代资格启动事件，**不授自然LogonTrigger事件或持久生产登记资格**。自然登录、持续数日/休眠/故障恢复、正式dailyTask、长期日历、全市场日线/自选分钟和慢receive治理继续open。

## 固定目标、初始只读证据与数据边界

项目 `C:\Users\<user>\Anatrading`（`<user>` 仅为原用户名的脱敏占位），数据根固定其现有 `data/local`，资格端口固定8791；不改8765产品/采集绑定，不使用17709。2026-10-08T12:20:22.2162715Z作者只读Get-NetTCPConnection观察8791监听数0；根方随后另核8791/8765均无listener及Anatrading任务无记录。这仅说明各自观察时刻，正式登记前须重新核精确目标。

真实日线原件 `data/local/acquisition/ad38b26212eb4e7ba6f58a57dc9e2c78/after.day` 本次只读SHA仍 `f9271218e4ae49729d4b38976552432da7bf529aa677a2c89358fa5df6887f30`。目标既有快照固定 `c3f950f6002fa14ea4569e2e7075722a3c4df897628e6d63e6b4e981cbffd39c`，7068行，窗口源序号7066—7068；准入时须实际重新核Store/query与原CAS引用，不能单凭历史文档验收。

允许正常现有锁/Store/数据库生命周期、query/catalog/attempts和**精确同Q的既有export派生写入**。HTTP `/api/export` 会写 `root/exports/<snapshot>/<query_id>.json|parquet`再回读，不能称文件系统零写。允许已存在相同派生文件验证，不泛清理exports。不发/import、geometry-export、采集/refresh/订单/SDK/客户端GUI请求；不恢复原件、不改解释/格式/schema。原raw、快照/attempt/catalog逻辑及来源journal内容不变，不以DuckDB物理文件逐字节相同约束正常打开/关闭。

原minute run `20dc43a410af406aa6ba099ce2015f1c` 的refresh_unknown保持。每层前后只读核current/receipt SHA、状态/run和marker/dispatch存在性；来源基准以现场sealed观察为准，已知current/receipt SHA `5fa6af4427152614838483704e9562c4200cdbb08c32e21ad0c7f2d7de1fb343`。任何变化记源状态受外部改变/资格未通过，不覆盖恢复，不归因于无证动作。

## 封定manifest与准入顺序

全部私有文件在 `artifacts/qualification/workbench-background/<UTC日期>-<总nonce>`，不进git。manifest strict UTF-8/重复键/非有限数拒绝，最大256KiB；字段在helper实现前冻结，至少精确记录schema、总nonce、两层各32hex nonce/TaskName/TaskPath、固定project/root/data_root_id/port、当前交互用户SID、venv launcher路径/hash、原生runtime路径/hash、helper/controller路径/hash、产品与依赖源hash、完整XML文本hash、Start/EndBoundary、baseline快照/Q/raw/export/hash和全部预算。层名只能wrapped/direct，不能接受用户任意argv/根/端口/命令。

- 每层名字 `AnatradingWorkbenchQualification-<该层32hex nonce>`，TaskPath固定根目录；两个nonce不同，不使用公共生产名称。同名存在即停止，绝不Force/UPDATE。manifest路径与所有证据/临时文件规范绝对，写入限制当前qualification目录；root导出派生仅上述精确路径。
- 解释器封定 `.venv/Scripts/pythonw.exe` launcher与真实 `Python314/pythonw.exe` 分开记录；根方当前重核launcher SHA `a23c852a5d2303784c42888745a9376f741a939e3c3b04ef4cd9f3fc7e2a89df`、runtime SHA `d278b258a6d565aa014a4cab0731134facdec77e9b25d97d0c235922353464b3`一致，仍须执行前重核。工作目录精确项目。产品源码与固定依赖读取/hash重核，不以git HEAD单项代替文件内容；不把新文档提交误当已运行源码。
- baseline前先核无既有目标监听/身份冲突，root必须是已存在有效Store和上述快照，锁只能正常取得；busy时停止，不停其他工作台/客户端、不删锁。baseline正常Store query/export/close已授权；不得初始化空root。派生baseline输出destination指私有artifacts，保留完整JSON/Parquet原字节和其SHA。
- 注册前核两个精确Task名称未存在，当前用户/SID和动作均匹配seal；COM首次仅TASK_CREATE(2)。StartBoundary至少仍未来30秒，EndBoundary=StartBoundary+60秒。筹备已越界只能重新封未来时间及相应XML/manifest hash并重审机械字段，不重跑已发生层、不改历史产物。
- 登记回读精确动作/SID/cwd/trigger/settings/root/port及实际有效默认。回读失败先核自己Task身份并disable，随后查询精确活实例与下述Task归属链。只有确证未启动或该层所有已绑定worker/launcher已终态、Task无活动实例，才可注销。若回读已越过StartBoundary、任一worker仍alive或归属/终态不明，保留Task与身份记录，执行最多一次已封定owned停止或继续只读观察；不通过注销隐藏可能活着的服务。不能据“禁用已请求”宣称运行已取消。回读不能只要求默认节点全部出现，U5显示系统会省略默认XML字段；使用原生ITaskDefinition属性独立核实际值，保留提交/返回两份文本及编码说明。

RegisterTaskDefinition调用明确flags=TASK_CREATE(2)、userId=sealed当前SID、password=null、logonType=TASK_LOGON_INTERACTIVE_TOKEN(3)，Principal与trigger也绑定相同SID；不使用不同userId覆写Principal。注册后核实际Principal/触发用户及任务安全身份；名称或SID表示可能由系统规范化，只有成功解析为同一SID才接受，不能凭字符串近似。未经封定的password/logonType/SDDL/UPDATE均拒绝。SystemRootFolder TaskEnginePID不替代真正worker；该参数检查须进离线controller负例及独立辅助代码审查。

此合同只计划，现场SID/launcher及helper/controller/XML哈希必须后续实际形成；空白/待填manifest不得登记。控制程序在任何操作前重新核seal；私有helper实现需先异常测试再独立审查，不根据此文直接注册。

## 系统定义：有限触发，正常退出

每层只有一个TimeTrigger，不含Logon/Repetition/Restart；当前用户InteractiveToken/LeastPrivilege，IgnoreNew，AllowStartOnDemand=false，StartWhenAvailable=false，Hidden=true。Settings和trigger ExecutionTimeLimit均PT0S，AllowHardTerminate=false；电池两个开关、RunOnlyIfIdle、RunOnlyIfNetworkAvailable、WakeToRun均false。明确Start/EndBoundary，仅限制启动窗口，**不声称边界会结束正在运行的serve**。无SYSTEM/账号密码/S4U。

不得调用Register UPDATE/Task.Run/Task.Stop、WM_CLOSE、signal、TerminateProcess或Stop-Process；不新增守护进程/PID runtime状态。PT0S不表示观察无限，AllowHardTerminate=false不证明正常数据库关闭。Task被接受/Running/LastTaskResult均不能单独充当server ready、进程终态或锁释放。

## wrapped helper：默认stdio与真实main

helper只读取自己的manifest/source身份并写私有资格记录；不会monkeypatch产品、替换标准流、配置额外日志handler或改变SQL/HTTP行为。导入产品前先留存 `sys.stdin/stdout/stderr` 和 `sys.__stdin__/__stdout__/__stderr__` 的is_none与类型名，使用独立文件IO记证据，**保持六个原对象不变**；后续正常退出再比较对象身份。不能用U5的StringIO重定向方式取得此资格。

原生记录实际GetModuleFileNameW路径/二进制SHA、当前PID、GetProcessTimes创建FILETIME整数、OpenProcessToken SID、GetConsoleWindow、UTC与monotonic。stdIO初始结果是实际观察，允许为None或合法流，不预写答案。原生/manifest/nonce/hash不符时不调用serve，写safe失败记录并退出。

固定 `cli.main(["--root",root,"serve","--port","8791"])`，只运行一次。写 `main_return_code` 和安全异常/源码绑定；不得捕获stdout重新序列化或声称直接取得stopped字典。返回0须结合封定main/serve门禁源码、生命周期本地验收、controller正常停止及进程/锁证据；非0/异常不成功。该helper不替代direct `-m`入口；wrapped Task的实触发绑定helper初始记录、实际worker和Task LastRunTime。

初始/终态资格记录各≤64KiB，原子写/fsync；其存在不证明worker仍活，必须实时查询实际PID+creation。helper正常失败/返回也不能把客户端TdxW未知状态取消。

## direct动作：外部身份，有限结论

第二层动作精确生产形式 `pythonw -X utf8 -m anatrading.cli --root <root> serve --port 8791`，不经helper包装、不额外环境bootstrap/stdio重定向。不修改产品添加qualification RPC或PID字段。

controller从唯一127.0.0.1:8791 listener取得**实际worker**PID，但同SID/runtime/root及启动窗口匹配仍不足归属：另一个手工serve可能占端口，而自己的Task已失败。ready及任何stop必须先完成下述机械Task归属；不能凭端口或时间推断。直接进程内部stdio和GetConsoleWindow没有自报，标not_observed；不能把controller自己的GetConsoleWindow、静态PE或wrapped结果充当direct观察。

### Task实例→Action launcher→实际worker的机械归属

对封定精确Task查询活实例，要求一个具体instance GUID；读取其EnginePID仅作父链锚，不把engine当worker。用成功的原生Toolhelp进程快照/CIM父PID资料，从listener worker回溯最多8层；snapshot完整/有界、不凭未匹配的pid列表猜测。每个实际链节点独立OpenProcess核PID、原生creation FILETIME、alive、native exe规范路径/hash；CIM命令行仅查询已识别链节点，不读取/输出其他进程敏感argv。父creation必须≤子creation，PID循环、缺节点、访问失败、tick不一致或层数超限均不能绑定。

链必须同时包含Task instance engine锚及其action launcher，并证明launcher→runtime worker关系。action launcher的native路径/hash及完整argv须与已回读Task动作和manifest完全匹配（Windows参数解析语义及unicode引号按已审controller机械校验，不只检查含-m/serve文字）。launcher和runtime worker可同一PID，仅在同一个原生EXE身份满足冻结Action与runtime身份时接受；不能把当前不同hash的venv launcher和global runtime强行合并。worker的native runtime路径/hash和SID仍必须匹配manifest。

完成首次绑定后，再做一次Task instance GUID/EnginePID及链PID/tick/path/argv观察，全部保持才能ready或停止。父链快照中的PPID不能单独排除PID重用：每节点creation及前后稳定性均须核，旧父对象失踪/后来PID重用按失败处理。EnginePID可能复用，必须也绑定其100ns creation；不同实例、engine或chain变化均zeroPOST。

wrapped也核该Task链，并可用helper自报nonce/PID/tick提供额外绑定；nonce文件存在不能替代实时链/进程。direct没有helper nonce证据，必须真先行观察父链。自己的Task失败但外来listener仍在时，记启动失败/归属未证，只清理自己确已终态Task；不停止外来服务、不抢root锁。若Windows存在更直接ActionPID API，仅经官方原始证据、字段/回收语义合同和独立反方后精确替代；本版不预写未知API承诺，不扩成PID daemon。

direct成功至少要求封定动作真实TimeTrigger、HTTP正确root、既有源读/导出、一次owned停止、Task无活动实例且LastTaskResult=0、原worker真实终态和root正常重开/字节稳定。这授direct后台动作路径的资格，仍不授自然登录或其内部标准流的精确值。

## 有界观察与HTTP读取

每层从StartBoundary起最多120秒观察ready，正常stop后最多120秒观察终态；root每次wait≤30秒并实际核Task/worker。最多6次明确记录的config就绪GET，每请求使用既有≤1MiB、≤5秒、连接≤2秒接缝；它们是有限就绪观察，单请求不自动retry，不反复start Task。listener未出现或读取异常不能据观察期限推定终态。

ready后最多：窗口query一次、完整catalog一次、attempts一次、完整源JSON及Parquet导出各一次；config token只内存，证据存SHA会话ID。窗口query严格7066—7068，与baseline逐字段及source/geometry身份比；两份export固定整批7068的原Q（无cutoff/ordinal限制），必须下载**完整正文**与X-Query-Id/X-Content-SHA256核对，另解析JSON/Parquet核7068/locators/metadata/精确源字段及baseline字节SHA，不拿前几行或首字节时间代替。

完整source export可能超过采集_http的1MiB，允许私有controller另实现封定fetch：只该端口/两条exact export URL，完整正文≤16MiB、总deadline10秒、connect≤2秒，无redirect/proxy/单请求retry；每阶段重核预算，流读和文件hash有界。不要临时修改产品_HTTP_MAX_BYTES。窗口/query/config仍按小正文边界。总分母与实际每请求结果/字节数/SHA记录，超限/超时即停止新读操作并尝试下面唯一owned正常stop，不降采样伪称完整成功。

实际worker每层外部采样private usage，2GiB为qualification资源失败阈值，观测结果不承诺自动硬取消。不将CurrentWorkingSet替代PrivateUsage。资源/HTTP失败后若身份与会话仍可确证且停止POST未用，可仅发一次owned停止；已发送则不追加。root和controller不对原客户端做资源控制。

## 一次owned正常停止与未知处理

使用controller已经核过的**旧config token+root+具体Task instance GUID/engine/归属链+实际worker PID/creation**。POST前再次核原worker仍alive同tick、唯一listener仍是该worker、exe/SID/hash仍匹配，而且同Task instance/engine与整条归属链稳定；变化/权限失败/链不明则零POST，不重新GET新token再关闭另一个服务。向exact `/api/shutdown`发一次空POST，精确Host/Origin/旧token、总10秒/单5秒，strict202固定root ack校验。没有任意PID命令、OS停机或client SDK动作。

本轮不用产品stop-workbench重新GET可能已变化的token；**该命令仍只保有本地测试资格**。此实测验证真实认证endpoint、owned Server和CLI main的启动/退出；不为qualification扩产品expected-session/PID参数或monkeypatch它。

完整202只记shutdown_requested；断连/超时/畸形回执记shutdown_unknown，未发送前身份/预算失败零POST安全拒绝；所有情况无retry、抢锁、删除锁或重启。回执unknown后仍有限观察**同一已绑定worker**和Task，若alive就保留未关闭。observer到期不是终态；状态文件/Task未Running单项也不是。原PID复用需按100ns tick区分，不能停止后来占该PID的进程。

未完成请求体可无限延迟graceful=None，本轮只自己完整有界请求，不测试强制中止slowreceive。此可用性缺口与后续治理继续open；不通过Task.Stop/强杀让资格变绿。若120秒后仍有自建工作台alive，可禁用自己的Task阻止未来触发，但不销毁其身份记录或注销来隐藏alive；明确遗留，保持同句柄后续观察，本轮失败且不得开始下一层。

## 真正终态、重开与精确清理

完整正常证据必须同时：wrapped main_return_code=0（direct Task结果0）、原worker PID/tick确已终态、精确Task无Running实例、root正常Store open/query/export/close成功、所有raw/来源journal hash与逻辑catalog/attempt不变、整批源JSON/Parquet SHA与baseline相等。旧worker外部终态查询权限失败/短暂观测错误继续未知，不重启同层；已有句柄signaled、确证missing或PID被复用按封定native语义分别记。

重开仅在实际worker终态后正常取得原OS锁，不删.operation.lock、不开第二writer；root缺失/空库/初始化标志/原件损坏拒绝，不恢复或创建替代。基线与重开只同现有快照查询及指定destination导出，正常close；DuckDB文件/WAL物理变化不被倒写为源数据变更。

每层先核精确TaskName/SID/action/XML身份，再禁用和注销自己Task，COM核GetTask精确0x80070002及实际worker终态。identity不符即停止，不触他人任务；清理失败记残留并继续精确处理，不批量枚举删除、不递归清理产物。注销不能充当process terminal证据。wrapped清理/重开成功之后才CREATE全新direct Task；direct最后同样清理，两个Task均消失才声称资格任务已清除。

## 先测试、再审辅助代码、最后实测

helper/controller先离线负例：manifest大小/duplicates/nonce/路径/解释器/source哈希/root绑定/阶段/过时trigger、错误SID/动作、wronglistener/worker tick/读权限失败、**同SID/root/runtime的外来手工listener+自己的Task失败、instance/engine PID复用、父链缺失/环/>8层/父比子晚/launcher argv或hash错/前后变化**、超限HTTP/坏ack/重复停止预算、stdio不重定向、main非0/异常、Task默认节点省略有效值、cleanup identity错和alive不作terminal。另测注册回读耗时跨StartBoundary后发现alive，先disable保留Task，未绑定者zeroPOST/不注销，不以根方观察超时清理绿化。测试不读写真实state、不create Task、不load SDK、不触17709。只自己私有files，fake控制器/native结果必须和真实资格分开。

独立读helper/controller/manifest/离线结果后根方封定具体两个动作和清理范围，才一次性执行上述顺序；实际回读、进程与完整数据证据须结果反方，不将828项旧测试或本合同代替。任何一层失败不新增同层run/新Task以绕过未知，下一层冻结；仍可推进slowreceive/日历架构等独立工作。公开结果仅证据范围、SHA和未通过项；SID/token/个人行情/完整manifest留私有。

本合同完成仅设计进展。完整工具目标active，原minute unknown未解除，生产工作台Logon登记和长期无人值守更新尚未实现。
