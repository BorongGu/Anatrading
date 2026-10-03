# Anatrading

个人 A 股交易数据研究工具。优先**日线判断波段、分钟选择时机与复盘**，完整范围包括日内研究、中长期择时与组合。

**总体方案与架构v1.0已通过三方反驳、修订及最终复审，当前进行G1真实数据资格验证。** BaoStock 五组匿名小样本请求成功，通达信公开历史文件已做独立审计；本仓库提供有限的只读探测工具。此前业务原型仍冻结、未并入仓库。当前客户端兼容、完整数据语义、正式产品和策略有效性均尚未完成。

- [总体方案](docs/MASTER_PLAN.md)：目标、功能全景、竞品对标、研究门禁、实施阶段、容量与验收。
- [架构设计](docs/ARCHITECTURE.md)：模块职责、数据/时间/精度契约、自动接入、版本与研究可复现性。
- [初轮功能研究](docs/research/001-data-and-price-volume.md)：量价、K线、数据精度及竞品资料。
- [软件接口调研](docs/research/002-data-access.md)：同花顺、通达信与替代免费数据路径。
- [量价与微观结构论文](docs/research/003-volume-microstructure.md)。
- [数据有效性与验证论文](docs/research/004-data-validity-and-evaluation.md)。
- [架构反驳与决策记录](docs/REVIEW_DECISIONS.md)。
- [18项首轮验收任务](docs/ACCEPTANCE_MATRIX.md)：真实接口、数值、回放、恢复与研究分开验收。
- [国内高级功能矩阵](docs/research/006-domestic-capabilities.md) / [国际高级功能矩阵](docs/research/007-international-capabilities.md)：各13个产品分组/产品，明确已读证据与待实测任务。
- [G1验证协议](docs/qualification/G1_PROTOCOL.md) / [BaoStock接口实测](docs/qualification/baostock-probe.md) / [通达信独立样本审计](docs/qualification/tdx-public-samples.md)。
- [BaoStock逐字段对账](docs/qualification/baostock-samples.md) / [数值表示与合同候选](docs/qualification/numeric-observations.md)：源量化、系统精度和字段语义分开记录，具体G2合同尚未定案。
- [只读小样本探测工具](qualification/README.md)：固定案例、超时和私有证据目录，不构成生产采集器。

用户已确定：Windows 本地优先；全市场日线 + 自选股票分钟；同花顺与通达信优先；真实软件数据验收；公开 GitHub 仓库。

已定架构：Python数据/研究内核、TypeScript + React界面、单一DuckDB存规范数据/目录/作业、原始证据按哈希保存；Parquet用于快照导出。一期采用本地模块化单体和离线备份。具体SDK版本、数值字段和接口能力仍按G1证据冻结。个人行情、账户数据、密钥与受限样本不提交至仓库。
