# Anatrading

个人 A 股交易数据研究工具。优先**日线判断波段、分钟选择时机与复盘**，完整范围包括日内研究、中长期择时与组合。

**总体方案与架构v1.0已通过三方反驳、修订及最终复审。** 本轮尚未恢复业务编码；此前的小规模原型保留为未审核实验，未并入公开仓库。下一阶段是G1真实数据与接口资格验证，正式产品和策略有效性均尚未完成。

- [总体方案](docs/MASTER_PLAN.md)：目标、功能全景、竞品对标、研究门禁、实施阶段、容量与验收。
- [架构设计](docs/ARCHITECTURE.md)：模块职责、数据/时间/精度契约、自动接入、版本与研究可复现性。
- [初轮功能研究](docs/research/001-data-and-price-volume.md)：量价、K线、数据精度及竞品资料。
- [软件接口调研](docs/research/002-data-access.md)：同花顺、通达信与替代免费数据路径。
- [量价与微观结构论文](docs/research/003-volume-microstructure.md)。
- [数据有效性与验证论文](docs/research/004-data-validity-and-evaluation.md)。
- [架构反驳与决策记录](docs/REVIEW_DECISIONS.md)。
- [18项首轮验收任务](docs/ACCEPTANCE_MATRIX.md)：真实接口、数值、回放、恢复与研究分开验收。

用户已确定：Windows 本地优先；全市场日线 + 自选股票分钟；同花顺与通达信优先；真实软件数据验收；公开 GitHub 仓库。

已定架构：Python数据/研究内核、TypeScript + React界面、单一DuckDB存规范数据/目录/作业、原始证据按哈希保存；Parquet用于快照导出。一期采用本地模块化单体和离线备份。具体SDK版本、数值字段和接口能力仍按G1证据冻结。个人行情、账户数据、密钥与受限样本不提交至仓库。
