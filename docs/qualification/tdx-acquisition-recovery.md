# 客户端会话恢复：实现与资格

2026-10-08。依据[研究016](../research/016-client-session-recovery.md)、[修订方案](../contracts/TDX_ACQUISITION_RECOVERY_PLAN.md)、[037合同反方](../reviews/037-tdx-acquisition-recovery-contract-review.md)、[开工决定](../contracts/TDX_ACQUISITION_RECOVERY_DECISION.md)与[038代码反方](../reviews/038-tdx-acquisition-recovery-implementation-review.md)。本页区分程序恢复规则通过、真实未知阻断通过和生产恢复成功；后者尚未获得资格。

## 已实现路径

`recover-tdx --client-directory D:\tdx_64` 仅核证并封结旧的、未关联调度刷新，不下载或打开数据库。手工 acquire 和定时 due 在新run/调度控制初始化/新槽之前共用相同门禁。原客户端同PID及完整100ns创建时刻仍活时返回 refresh_unknown/client_task_unresolved；仅监听身份改变不够。

原进程已结束或PID已复用，且新唯一监听/path/AMD64/EXE与SDK指纹和原生创建时刻前后稳定后，才创建不可覆盖的恢复记录，保留旧current/receipt原字节与哈希。新failed只由原记录机械改变四个状态字段，保留来源诊断、单位/覆盖及“取消未证明”。恢复当轮零HTTP、不消费新槽；下一轮定时触发可按原计划正常采集。

保存中断通过原记录O/机械新记录N处理：有合法恢复记录时O/O、N/O、O/N仅补旧run；N/N为完成。缺记录的首次恢复必须O/O，不能接受已经改写的收据。完成后 recover 幂等，普通入口可继续；带恢复tag却丢记录仍拒绝。只查当前run，不扫描或删除历史证据。

原子replace的中止与重新进入为本切片故障模型；外部删除整个current且无全局anchor时不能与初次运行区分。路径包含保护通过代码检查，真实junction/symlink对抗未验。源文件没有新增格式或经济单位资格，分钟尚无有效样本。

## 自动检查与独立审查

新增140项恢复测试、66项原生封装测试。先异常用例，再实现；代码反方促成三项P1修复：无final却允许新收据、畸形Unicode路径漏typed错误、读写跨预算后仍继续阶段。各负例实红后转绿；FileIO短写也不得flush/fsync/replace，临时文件不充当完成证据。

最终完整Python回归 **680项通过，95.08秒**，只有既有Starlette/httpx弃用提示。此前focused331项/42.05秒为较早源码结果，不与最终680相加。反方独立运行原生66项及关键负例5项，来源/范围见038；其中实际进程核验仅针对当次测试Python自身，不能证明通达信已结束。

临时目录覆盖三入口、checkpoint rename/receipt-current写入flush/fsync/replace断点、四个O/N组合、inactive control原bytes、active/单边控制拒绝、completed下次正常派发、历史记录不阻断新run、严格JSON/大小/路径/身份字段及deadline。100ns/非法offset/PID范围/完整Toolhelp至18与句柄关闭分别验证。同步磁盘和原生查询不能硬取消，预算只阻止后续阶段，cleanup关闭既有句柄仍执行。没有UI改动，本轮不授予图形交互资格。

## 真实现场与受控原生实测

本轮只读现场2026-10-08T10:35:39.0705685Z：生产current/receipt均SHA `5fa6af4427152614838483704e9562c4200cdbb08c32e21ad0c7f2d7de1fb343`、run `20dc43a410af406aa6ba099ce2015f1c` 为原分钟refresh_unknown，marker/control均不存在。原PID25140仍以2026-10-08T03:19:49.7815869Z会话拥有127.0.0.1:17709。

随后 root 只读调用新 process_observation(25140)：state=alive、creation FILETIME `134359031897815869`，与上述7位原started经整数转换完全相等。此执行没有SDK/行情/Store或journal写入；只授予该观测时刻仍为原会话的证据，当前不能恢复。

按[R1动作合同](../contracts/TDX_RECOVERY_NATIVE_QUALIFICATION.md)、[039准入反方](../reviews/039-tdx-recovery-native-qualification-review.md)及[根方执行决定](../contracts/TDX_RECOVERY_NATIVE_DECISION.md)，一次guarded helper已执行成功。NQ-01清理P1先以纯fake五分支验证：任何一项close/wait失败仍尝试其余清理；此后才运行自建进程和真实blocked分支。

| R1实际证据 | 结果 |
|---|---|
| 自建无窗口子进程 | PID35936，原生creation `134359314608153713`；先alive，stdin正常结束/exit0后保留句柄可读同tick ended；全部自有句柄关闭 |
| 完整缺失枚举 | 固定DWORD 0xFFFFFFFF：OpenProcess87之后，完整Toolhelp至18、290项、PID缺席，missing；不是只凭87 |
| 真实原客户端 | PID25140、原tick `134359031897815869` 为alive；实际public recover返回refresh_unknown/client_task_unresolved，不封结旧run |
| 禁止入口 | HTTP/socket/SDK/Store/身份重新获取/产品及文件写入等28个拦截入口计数全部0。Python封锁与审过的调用图限定此次执行，不声称任意原生DLL网络硬隔离 |
| 生产保持 | current/receipt仍为上述5fa6...哈希；marker/control/recovery及三个临时文件继续不存在；已有非空operation.lock取放后哈希不变，state/run目录列表完全相同 |
| 资源 | 原生资格进程日志complete/exit0，1.036秒，11次100ms名义样本；原生内存计数峰值550,883,328字节，低于120秒/2GiB。阶段耗时不是行情或HTTP性能资格 |
| 清理后独立观察 | root再次原生检查资格PID与child PID均missing，完整非空枚举至18（289项）；没有再次运行helper、停止用户客户端或追加行情 |

私有文件仅 `artifacts/qualification/tdx-recovery/20261008-r1/`：helper SHA `9a212b63c77eafb32844ff66d6bf818b6489d5a0321849317f4e1f9368e444ed`，原样guard SHA `5350dc54c1cd097676324897870f49e2dde6790be1dca55f86281adf058e04ad`；native-result、resources、cleanup-audit与final-observation保存结果。原生资格和生产unknown拒绝通过；当前生产恢复成功仍未证明，已结束后成功补齐仅在临时测试中验证。结果独立复核见039，范围按该记录。

持续日常更新尚需实际已结束会话恢复、新日线采集、工作台正常启动/关闭、正式系统任务和长期计划；全市场、自选分钟与同花顺也各有来源验收。当前代码切片不代替这些完整用户目标，整体保持active。
