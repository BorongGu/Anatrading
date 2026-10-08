# 工作台后台资格方案决定

2026-10-08。根方采纳[资格方案v0.2](WORKBENCH_BACKGROUND_QUALIFICATION.md) SHA `e57056eb985ff0535a5dfb588299b5ea659f55d135786ec36ab9a2df0237a609` 与 [042独立反方](../reviews/042-workbench-background-contract-review.md) SHA `b52e2cb9b42fc4926a01312db70f2e2212d65d54e276ea653719066b07542f88`。两项P1在设计层闭合：实际Task归属需instance/原生父链而非时间窗口猜测；注册回读越界后alive/未知不得注销隐藏。

只解冻下一辅助实现合同、精确manifest schema与异常用例设计。当前schema“至少记录”的草案仍未构成逐字段严格合同；helper/controller源代码及实际动作继续冻结。需具体合同独立复审→根方决定→先负例后最小辅助代码→源码/manifest再次复审→封定动作后才执行。

最终实测拟两新nonce任务顺序CREATE、各一次TimeTrigger；wrapped保留默认标准流并调用真实main，direct精确生产命令且内部stdio/console未观察。旧token及原进程/任务血缘绑定、一次停止、真实终态/锁重开和完整源值导出共同验收。正常root导出派生允许精确写入，源对象和逻辑账本必须保持。

本决定没有启动服务、注册任务或解除来源未知状态。自然登录、长期连续更新、分钟样本、慢请求治理及完整分析目标继续保持未完成。
