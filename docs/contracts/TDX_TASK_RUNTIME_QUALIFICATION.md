# U5 Windows任务运行资格合同 v0.2

2026-10-08。上一轮[U4](../qualification/tdx-daily-schedule.md)为具体代码进展，未获得真实系统触发资格。本轮验证操作系统的触发、解释器身份、无控制台启动和未知状态保留；不会将此资格等同于成功取到行情。等待独立反方和根方决定后才编写私有辅助程序/注册临时任务。产品代码与行情来源合同不变。

## 官方依据与边界

本轮重读微软[注册](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/register-scheduledtask)、[多实例](https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-multipleinstances)、[Hidden](https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-hidden)、[注销](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/unregister-scheduledtask)。注册仅建立任务定义，不证明动作适配平台或成功执行；Hidden控制任务可见性，不证明没有控制台窗口。通过原生pythonw PE子系统和运行中的GetConsoleWindow独立核对。系统终止结果也需核真实Python PID，不能只看venv启动器或LastTaskResult。

## 固定范围与操作

只用一个新建随机精确名称 `AnatradingQualification-<32位hex>`，TaskPath固定根目录。名称、nonce、绝对pythonw/辅助脚本/计划/证据目录、当前交互用户SID、注册XML原文与哈希在执行前形成私有sealed manifest。查询确认此精确名字不存在，Register不用Force；不得批量改/停/删除任何其他任务。第二阶段仅替换自己已终态任务且先核名称、SID、动作与前一XML身份。发生身份不符立即停，不覆盖。此范围只批准临时资格任务，真实生产采集任务继续冻结。

登记使用本地Task Scheduler COM API，首次flags=TASK_CREATE(2)，第二阶段只TASK_UPDATE(4)；同名存在、权限不能确定或原任务失踪均停止。XML显式AllowHardTerminate=true、AllowStartOnDemand=false，登记后回读；不用手工Start请求。第二阶段若系统未终止实际PID，记强停资格失败，后续自己清理的停止不能算作系统自动终止成功。

动作固定 `.venv/Scripts/pythonw.exe -X utf8 <私有helper> --stage <blocked|reserve-hang> --manifest <绝对路径>`，固定项目工作目录。helper先原生记录实际运行exe、PID、GetProcessTimes的整数FILETIME和GetConsoleWindow，并把stdout/stderr导向内存／文件；不用账号密码。计划和原件均在git忽略artifacts中，helper只运行已审产品due入口，不打开数据库，不运行SDK或DLL交易接口。只允许调用系统本地Get-TimeZone身份检查。

两个阶段共用任务名，分别有限TimeTrigger（真实时钟触发，首次不调用Start-ScheduledTask），交互用户LeastPrivilege、IgnoreNew、StartWhenAvailable=true、Hidden=true、无失败重启、无重复触发、明确结束边界；不设SYSTEM、密码、开机触发或永久后台服务。注册前StartBoundary仍至少未来15秒；若筹备越界，只重新生成并核时间及XML哈希，不重跑同阶段已完成动作。

1. **blocked**：最多一次实际定时启动。使用U4真实current的有哈希副本，client/root身份字段不改，`_state_directory`仅映射私有clone目录；封住 `_http`、`_collect_locked`、`_client_identity` 和CLI EvidenceStore，任何意外调用计数并立即拒绝，不构造socket。调用实际CLI `acquire-tdx-due`并保存其结构化stdout和返回码。应refresh_unknown/client_task_unresolved、exit2、HTTP/采集/客户端探测/Store调用全0，current副本不变。状态副本和收据中的本机路径不授予真实客户端/根目录写入权。原始真实current/receipt、marker/dispatch存在性及哈希执行前后只读比较，未变化为必要验收。

辅助程序同时封_capture/_recover_locked，在blocked分支两者也应零调用；Python socket审计钩子补充拦截socket构造/连接。审核不能把Python钩子当成任意原生DLL的网络隔离，因此不执行SDK或未审 native helper，唯一允许原生动作是身份/console/time和Task Scheduler本身。
2. **reserve-hang**：仅首阶段已终态且精确动作可核后允许一次替换。采用另一私有空state，无真实current。封同样网络/来源入口，注入固定当前民用日18:00 UTC时点供资格，让产品due先持久reserved，再由 `_collect_locked` stub记录reserved-entered并阻塞。仅此自建helper可被停止。任务外层ExecutionTimeLimit固定PT10S，验证计划任务终止了实际Python PID（FILETIME相符）、保留可解析reserved，之后普通acquire对同私有state拒绝且0HTTP。该试验只授予缩短时间的系统终止行为资格，不能称已经证明生产PT3M或真实refresh/import在途终止。

blocked外层PT3M；helper应很快返回，根方单阶段观察上限120秒。reserve-hang外层PT10S，根方最多观察60秒。root每次wait≤30秒并核精确任务Info/State和原生进程；未观察到结束不能重启。当任务句柄有证据为Running且超过观察上限时，只停止此精确任务，再核实际PID；若实际子进程仍活，只在再次验证exe路径/FILETIME/自己nonce证据后停止此PID。任何条件不足不得泛杀python/通达信/工作台。停止均记录“外部客户端任务取消未证明”。

## 辅助校验与登记门禁

helper准备后独立反方阅读源码/manifest字段、核封网路径与目录边界；先离线测试不合法stage、manifest/nonce/hash、错误目录应在任何真实状态/网络操作前拒绝。只有闭合反方后根方注册第一次任务；已获授权范围内的时间字段更新无需再次询问用户。每次实际注册后导出实际XML核Principal/Actions/Settings/Start/End，核精确工作目录和动作身份；StartBoundary之前核失败即Disable本任务并注销，不发起其他来源动作。

终态证据包含LastRunTime/LastTaskResult/任务State、helper真实PID/FILETIME/exe/console、UTC及单调耗时、调用计数、完整计划槽分母和current/dispatch哈希。根方先禁用后注销自己精确任务并核Get-ScheduledTask该名字已无记录；若cleanup失败明确报告剩余任务且继续处理，不声称清除。保留日志，不递归删除产物。不修改生产LOCALAPPDATA控制、用户客户端或工作台；不添加行情POST、生产计划注册或自动重试。

两个阶段及独立结果审查完成后停止本资格切片。持续无手工更新仍需要真实行情定时成功、长期日历续期、工作台生命周期、积压恢复与分钟有效样本；完整目标保持active。
