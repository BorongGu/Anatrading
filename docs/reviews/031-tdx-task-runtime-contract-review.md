# U5 临时任务运行合同反方审查

2026-10-08；初审 v0.1、复审[合同 v0.2](../contracts/TDX_TASK_RUNTIME_QUALIFICATION.md)、当前 `tdx_schedule.due/task_xml` 与 `tdx_acquisition.acquire`。仅静态阅读和官方文档查询；没有注册任务、访问行情接口或执行 SDK。

## 结论

范围与证据界限合理：私有 helper action 的一次 TimeTrigger 可以检验系统触发和真实 unknown 的副本阻断；另一次 PT10S 试验可以检验缩短上限的系统停止及 reserved 保留。两项结果均不能证明生产 CLI action、PT3M、真实行情定时成功或在途 refresh/import 取消。v0.2 已闭合下列两项 P1；合同定案可推进私有辅助程序，仍需独立审完 helper/manifest 后才能登记。

## 必须修订

1. **P1：硬终止和触发来源必须写入 XML 并回读。** 两阶段显式 `AllowHardTerminate=true`、`AllowStartOnDemand=false`。仅写 ExecutionTimeLimit 未固定硬停止行为，禁止手动 Start 的操作约定也未固定实际任务定义。[微软定义](https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-allowhardterminate)说明 AllowHardTerminate 控制任务服务能否使用 TerminateProcess；[设置参数](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtasksettingsset)说明 DisallowDemandStart 禁止按需启动。观察结果仍需真实 PID/FILETIME，不能仅从定义推论退出。
2. **P1：登记和更新需消除先检查后覆盖的窗口。** 首次只允许 create-only；精确名称不存在的判断必须区分 not-found 与查询失败，后者拒绝。二阶段只能 update 自己的任务：更新前导出原 XML，并逐项核 nonce、SID、Action、目录和原哈希；不允许 create-or-update/Force。清理前也复核上述身份，避免误停或误删同名替换任务。

复审：v0.2 明确 TASK_CREATE(2)、TASK_UPDATE(4)，同名存在/权限未知/原任务失踪拒绝，且保留前一 XML 身份检查；硬终止、禁止按需启动、系统未杀实际 PID 的失败结论均已补入。两项合同缺口关闭。登记实现仍需证明这些约束实际执行，包含清理时的同名替换防护。

## 实现审查的验收点

- helper 在读取生产 current/receipt 之外，所有写入必须位于 manifest 指定的私有目录；计划内原 root/client 字段不得成为写入授权。生产控制及原 receipt 的前后存在性和 SHA 必须相同，blocked 副本 current SHA 也必须相同。
- `_http`、`_collect_locked`、`_client_identity`、CLI EvidenceStore 全部封闭；补封 `_capture`、`_recover_locked`，误走路径计数后拒绝。可增加 socket audit hook 作为附加防线；不能以 hook 替代调用路径检查。
- manifest 必须在任何 source/state 操作前验证 stage、nonce、绝对路径/目录包含关系、helper/产品/计划/源副本哈希。两阶段使用不同 state 目录，reserved 测试不能移除真实 unknown 或其副本。
- `.venv/Scripts/pythonw.exe` action 可能是启动器；记录并由观察端复核实际运行 exe 的绝对路径、文件哈希、PID、原生 GetProcessTimes FILETIME。console=0 和 PE subsystem 检查独立保存，任务 Hidden 不能替代无控制台证据。
- 实际 TimeTrigger 启动需未来边界、注册/导出时间、LastRunTime、helper nonce 开始日志交叉对应；不能用按需启动补救第一阶段的失败。阶段一终态后才可更新阶段二。
- PT10S 若超过上限仍存活，记录系统停止验收失败；之后定向清理的人工 Stop/Terminate 不得写成系统自动停止成功。若 task State 和 actual PID 矛盾，持续核同一实例；停止只允许核实路径、FILETIME、nonce 的本次进程。
- 阶段二正常 `acquire` 阻断必须通过产品入口，调用计数全零，reserved 的 dispatch/marker 可解析且关联原 owner/run/slot，不从仅有文件存在推论调度有效。
- 注销后精确任务 not-found 和实际 PID 终态均需保存；无法证明清理时必须报告剩余任务/进程，不修改其他任务或生产控制。

## 授权边界

允许根方落实合同修订及编写私有辅助程序，供再次静态复审。当前没有登记解冻；产品代码、生产任务、真实行情请求均保持原合同限制。
