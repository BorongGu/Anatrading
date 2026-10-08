# 当前客户端缓存离线导入：结果复审

2026-10-08。依据[018 设计反方](018-tdx-current-cache-import-review.md)，独立核读[根方验收](../qualification/tdx-current-cache-import.md)、私有原件／回执／审计／资源日志与两份执行脚本。未发送接口请求、执行导入或修改产品／原数据根。另以受监控的只读 Python 独立解码现有 Parquet；未打开 DuckDB。

## 判决

**接受本次缓存源值保存、固定窗口往返和幂等结果，无新增 P1。** 017 的来源混合风险在本轮执行中保持关闭：原缓存 uint32 数量及 binary32 精确值保留，HTTP 数值没有混入。完整软件兼容、量额单位和交易所真值继续未通过。

## 独立核验与证据范围

| 项目 | 核验结果 |
|---|---|
| 原件 | 指定缓存副本与新根 raw object 逐字节相同；270,848 字节，SHA-256 `715cee9f7203c560944c8ffa665321ace00805f6648d6892f81d8230baa66cca` |
| 回执身份 | 初次与复导均 committed，不同 attempt 指向相同批次、快照和原件；复导 `reused=true`；窗口沿用该快照 |
| 全行审计 | 静态核读独立 IEEE754 尾数／指数期待值算法及持锁、每 128 行对账控制流；原审计报告 8,464 槽、50,784 数值、全部 token／定位相等。复审未重新打开数据库，这一结论的执行证据来自该完整审计及日志 |
| 窗口原位对照 | 复审用独立 BigInt 精确算法核三条原位与 JSON 的 OHLC、量、额、定位及金额／保留字节；Volume 为 71534143、69097909、104535745，Amount 为 810575808、784632832、1205814912 |
| JSON／Parquet | 两份文件哈希吻合回执。独立 PyArrow 解码确认三行、完整查询 metadata、字段 schema、源值、checks、token 和定位与 JSON 一致；量为 int64，价／额为 decimal128(38,18) |
| 未知资格 | 原件身份、retrospective 模式与源序号 8462–8464 一致；`instrument_id`、`volume_shares`、`amount_cny` 为空；源语义全部 unknown，报价缩放 assumed；声明未晋级 |
| 关闭与改动 | 复审时新根目录没有 WAL；五份阶段 stderr 均为空。`git status --porcelain -- src tests web` 为空，无本轮产品修改。操作锁文件存在只证明文件存在，持锁行为依据已核执行代码 |

固定快照 `03316f3667be495dac0b64260fc796692100c444d3e6be94a20d859c02a9711f`；查询 `b3175c0f9cd18a5fe1386831b366419a5ed7189882225ca44afa8cf697eaa73e`。

## 条件质量与资源

复审对原件全部槽独立使用 BigInt 有理数重算候选量额边界：严格判据 105 fail、8,358 pass、1 not_evaluated；分阈值判据 81 fail、8,382 pass、1 not_evaluated，与原审计一致。两组失败不能相加。8,464 条标准单位检查仍为 not_evaluated；数值通过不赋予单位／覆盖资格。

逐份资源原日志核验五段 complete／exit 0、采样最大值及系统峰值与汇总一致；创建 FILETIME 从原 JSON 文本按整数字符串读取，与汇总字符串完全相符，没有经 JS Number 重编码。已核包装器使用 GetCurrentProcess 自监控实际 Python 进程，执行同一进程内的 CLI／审计，未把 venv 重定向器当业务进程。

本轮原任务峰值 WorkingSet 为 265,555,968 字节，PeakPagefileUsage 为 773,238,784 字节，各段均低于 2 GiB 观测停止值及 60 秒。复审只读 Parquet 进程另有自身监控，峰值 WorkingSet 99,164,160、PeakPagefileUsage 576,131,072 字节，约 0.52 秒；其结果不合并到原任务资源统计。自监控及采样不构成硬隔离、HTTP 延迟或全市场容量证明。

## 可信边界

根方审计脚本 SHA-256 `60cf7fb7d77f25790a28a296404cef86d40cd47734e434a60fdc627d844ba2f5`；资源包装器 `4e8ac235c09c28d1abfd82a600feeeeacbc21dfc8034cb0bb01a5bfcbf13b654`。全行与幂等的数据库事实采用既有锁协议下的原执行证据；本复审独立重算原件质量并复核导出，不声称重新执行了完整数据库审计。

本次结果支持现有源值证据内核处理这一缓存样本。仍不关闭手动导出、当前商业版本、单位、复权、历史可得性、分钟、全市场自动更新或指标验收；不放行 HTTP 精确量额接入、跨源合并或交易操作。
