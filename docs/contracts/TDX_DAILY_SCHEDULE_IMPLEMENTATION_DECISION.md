# U4 定时入口编码决定

2026-10-08。根方采纳[实现合同v0.2](TDX_DAILY_SCHEDULE_IMPLEMENTATION.md)及[029独立反方](../reviews/029-tdx-schedule-implementation-contract-review.md)。反方确认同客户端锁贯穿与单控制文件原子归槽，POST前民用时间重核、slots语义校验两项已修订关闭。

解冻 src/anatrading/tdx_schedule.py、tdx_acquisition.py必要内部采集/恢复提取与预算/全局门禁、cli.py新due入口、对应测试和说明。先写异常用例再实现，合成输入只授予边界资格。任务XML只生成与测试，不注册、不发真实行情、不清除现有分钟refresh_unknown。真实系统触发与长期免手工更新仍待后续资格，完整目标active。
