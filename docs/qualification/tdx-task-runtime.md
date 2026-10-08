# Windows定时运行：实际系统资格

2026-10-08。按[U5合同](../contracts/TDX_TASK_RUNTIME_QUALIFICATION.md)、[决定](../contracts/TDX_TASK_RUNTIME_DECISION.md)、[031](../reviews/031-tdx-task-runtime-contract-review.md)、[032](../reviews/032-tdx-task-runtime-helper-review.md)、[033独立结果反方](../reviews/033-tdx-task-runtime-results-review.md)执行。上一轮U4源码HEAD `2c3e4fd`完整回归416项；本轮独立系统任务试验后，只修正产品XML编码单行。

## 实际证据

同一个随机精确临时任务、两个一次性TimeTrigger，InteractiveToken/LeastPrivilege、IgnoreNew、禁止手动启动、无失败重试，均由系统时钟触发。动作是资格helper，内部调用产品CLI/due；行情、SDK、客户端探测、Store和socket入口封住，真实客户端控制目录不作为写入目录。

| 阶段 | 实际结果 |
|---|---|
| blocked | 上海17:37:58触发；实际Pythonw PID38760／FILETIME134359258782248609；CLI refresh_unknown/client_task_unresolved，exit2；HTTP/collect/identity/capture/recover/Store/socket计数全0；原未知副本不变 |
| reserve-hang | 上海17:41:10触发；PID29664／FILETIME134359260705404364；产品先写reserved，私有stub阻塞；09:41:55.124Z核任务非Running、实际PID不存在、LastTaskResult267014；此前root未调用Stop/Stop-Process |
| 终止后门禁 | 私有reserved可严格解析；跨数据根acquire拒绝schedule_dispatch_unresolved、0HTTP、未创建新数据根、dispatch不变 |
| 清理 | 09:42:58.292Z禁用并删除精确任务；COM GetTask明确0x80070002；两个实际PID均终态，没有额外cleanup-child-stop |

两实际进程均为原生Python314/pythonw.exe，SHA `d278b258a6d565aa014a4cab0731134facdec77e9b25d97d0c235922353464b3`，实际用户SID吻合，GetConsoleWindow=0。venv启动器与实际解释器分开核验；这里只证明本helper启动没有控制台。

第二阶段配置PT10S，但TaskScheduler Operational日志未启用，没有精确终止时刻。微软[返回码说明](https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-error-and-success-constants)将267014/0x41306列为任务终止，单个返回码不证明因果。配置与无主动Stop观测支持系统上限停止的推论；本轮授予该配置下实际子进程后来终态、reserved仍可读并阻断新请求的资格，不授予精确10秒、生产PT3M或真实refresh/import在途取消资格。

生产current及对应receipt始终SHA `5fa6af4427152614838483704e9562c4200cdbb08c32e21ad0c7f2d7de1fb343`，仍为原分钟refresh_unknown；生产marker/dispatch始终不存在。未新增行情请求、运行SDK、修改客户端、启动工作台或重置全局未知状态。

## 现场缺口与产品修复

时间余量门禁在COM调用前拒绝过时XML；UTF-8声明的Unicode字符串在实际COM登记出现(1,40)“无法切换编码”。去掉声明后确实可登记。系统注册又会省略默认RunLevel/Enabled/AllowHardTerminate等节点，私有验证器过严拒绝后自动禁用/删除任务，没有实际启动。保存实际返回文本后，通过原生ITaskDefinition读取有效默认值，仍严格核动作/用户/单trigger/权限/超时。显式HardTerminate=false、HighestAvailable、Enabled=false继续拒绝。

依据[编码窄修决定](../contracts/TDX_TASK_XML_ENCODING_DECISION.md)，产品task_xml只去掉Unicode文本编码声明，测试增加无声明及中文路径。先复现后修复，定时/预算59项通过；独立Windows NewTask.XmlText只解析旧产品模板仍失败、新模板成功，0生产注册。此修订后未重跑或宣称整仓416项回归。

私有证据在 `artifacts/qualification/tdx-task-runtime/20261008-u5`：helper SHA `878b7bf64ac834cdba6261431a0f8989f79870c1299d296554bbbb68663a81e4`，原运行manifest `e39d926005e3f67748cb34827e6f56aa226891b955d25c81480ab220457daa86`，最终controller `d2648814c9e1be0c08905cccd0dadf33efd019e755caa96ba42b687726b5469a`。提交XML、系统返回XML、各阶段进程/结果、sealed哈希、终止后门禁及清理分别保存。运行前manifest原样保留；产品修复另存product-encoding-patch.json，没有重封历史输入。

系统返回XML是COM Unicode文本另存UTF-8，文本仍含UTF-16声明；这些文件记录API文本，不能根据声明称保存文件为UTF-16原始字节。helper离线异常18项、controller有效默认正例及3项拒绝通过，独立范围见对应评审。

本轮取得真实系统触发、未知保护、实际子进程终态与精确清理证据，并修复原生XML兼容。生产CLI动作、真实持续行情更新、长期日历续期/生命周期、全市场与自选分钟仍未验。完整工具目标active；临时任务已注销，生产定时任务未启用。
