# 042 · 工作台后台真实资格合同反方

2026-10-08，独立反方 `/root/candle_contract_rebuttal`。仅审[后台资格合同](../contracts/WORKBENCH_BACKGROUND_QUALIFICATION.md)、既有源码与[017研究](../research/017-workbench-lifecycle.md)；未改产品/测试、生成或执行helper/controller、启动服务/pythonw、注册/操作Task、加载SDK/行情或写生产journal。独立源码及sealed manifest第二次审仍必需；本记录不直接授权真实动作。

## 实质问题与最小修订

| ID | 级别 | 可复现路径与影响 | 窄修与状态 |
|---|---|---|---|
| BQ-01 | P1 | direct阶段Task启动失败或尚未运行时，同SID、同runtime/hash、同root的手工serve在TimeTrigger窗口占8791。唯一listener、HTTP/root、exe/hash/SID与创建窗口均可符合，仍不能证明其属于该Task；将它推定为owned会误发shutdown。原文要求“绑定动作/新进程/窗口”但未给机械归属判据。 | 合同v0.2已闭合：具体Task instance GUID/EnginePID原生tick锚，最多8层完整父链，每节点PID/tick/alive/path/hash、父不晚于子、固定launcher完整argv匹配与两次稳定观察；身份不明零POST。wrapped nonce不能替代链；冻结外来manual listener、engine复用/缺父/环/晚父/错误argv及链变化负例。实现效果待二审。 |
| BQ-02 | P1 | CREATE时StartBoundary尚未来30秒，登记或COM回读耗时越过触发时刻后返回不符，Task可能已启动。前段要求“触发前禁用/注销，并核无已启动worker”，与后文alive必须保留Task不注销的规则冲突；若先注销再核worker，会失去仍活实例的任务身份。 | 合同v0.2已闭合：回读失败核自己Task再disable，之后核活实例/归属；仅确证未启动或该层全部bound worker/launcher终态且无活实例才注销。越过触发时刻、alive/未知保留Task与身份，唯一owned停止仍须归属/旧token证明，未绑定者零POST。冻结跨StartBoundary回读失败的alive负例。 |

两项均是资格控制的归属/清理漏洞，不要求新增产品PID字段、通用daemon或强停。以上是合同修订闭合，尚无辅助代码或真实系统结果，不能称该资格已通过。

## 已审设计与源码事实

- 两个全新Task顺序CREATE，各一次TimeTrigger，不UPDATE换动作；wrapped终态、root重开、数据保持和清理通过才direct。实际监听worker与venv launcher分开；direct stdio/console明确not_observed，不转授wrapped自报。
- wrapped保留六个标准流原对象，产品导入前记录默认状态，再调用真实cli.main固定argv；不monkeypatch产品或捕获stdout伪造stopped。main返回0必须与固定源码/真实关闭/进程及锁证据合取。direct精确生产`pythonw -m anatrading.cli`，不经helper。
- 一次停止保留首次已核tokenA与原worker身份，POST前重核唯一listener/PID/tick/exe/SID；不重新GET新token，不调用产品stop-workbench误停同root的新会话。202仅请求意图，unknown不重投。禁止Task.Stop/强杀/删锁，alive/权限失败不当终态。
- 两层PT0S、无Repeat/Restart/Logon/手工Run、IgnoreNew、InteractiveToken/LeastPrivilege、AllowStartOnDemand及电池/idle/network开关；实际ITaskDefinition有效属性回读，不能将系统省略默认XML节点误判为值未配置。RegisterTaskDefinition明确CREATE2/userId sealedSID/passwordnull/logon3，现场SID回读；登记参数优先于定义Principal的事实已纳入合同。
- Store.export_json/export_parquet真实默认发布到root/exports；正常Store生命周期可能改变DuckDB/WAL物理文件。合同明确允许精确派生写，仅要求raw/既有exports及catalog/attempt逻辑保持，不作文件系统零写误报。baseline重开正常OS锁，禁止空root初始化与损坏恢复。
- window7066—7068与完整7068 export分开验收。source JSON/Parquet完整下载、Q/header SHA/正文SHA/locators/精确字段及baseline字节比对，最大16MiB/10秒、零重试；配置等小请求仍1MiB/5秒，实际worker PrivateUsage资格阈值2GiB。不得以metadata/首字节/局部行或launcher资源替代。
- minute refresh_unknown及current/receipt/marker不动；source/journal变化记录资格未通过。自然Logon、正式持久任务、长期运行、daily计划和slowreceive治理仍open。

## 补核官方事实与二次代码门槛

本轮独立阅读微软[RunningTask.EnginePID](https://learn.microsoft.com/en-us/windows/win32/taskschd/runningtask-enginepid)：它表示运行任务的engine PID，文档不保证为Python实际listener worker；不能只凭此字段发停止。另读[RegisterTaskDefinition](https://learn.microsoft.com/en-us/windows/win32/taskschd/taskfolder-registertaskdefinition)：TASK_CREATE=2，InteractiveToken=3且依赖已登录交互会话；userId参数优先定义中的凭证。此处为文档事实，尚无真实Windows调度结果。

二次独立审不得跳过：strict manifest精确字段/大小/路径及源码哈希；原生函数ABI、100ns整数、保留handle与CloseHandle所有故障路径；listener/Task/launcher/worker机械归属；注册时间余量、回读失败越界与alive清理；一次POST预算在尝试前消耗、unknown无retry；端口/URL/body/header与旧token固定；完整响应deadline/长度/原字节hash；stdout默认对象不变与main返回安全记录；PrivateUsage实际worker采样；logical catalog/attempt/raw及已有export清单前后比对。默认值回读与动作/SID不符均须先负例。

## 结论

独立全文读当前v0.2并实际核SHA256：`e57056eb985ff0535a5dfb588299b5ea659f55d135786ec36ab9a2df0237a609`。两项P1在方案合同层已修订闭合，未发现其它未闭合P0/P1；允许根方推进下一辅助实现合同、精确manifest schema与离线异常用例设计。当前“至少精确记录”的字段清单仍是草案，尚无exact schemaset/逐字段类型与组合规则；不直接解冻helper/controller代码或真实动作。

先冻结辅助实现合同的精确字段/取值/长度/类型/null与阶段组合、未知键拒绝、规范路径和动作/预算；复审及根方开工决定之后才写辅助代码。随后helper/controller/manifest与离线结果仍须第二次独立源码审和根方精确动作决定，含默认有效COM属性、真实原生链与所有故障清理。EnginePID是否确实位于本机Action父链、launcher存活/argv可读取等仍未取得真实证据；无法机械证明时按合同失败保留未知，不降级成时间窗口猜测或停止外来进程。最终真实结果另审，不由828本地测试替代。

慢receive、自然Logon、持久生产Task、direct内部stdio/console观察和长期自动更新仍未取得资格；source minute unknown不解除。根方决策前本轮未写辅助代码或执行任何系统动作。
