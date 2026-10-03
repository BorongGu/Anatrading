# Anatrading

个人 A 股交易数据研究工具。优先**日线判断波段、分钟选择时机与复盘**，完整范围包括日内研究、中长期择时与组合。

当前处于**总体方案与架构反方评审阶段，业务编码冻结**。此前的小规模原型为未审核实验，不构成正式架构或完整产品。

- [总体方案](docs/MASTER_PLAN.md)：目标、功能全景、竞品对标、研究门禁、实施阶段、容量与验收。
- [架构设计](docs/ARCHITECTURE.md)：模块职责、数据/时间/精度契约、自动接入、版本与研究可复现性。
- [初轮功能研究](docs/research/001-data-and-price-volume.md)：量价、K线、数据精度及竞品资料。
- [软件接口调研](docs/research/002-data-access.md)：同花顺、通达信与替代免费数据路径。
- [量价与微观结构论文](docs/research/003-volume-microstructure.md)。
- [数据有效性与验证论文](docs/research/004-data-validity-and-evaluation.md)。
- [架构反驳与决策记录](docs/REVIEW_DECISIONS.md)。

用户已确定：Windows 本地优先；全市场日线 + 自选股票分钟；同花顺与通达信优先；真实软件数据验收；公开 GitHub 仓库。

拟采用 Python 数据/研究内核、TypeScript + React 界面。具体依赖、接口与数据能力以最终评审决策为准。个人行情、账户数据、密钥与受限样本不提交至仓库。
