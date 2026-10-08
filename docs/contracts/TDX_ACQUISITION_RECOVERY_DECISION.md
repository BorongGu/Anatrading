# 客户端未知刷新恢复开工决定

2026-10-08。根方采纳[研究016](../research/016-client-session-recovery.md)、[方案v0.2](TDX_ACQUISITION_RECOVERY_PLAN.md) SHA `0fc1f65b618d9018a72da172bce450cba3b10884edcf6f60b2eb2d849c28c47e`、[实现合同](TDX_ACQUISITION_RECOVERY_IMPLEMENTATION.md) SHA `b659a7ad5ba81fb622f70fb15bf355c041bf3fb158a47a3f61af8542de4b4c63` 与[037最终反方](../reviews/037-tdx-acquisition-recovery-contract-review.md)。036三项P1在合同层闭合；此决定覆盖U1身份变化直接采集、U4无active未知永不核终态的旧规则，保留active调度/发布核账门禁。

仅解冻tdx_recovery.py、tdx_session.py、对应新测试、tdx_acquisition/schedule/cli必要接入及原采集测试fixture/旧宽松用例的必要更新。不改行情方法、下载预算、格式、数据库或UI。先异常用例再实现；时间regex明确限制offset小时0—23/分钟0—59，测试不查询伪造PID对应的真实进程，state fixture按LOCALAPPDATA及client hash绑定。

当次恢复零HTTP且不消费新槽；机械old/new及不可覆盖checkpoint提供崩溃完成判据。实现、独立代码复核与真实资格分别验收；自建/合成终态不能证明当前TdxW已结束。当前真实原会话仍活，不授权清生产状态、强停客户端或追加行情。完整免手工更新与工具目标active。
