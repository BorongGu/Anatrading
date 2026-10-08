# U5 临时任务运行结果独立反方

2026-10-08；依据[运行合同](../contracts/TDX_TASK_RUNTIME_QUALIFICATION.md)、[实现复审](032-tdx-task-runtime-helper-review.md)。读取私有 `artifacts/qualification/tdx-task-runtime/20261008-u5` 实际日志、XML、manifest；只读原生 COM/进程/源状态复核及封闭来源入口的私有跨 root 门禁复测。没有行情请求、SDK执行、任务创建/修改/停止。

## 结论

真实 TimeTrigger 启动、实际无控制台 pythonw 身份、原 unknown 阻断、reserved 持久保留、跨 root 拒绝和精确任务清理通过。实际子进程在后续观测时已终态；PT10S 精确终止时刻及终止原因没有直接证据，不能称已证明10秒硬上限或生产 PT3M 强停。真实行情定时成功、在途 refresh/import 取消、长期无人值守仍未资格。

## 已核证据

- **blocked**：实际 LastRunTime UTC09:37:58；helper native PID38760/FILETIME134359258782248609、runtime pythonw SHA `d278b258a6d565aa014a4cab0731134facdec77e9b25d97d0c235922353464b3`、SID和console0绑定。结构化 CLI exit2、refresh_unknown/client_task_unresolved；http/collect/identity/capture/recover/store/socket 全0。分母7 civil/5 trading/2 closed，没有成功槽。独立当前 COM State3/LastResult2，实际 XML 与 saved XML 完全相同，实际 PID 明确 NoProcessFound；详见032。
- **reserve-hang**：实际 LastRunTime UTC09:41:10；native PID29664/FILETIME134359260705404364、同 runtime/SID/console0。`reserved-entered` 与当前持久 control 完全相同，active owner 与实际 identity 相同，run/dispatch/plan/slot/root/port均可由产品 `_read_control` 校验。source transport 和 Store 调用计数全0；允许的 collect stub 已进入无限等待，不能把计数0解释为 stub 没有运行。
- **观测终态**：UTC09:41:55.1240397 的任务观测 State3/LastResult267014、actual PID missing。此时早于 UTC09:42:58.2929180 cleanup；根方未调用 Stop/StopProcess，cleanup-child-stop文件不存在。没有记录精确退出时刻，TaskScheduler Operational日志未启用，因此只支持“后观测已终态”，无法将约44秒观察间隔压缩为实测10秒。
- **门禁**：独立重读 current hang control，并在 `_http/_capture/_client_identity/_collect_locked/_recover_locked` 强拒绝 stub 下调用实际普通 `acquire`，跨 root 返回 schedule_dispatch_unresolved，calls[]、目标 root 未创建、dispatch SHA 前后相同。此复测只操作私有锁，不改变生产控制。
- **源与清理**：独立精确 GetTask返回明确 not-found、PID29664返回明确 NoProcessFound；生产 current/receipt 和 blocked clone SHA 均 `5fa6af4427152614838483704e9562c4200cdbb08c32e21ad0c7f2d7de1fb343`，生产 marker/dispatch 均缺席。hang dispatch SHA `da5bfae721e513f67b2fc4ed1360ac2aefff7a33012988b227a263f6c4ffb01c` 与 post-termination-gate 相同；保留未知，不清掉 reserved。

267014=0x00041306 是[微软 SCHED_S_TASK_TERMINATED](https://learn.microsoft.com/windows/win32/taskschd/task-scheduler-error-and-success-constants)；该状态码本身不能确定是时间上限、手工或其他终止源。PT10S/HardTerminate定义、无限 helper 和无根方停止记录使时间上限终止成为合理推论，但因果资格不能由推论替代。

## 窄修与后续限制

无编码声明的私有 XML 已完成真实 COM 登记和 TimeTrigger 启动；此前 UTF8 声明经 BSTR 登记失败，最小去声明修复具备运行证据。允许根方按独立决策仅修改产品 `task_xml` 序列化为 `xml_declaration=False`，在既有测试核无声明及中文路径完整，并执行适当回归。保留旧 manifest/阶段 seal 的历史产品 SHA，新建 after-patch 映射记录新 SHA；不得重写已完成运行证据。

此切片不注册生产任务，不新增行情 POST，不恢复或清理真实分钟 unknown。未来需专门资格验证成功行情派发、实际总时限、长期日历与工作台生命周期；完整目标持续保留。

## 产品窄修独立复审

已读[编码决定](../contracts/TDX_TASK_XML_ENCODING_DECISION.md)及实际 git diff：产品仅 `xml_declaration=True→False` 一行；既有测试仅将路径改为含中文/`&`，增加无 XML 声明断言，原 Command/WorkingDirectory 解码后精确路径断言保留。未改采集、调度、权限、时限、Store、数据合同或来源单位。根方报告先红后绿、定时/budget59项通过；此处未重复全套测试。

独立当前产品 SHA `2e81fe12f40e04151a0749267c277508409f4b82252e44b5837dbefe1e1ec9b8`，旧 manifest SHA 仍 `e39d926005e3f67748cb34827e6f56aa226891b955d25c81480ab220457daa86`。`product-encoding-patch.json` 单独记录映射，没有把旧阶段输入改成新产品。

独立只读 COM NewTask(0).XmlText 解析当前生产模板（SHA `5e7db0fa606107d062638f3c482f09b4ad96a9ea938beaf36621ce4015ded940`）成功，RunLevel0/Trigger1/PT3M；给同文本恢复旧 UTF8 声明后得到 `(1,40) unable to switch the encoding`。0 RegisterTask，未创建生产任务。窄修通过，授予 COM Unicode 文本解析兼容；生产动作运行、精确期限和真实行情资格保持未通过。
