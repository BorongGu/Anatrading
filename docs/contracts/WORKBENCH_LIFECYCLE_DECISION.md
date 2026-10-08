# 工作台生命周期开工决定

2026-10-08。根方采纳[研究017](../research/017-workbench-lifecycle.md)、[方案](WORKBENCH_LIFECYCLE_PLAN.md) SHA `9f55e3f12d5d7b6f8e8aa001882c4275fec8bcf1172bd6914c19c197469be0b1`、[实现合同](WORKBENCH_LIFECYCLE_IMPLEMENTATION.md) SHA `4cf6b68d70676c93c375a5d75ce575fafe94e665a92bf7f12489647870806f31`、[040独立反方](../reviews/040-workbench-lifecycle-contract-review.md) SHA `1754584216b85f97ffc8940c2cb49886cc30c3669705fc7059dcafa89e598cbb`。两个P1已在合同层关闭，先写异常用例并确认失败，再实现。

仅解冻 workbench.py 的认证关闭与响应finally、cli.py 的薄serve/stop接入及退出码、新 workbench_lifecycle.py 的serve/stop/纯XML、tdx_acquisition.py 的_config兼容budget参数、新test_workbench_lifecycle.py/test_workbench_stop.py及必要CLI回归。保留现有单线程Store与OS锁，不新增服务、PID状态、重启机制、依赖、数据库、行情或UI。

正常结果须核真实生命周期完成标志；回执发送失败仍同步请求一次退出；停止POST未知不重试，两个预算/guard上下文必须恢复。未完成请求体可能无限延迟关闭，此可用性问题保留后续架构与完整系统验收，不能声称关闭闭环已完成。

此决定只授权本地测试与有限实现。真实pythonw启动、系统任务登记/触发及关闭另封精确资格；生产客户端原会话仍alive，当前minute refresh_unknown保持，零SDK/行情/委托操作。正式持续更新、全市场日线、自选分钟、长期日历和完整分析目标保持active。
