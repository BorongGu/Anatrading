# 039 · 原生恢复 R1 资格动作与结果反方

2026-10-08。独立反方 `/root/candle_contract_rebuttal`。承接[038代码复审](038-tdx-acquisition-recovery-implementation-review.md)，只读审查[动作合同](../contracts/TDX_RECOVERY_NATIVE_QUALIFICATION.md)及私有 `artifacts/qualification/tdx-recovery/20261008-r1/{native_qualification.py,audit_import.py,guarded_stage.py}`。本次只新增本记录，未执行helper、启动child、修改真实journal、调用行情/SDK/Store或操作用户客户端。

## 执行前审查

初始helper SHA `cf655b382d286a383df232d1376b6681efb68a8ad46c28c63f5b662254aa032c`，薄入口 `87437fc477753a69183bb4cb6fb911e96d71d4f530c6cfe55cfdf8e0acb84cd1`；资源guard SHA `5350dc54c1cd097676324897870f49e2dde6790be1dca55f86281adf058e04ad`，反方逐字节核实与G1守卫相同。仅AST解析检查语法，未runpy/import执行helper主体。

| ID | 级别 | 发现 | 最小修订与状态 |
|---|---|---|---|
| NQ-01 | P1 | child finally中stdin.close失败会跳过wait/stdout/进程句柄清理；stdout.close失败也跳过Popen handle.Close。 | 已关闭：ExitStack按handle.Close→stdout.close→wait(timeout10)→stdin.close注册，LIFO完成close/wait/stdout/handle，任一异常仍尝试余项并让资格失败。builder纯fake5分支通过，反方也独立AST仅抽finally对fake重跑5分支通过；未执行main/child/native。 |

初审的唯一P1 NQ-01已闭合，其余范围符合有限资格动作：

- 新建无网络Python child用-I/-S/-u、隐藏窗口、stdout ready、stdin一字节正常exit0；Popen句柄保留到ended核查结束。独立GetProcessTimes句柄tick与模块alive/ended同PID/tick相等；child结果限于封装本身。
- 固定0xFFFFFFFF只做一次missing查询，要求87加完整非空Toolhelp census/结束18；不循环选择新PID，不据此推断用户客户端终态。
- 真实入口前current/receipt固定原SHA/旧run/PID25140/精确tick/unknown绑定，state/client/root/run路径规范，marker/control/checkpoint/tmp缺席，锁已有且非空。原PID必须仍同tick alive，任何变化先失败，不调用recover。
- public recover的阻断分支期间，acquisition request/HTTP/identity/collect/publication/save/write、recovery publish/write、schedule active/save、EvidenceStore、socket/HTTPConnection、SDK import和os文件修改入口均失败计数门禁；Path/builtins写open仅私有资格目录及原有规范锁a+b，锁write额外拒绝，state.mkdir仅现有目录no-op。只允许取得/释放既有锁，不创建/扩展锁或记录成功恢复。
- 实际回执必须refresh_unknown/client_task_unresolved且全部forbidden计数0；当前/receipt/control/marker/lock/checkpoint/tmp存在/哈希及state/run目录项前后相等。结果仅安全状态、PID/tick、哈希/计数，不输出行情原文/账户/token。
- 复用guard在独立进程100ms名义采样WorkingSet/PrivateUsage和系统峰值，120秒/2GiB观测上限。ready读取由总guard覆盖，child.wait每次10秒；没有客户端等待或强停。同步native/文件调用不承诺可硬取消；超界os._exit关闭自建stdin管道使child正常EOF退出。允许私有观察产物写入，不能称该进程所有文件写入为零。

## 执行前最终区

**最终执行前反方结论：无未关闭P0/P1，允许根方记录决定后执行一次下列冻结R1动作。** 主helper仍未由反方执行。仅批准contract限定child正常结束/native封装与真实alive blocked分支，不批准SDK、行情、成功journal恢复、关闭通达信或正式任务登记。失败先核留存PID/tick现有实例，不因观察超时自动重启。

审批锚点：合同 SHA `67eeb14d3ae668cd1595422e567ac4f81da30445310c38be87d1d18f5d5845b1`；helper SHA `9a212b63c77eafb32844ff66d6bf818b6489d5a0321849317f4e1f9368e444ed`（141行），薄入口/guard保持上列原SHA。清理fake结果 SHA `6f9bbb17b715e1b3d6e23c135dc5bfd50e52b72a63a0763b61b44cecc083d869`，绑定该helper且记录正常及每个callback失败共5项。helper在ready读取前留child PID及原生创建tick；进程等待/清理范围不扩大。

## 执行后复核区

根方据[执行决定](../contracts/TDX_RECOVERY_NATIVE_DECISION.md)仅运行一次冻结主资格，报告退出0；本反方随后只读核源码断言、native-result/resources/final-observation及当前九路径，未再次执行helper或查询客户端。

| 项目 | 核验所得 |
|---|---|
| 自建child | PID35936，直接Popen句柄GetProcessTimes及模块alive/ended创建tick均 `134359314608153713`；stdin正常结束、wait返回0，再在持有句柄期间得到ended。main及资源观察器exit0证明实际正常清理路径完成；失败清理另由fake5分支证明 |
| 固定absent | 0xFFFFFFFF返回missing，error87、完整census290、complete=true；符合有界枚举策略，限该次系统列表 |
| 真实原实例 | PID25140仍alive，creation `134359031897815869`等原started7位tick；public recover返回refresh_unknown/client_task_unresolved、client_task_cancelled=not_proven，未生成成功恢复checkpoint |
| 禁止动作 | native-result记录28个明确门禁，全部0。已审源码禁止HTTP/SDK/Store/identity/collect/publication/journal/control和外部文件修改；既有lock仅取得/释放，state.mkdir为既有目录只读no-op |
| 生产文件 | 9路径before/after存在与哈希完全相同，state/run目录项不变。本反方当前再次只读核这9路径，全部仍等after；current/receipt仍SHA `5fa6af4427152614838483704e9562c4200cdbb08c32e21ad0c7f2d7de1fb343`，checkpoint/control/marker/tmp缺席，锁原bytes不变 |
| 资源 | helper PID35680、creation FILETIME `134359314603134963`、实际Python exe已记录；complete/exit0，1.036036秒，11次100ms名义样本，native峰550883328B，低于120秒/2GiB。观察性控制，无硬内核取消资格 |
| 后续终态 | root final-observation记录本helper和child之后均missing，error87/complete=true/census289；这是执行方后续只读核证汇总，本反方不重复native查询。child正常退出及helper实际退出0与该汇总一致 |

私有证据SHA-256：native-result `4ab10a716095316fda87b8c70591c3b75fe713cac5a5bd250718a1217be0a848`；audit-native-resources `13885355e3206422555d7b4f00a00c3d10948fb704e30ac2aa3e01db95236d4c`；final-observation `e457035562b6e7e3459ec91ebbb122ad5ba1db5dc95b995ca21807f6de760bce`。回执内容限安全字段/路径哈希，没有原行情、token或账户。

**执行后结论：R1有限原生封装和真实同实例alive阻断安全通过，未发现新P0/P1。** 自建alive→ended、固定PID完整missing与真实TdxW仍alive为三个不同证据；没有授予真实已结束会话后的生产恢复、分钟有效样本、持续自动下载或完整工具完成。私有资格/资源写入实际存在，零计数限定被审禁止入口及生产状态写入；不能称全进程绝对零文件IO或通用安全沙箱。
