# 首批合同定案与原型处置

日期：2026-10-04。主方核读 [005最终复审](../reviews/005-initial-data-contract-review.md)，登记 [首批合同](INITIAL_DATA_CONTRACT.md) 通过本批开工门槛。P0与文档开工阻断均为0；产品测试尚未执行，不将此状态提升为G1/G2整体通过。

- 合同 SHA-256：`8dcd1cdde0260b8304a076dec32f99011c4ef04df477e9e57250c938a8f1628c`。
- 005最终复审 SHA-256：`80a87bac5172eb90a9f0c6aa35579a7679f57c40a2af5bb1ddbdd3af8b149901`。
- 数值独立实验：DuckDB 1.5.6 / PyArrow 25.0.1，38,763行四段往返无损；产品入口仍须精确前检及自身测试。

## 存档与解除范围

12个原型文件均已按 `artifacts/prototype-freeze.json` 逐个复制至私有 `artifacts/prototype-v0/`，原件及存档SHA-256均相等，清单为该目录的 `manifest.json`。存档及原行情不进入公开仓库。

从此记录起，允许重写原 `src/anatrading/{__init__,ingest,analysis,store,api,cli}.py`、`tests/{test_ingest,test_analysis,test_api}.py` 和 `pyproject.toml`，并按模块职责增添少量实现/测试文件。旧文件若不被采纳可从活动目录移除，存档必须保留。新内核不直接扩展旧JSON存储或导入即算指标的流程；暂不采纳旧analysis/API实现。旧26项测试属于存档实验，不混入新系统的通过统计。

`web/package.json` 与 `web/package-lock.json` 本轮继续冻结，图形工作台依相应后续实现和浏览器验收推进。该解除范围不包含交易信号、自动行情采集、PIT、跨源合并或完整研究引擎。

## 实施与验证责任

主方负责集成、单库提交/查询、CLI、实际故障和恢复验证及最终发布。子agent可在明确文件所有权下实现精确数值入口、格式解析和独立测试；主方核读并对照G1独立控制值。首次可运行链先闭合精确JSON，Parquet与备份逐项启用。未通过的路径明确未启用，完整目标保持未完成。

## 首批实现放行

依据 [006实现复审](../reviews/006-evidence-core-review.md) 和 [产品验收](../qualification/evidence-core.md)，当前有限实现通过218项测试，含真实源值的JSON/Parquet往返和离线备份恢复。放行 `0.1.0.dev1` 的固定格式导入、retrospective查询、精确导出、单批事务与恢复、命令行。Parquet与备份各自测试完成，可以在该合同范围使用。

对应实现只有 `src/anatrading/{__init__,models,numeric,formats,store,cli}.py`；未采纳旧analysis/API实现。格式合同内容版本为2（逐字段语义），存储Schema为1，规范化禁用版本为`disabled-1`。旧12文件存档以及冻结web两文件的哈希再次核验无差异。

总体方案、架构、首轮验收矩阵和首批合同正文仍保持批准指纹；本次完成状态写在新报告，不追改原始门槛。T09/T10的已测子能力与T11当前规模的验证见报告，完整T01–T18、G1/G2及原目标继续保留未完成项。
