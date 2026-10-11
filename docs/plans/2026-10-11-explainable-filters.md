# 有限条件筛选实施

依据：[032 合同](../research/032-explainable-stock-filters.md)及[独立批准](../reviews/2026-10-11-explainable-filters-review.md)。只实施纯函数与只读 API，不接 UI，不提交真实行情，不改同行研究。

1. 先锁定旧 universe/API 合成 golden，新增规则异常、精确阈值、独立三值参考和来源资格测试。
2. 从现有 universe 一次计算提取私有 exact/窗口辅助产物，旧公开输出与身份保持不变。
3. 新 stock_filters 模块实现固定两层规则、共享事实、所有原子 eager 评价、原因/守恒、来源摘要与身份。
4. 新只读路由在加载前校验规则/数量/行数预算；每来源一次紧凑加载/原件核验/归一化，复用旧本地 HTTP 边界。
5. focused 回归、独立实现反方、合成性能与授权离线真实矩阵分别验收；最终与并行工作协调源码冻结后全回归。

当前：最小纯函数与只读 API、独立对抗、联合全 Python 及冻结离线真实矩阵已通过；合成资源观察和最终状态见[实现验收](../qualification/stock-filters.md)。本后端计划未覆盖 UI，其进展见[独立界面资格](../qualification/research-filter-ui.md)；Windows、Pine 对照、用户任务价值及预测/交易效果仍未验。未经最终核实不把设计指标记为已达到；不 commit/push。
