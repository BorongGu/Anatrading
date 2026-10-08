# 040 · 工作台生命周期方案与实现合同反方

2026-10-08，独立反方 `/root/candle_contract_rebuttal`。全文核读[方案](../contracts/WORKBENCH_LIFECYCLE_PLAN.md)、[实现合同](../contracts/WORKBENCH_LIFECYCLE_IMPLEMENTATION.md)、[研究017及补核](../research/017-workbench-lifecycle.md)，对照当前workbench/CLI、已有owner取消/drain测试及本机固定Uvicorn/Starlette源码。只新增本评审；没有修改产品/测试、启动服务/pythonw/子进程、注册/停止Task、请求行情/SDK或改生产状态。

**最终结论：两项实质P1在合同层关闭，无未关闭P0/P1；根方可据冻结合同作有限解冻决定。** 这仅授权先异常用例、后最小实现，代码反方及本地/真实资格须另完成，不能授予后台已启用、正常进程已终态或无人值守闭环。

冻结锚点：PLAN SHA `9f55e3f12d5d7b6f8e8aa001882c4275fec8bcf1172bd6914c19c197469be0b1`；IMPLEMENTATION SHA `4cf6b68d70676c93c375a5d75ce575fafe94e665a92bf7f12489647870806f31`。研究末尾追加定义/固定版本补核，未改这两份合同的SHA。

## 实质反方与修订

| ID | 级别 | 可复现失败路径/源码 | 合同修订与闭环 |
|---|---|---|---|
| WL-01 | P1 | route置accepting=False/一次标记后仅把callback交普通BackgroundTask；本机Starlette Response先await send-start/send-body，再运行background。send任一阶段抛异常/CancelledError会跳过background，重复请求又跳过callback，留下不受理却未请求Server退出的半关闭服务。同步BackgroundTask还有线程池切换。 | 已关闭：私有JSONResponse的try/finally同步调用app内once闭包；正常body后、send异常/取消均调用。closure先标called后仅设置所属Server.should_exit，至多一次，无IO/await/threadpool/call_soon。缺callback503保持accepting；显式async函数/async __call__和非callable构造时拒绝。先写send-start/send-body异常及取消、重复请求、失败后不遗留半关闭负例。 |
| WL-02 | P1 | 拟serve只核server.started就返回stopped。固定Uvicorn LifespanOn将owner.close/lifespan异常记录到shutdown_failed/error_occurred，Server.run仍正常返回且started保持True；force_exit还会跳过lifespan.shutdown。此时正常关闭未证却exit0。 | 已关闭：lifespan="on"，返回成功同时要求started严格True、force_exit严格False、life存在、startup_failed/shutdown_failed/error_occurred严格False、shutdown_event.is_set()严格True。缺字段/未完成/失败均typed非成功。假Server覆盖每个失败路径和SystemExit，只有全正常才stopped；真实PID/锁/Store重开资格仍独立。 |

上述是设计审查闭环，尚无新增产品测试结果。当前旧uvicorn.run的单worker/notstarted返回路径及Server.startup明确STARTUP_FAILURE已exit3；没有证明现有CLI会把该失败报stopped/0。WL-02针对新owned包装的成功判据，不能倒写为旧代码已存在的false-success。

## 关闭门禁、接受点与未解决边界

现有Store owner为单线程FIFO；submit验accepting/32pending，call及import已提交future用shield，close停止受理后把Store.close排在accepted操作后。合同保留这些关系，禁止另一个close线程、取消已accepted操作或用网络取消宣布提交失败。callback请求退出不直接释放锁；只有lifespan/Store close与后续真实观察能证明正常关闭。

POST shutdown先验精确Host/Origin/单一token、零query/实际空body；非法/断连没有动作，缺callback不改accepting。合格请求在event-loop同步门禁，两个响应共享once闭包；202及固定root ack仅为停止意图。callback生产实现限已构造owned Server的同步setter，不能接受外部PID/命令/signal或任意用户执行逻辑。

