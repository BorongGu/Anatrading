# Anatrading

个人 A 股交易数据研究工具。优先**日线判断波段、分钟选择时机与复盘**，完整范围包括日内研究、中长期择时与组合。

**总体方案、架构和首批数据合同已通过子 agent 反驳评审。** 当前实现 Windows 本地数据证据内核：保存原件、精确解码、冻结快照、按源标签查询、JSON/Parquet 导出、离线备份恢复。通达信公开历史文件和五份 BaoStock 响应已经过真实样本回归；当前客户端兼容、自动取数、图形界面和交易研究仍在后续验收范围内。

- [总体方案](docs/MASTER_PLAN.md)：目标、功能全景、竞品对标、研究门禁、实施阶段、容量与验收。
- [架构设计](docs/ARCHITECTURE.md)：模块职责、数据/时间/精度契约、自动接入、版本与研究可复现性。
- [初轮功能研究](docs/research/001-data-and-price-volume.md)：量价、K线、数据精度及竞品资料。
- [软件接口调研](docs/research/002-data-access.md)：同花顺、通达信与替代免费数据路径。
- [量价与微观结构论文](docs/research/003-volume-microstructure.md)。
- [数据有效性与验证论文](docs/research/004-data-validity-and-evaluation.md)。
- [架构反驳与决策记录](docs/REVIEW_DECISIONS.md)。
- [18项首轮验收任务](docs/ACCEPTANCE_MATRIX.md)：保留G0时冻结的基线；本轮有限通过状态见内核验收报告。
- [国内高级功能矩阵](docs/research/006-domestic-capabilities.md) / [国际高级功能矩阵](docs/research/007-international-capabilities.md)：各13个产品分组/产品，明确已读证据与待实测任务。
- [G1验证协议](docs/qualification/G1_PROTOCOL.md) / [BaoStock接口实测](docs/qualification/baostock-probe.md) / [通达信独立样本审计](docs/qualification/tdx-public-samples.md)。
- [BaoStock逐字段对账](docs/qualification/baostock-samples.md) / [数值表示观察](docs/qualification/numeric-observations.md)：源量化、系统精度和字段语义分开记录。
- [首批数据合同](docs/contracts/INITIAL_DATA_CONTRACT.md) / [实施决定](docs/contracts/IMPLEMENTATION_DECISIONS.md) / [内核验收报告](docs/qualification/evidence-core.md)。
- [当前客户端调查](docs/qualification/current-client-paths.md)：通达信安装包已下载并核验签名；尚未安装、登录或完成新导出对账。
- [只读小样本探测工具](qualification/README.md)：固定案例、超时和私有证据目录，不构成生产采集器。

用户已确定：Windows 本地优先；全市场日线 + 自选股票分钟；同花顺与通达信优先；真实软件数据验收；公开 GitHub 仓库。

已定架构：Python数据/研究内核、TypeScript + React界面、单一DuckDB存数据/目录/作业，原始证据按哈希保存；Parquet用于快照导出。一期采用本地模块化单体和离线备份。个人行情、账户数据、密钥与受限样本不提交至仓库。

## 本地运行

已测环境：Windows 64位、Python 3.14.0、DuckDB 1.5.6、PyArrow 25.0.1。当前命令行只开放源值历史查询；数据单位、证券身份和历史可得性保留各自证据等级。

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\anatrading.exe --help
```

下面的源文件路径应替换为自己的文件。`tdx-public-text-v1` 仅接受已审计的1m/5m标题、列与页脚形状，不接受任意CSV。当前可选格式还有 `tdx-public-day-v1` 和 `baostock-decoded-v0.9.4`；后者读取已经捕获的行情解码响应，不会自动请求网络。

```powershell
$imported = .\.venv\Scripts\anatrading.exe --root .\data\local import `
  'C:\行情导出\sample.txt' --format tdx-public-text-v1 | ConvertFrom-Json
$imported

.\.venv\Scripts\anatrading.exe --root .\data\local snapshots
.\.venv\Scripts\anatrading.exe --root .\data\local query $imported.snapshot_id `
  --cutoff '2021-02-26T09:35'
.\.venv\Scripts\anatrading.exe --root .\data\local export $imported.snapshot_id `
  --format parquet --cutoff '2021-02-26T09:35'
.\.venv\Scripts\anatrading.exe --root .\data\local attempts
```

日线截止值使用 `YYYY-MM-DD`；分钟使用 `YYYY-MM-DDTHH:MM`，均包含边界。无法解析日期的记录单列为 `unlocated`；重复标签全部保留。数值JSON使用字符串，原token和错误原因可查。声明单位或代码不会把未知规范字段自动填成已验证值。

导出默认放在数据目录下 `exports/`。备份必须使用数据根以外的新目录，恢复也仅接受新空目录：

```powershell
.\.venv\Scripts\anatrading.exe --root .\data\local backup .\artifacts\backup-01
.\.venv\Scripts\anatrading.exe restore .\artifacts\backup-01 .\data\restored-01
.\.venv\Scripts\anatrading.exe --root .\data\restored-01 snapshots
```

导入退出码：成功提交为0，拒绝/失败为2，接受取消为130。Ctrl+C在提交临界段前可取消；进入临界段后返回实际提交结果。故障恢复目录中的 `.restore-incomplete` 表示验证未完成，工具会阻止打开；保留该目录用于排查并改用新空目录恢复。

## 验证与后续范围

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests -q
```

公开测试含合成异常输入；真实样本原件保持私有，缺少原件时相应回归会明确跳过。不能用干净克隆中的跳过结果替代本机真实样本验收，细项和当前计数见[内核验收报告](docs/qualification/evidence-core.md)。

旧原型已经校验存档，Python内核按新合同重写；`web/`仍冻结且未发布。首批内核不代表G1/G2整体完成。下一步仍包括当前同花顺/通达信实际导出、受测接口自动更新、主数据与交易语义、日线/分钟联动界面，再按研究合同推进指标和策略评价。