**明确保留的可用性缺口（不作为当前薄接缝P1）**：关停前进入body receive且一直不完成的请求并未accepted；本机h11.shutdown对未完成cycle只置keep_alive=False，graceful=None仍可能无限等待该HTTP连接/task。当前合同只承诺body完成/断连、抵达submit门禁后503，不主动中止receive，不承诺无条件最终/限时退出。原方案模糊处已补此限定；测试“未完成body停止后拒绝”须在完成/断连后的门禁检验，不能以永不结束body证明成功退出。接收阶段与stop事件竞争/慢连接治理保留为完整系统必需后续，不能永久删去或将薄切片当全目标完成。观察超时保持未关闭，不kill/restart/抢锁。

## stop与预算的窄设计

stop位于EvidenceStore CLI分支之前；无PID/SDK/client-state/Task操作。10秒总deadline与继承预算取早，单次5秒、连接≤2秒、正文≤1MiB，复用固定localhost无代理/重定向/重试接缝。_config只加兼容keyword budget=15，stop传5；原采集语义不放宽。_post_guard在stop作用域置None，防止关闭POST消费继承的行情guard/写控制；finally恢复两个ContextVar，包括所有异常/参数拒绝路径。

GET config必须成功且root ID/必要字段匹配，csrf为当前token_urlsafe(32)的43位ASCII安全形状。之后只发一次旧token绑定的空POST，不能GET换token后关闭新会话。root不符/GET失败/预算耗尽零POST；两请求之间不重设预算。POST202要求strict JSON固定两字段/root ack；请求后断连/超时/畸形/其它回执均shutdown_unknown非zero，只有合同列出的明确403/503安全拒绝可typed拒绝，不回显原正文。202不是process_closed；耗时/错误都不授权抢锁、杀进程或重新发送。

这个CSRF+root边界用于本地误投/跨源保护，不能宣称能抵御可GET config的恶意本地进程。token仅内存，不能出现在参数、日志、Task或公开仓库。

## stdio与Task分层

None标准流是研究017纯配置模拟及Python官方定义范围，尚未实际启动pythonw。use_colors=False解决默认formatter的isatty初始化；显式配置副本避免全局False污染负例。默认StreamHandler缺stderr可能无可见日志，不能据无输出/Config构造/LastTaskResult判ready或成功。typed退出码、HTTP root/会话、实际进程及私有资格必须结合；持久诊断日志仍独立未实现。

本机Uvicorn固定字段检查属于0.54.0封定接缝，生命周期源码核读SHA `8844cf163e921613c33dc75e1b17dae372ca226254ecc2398bb41451ea4170f1`；不推广为任意Uvicorn版本API。此次线上Starlette/Uvicorn两次文档打开失败，未计入独立网页阅读；本反方实际依据本机源码和研究017已标阅读范围作判断。

纯task_xml只生成未注册Logon定义：规范绝对路径、pythonw、list2cmdline/ElementTree escaping、当前SID、InteractiveToken/LeastPrivilege、IgnoreNew、两层PT0S、无Restart、AllowHardTerminate=false，电池/idle/network等固定设置。Settings xs:all与Logon节点顺序由研究补核记录，实际COM解析/有效默认/真实SID运行仍待资格。Hidden与IgnoreNew均有限语义，不能证明无console、跨任务重复禁止或自动故障自愈。

## 有限解冻与后续资格

根方决定后可仅解冻实现合同列明的workbench route/私有响应、cli薄接入、小workbench_lifecycle模块、_config可选budget及针对性测试/说明；不改Store/schema/数值/源格式/分析/UI、调度控制或生产journal，不增daemon/PID状态/服务/依赖。

须先负例再实现；本地focused/完整回归、独立实现反方不能由本页替代。之后真实资格另封精确Task/manifest/cleanup与有限观察：pythonw默认stdio、实际worker PID/100ns creation/exe/SID/console、HTTP root ready、真实只读query/export/raw、202后独立终态/Task非Running/Store重开与锁释放。TimeTrigger、Logon实际事件、正式持久登记、数日/休眠/故障持续运行分别验；没有任一已执行。本轮原minute unknown不因workbench生命周期定义解除，完整工具目标保持active。
