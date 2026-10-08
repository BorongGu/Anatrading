# 当前客户端缓存离线导入验收

2026-10-08。依据[离线验证合同](../contracts/TDX_CURRENT_CACHE_IMPORT.md)、[018 反方](../reviews/018-tdx-current-cache-import-review.md)及[执行决定](../contracts/TDX_CURRENT_CACHE_IMPORT_DECISION.md)，复用既有证据内核，无产品代码、格式白名单或 Schema 修改。

**本次源值保存和往返通过；当前客户端完整兼容、标准单位与行情真值仍未通过。** 输入为实际安装客户端的 `.day` 缓存副本，来源链与 HTTP 精度差异见[缓存诊断](tdx-cache-diagnostic.md)，不能称为用户手动导出。

## 输入、快照与私有目录

- 输入 SHA-256：`715cee9f7203c560944c8ffa665321ace00805f6648d6892f81d8230baa66cca`，270,848 字节。
- 使用既有 `tdx-public-day-v1`；声明证券 `000001.SZ`、市场 `SZ`、品类 `stock`，解释为 assumed。没有声明量额单位。
- 独立数据根：`artifacts/qualification/tdx-current-import/20261008T051530922Z/data/`；源副本、回执、审计、导出和资源原件均私有，不提交 Git。
- 批次：`e1f35121db44876bdc07a75a90cfc68e24d9dd30c5cf59676d4f4a813477b374`。
- 快照：`03316f3667be495dac0b64260fc796692100c444d3e6be94a20d859c02a9711f`。

## 实际通过项

| 验证 | 结果与边界 |
|---|---|
| 既有 CLI 导入 | committed；保存一个原件、一个批次和一个快照；未导入 HTTP 数据 |
| 全记录独立对账 | 8,464 条、50,784 个源数值全部一致；ordinal、字节定位、日期、原 token、金额位字节与保留字节全部对照；unlocated 为 0 |
| 数值方法 | 原量为 uint32 整数；金额预期由 IEEE754 位型的整数尾数／指数独立解码，没有复用产品金额解码器；与数据库 Decimal 精确相等 |
| 资格保留 | `instrument_id`、`volume_shares`、`amount_cny` 仍为空；源单位与时间语义全部 unknown，报价除 100 为 assumed；未启用规范化、VWAP 或量能指标 |
| 固定三条窗口 | 源序号 8462—8464；查询、JSON 完整对象、Parquet 行值／schema／metadata／checks／token 全部对账；未知资格保留 |
| 幂等复导 | 第二次 committed 且 `reused=true`；两个不同 attempt 指向同一批次和快照；仍仅 8,464 行和一个 raw object |
| 关闭和原件 | 各段串行通过同一 EvidenceStore 操作锁；每段正常关闭；最终无 WAL；源副本完整哈希未变；没有打开旧性能副本或个人数据根 |

三条窗口 Q：`b3175c0f9cd18a5fe1386831b366419a5ed7189882225ca44afa8cf697eaa73e`。JSON SHA-256 `ee12e5dd300f7bdb8ebdbfc80ad79672f470bdf59bff35f4da16551287fdbd9c`；Parquet SHA-256 `7d59e22b71d17d93fb8dca7442b2ffc6829ebece840e1fbd6a51e3f1a812ed8d`。两种导出只覆盖这个窗口，不把其范围外推为完整导出或性能结果。

## 保留的质量问题

数值解码、日期、重复／逆序、OHLC 包含关系、非负量额及零量非零额的现有检查均通过。标准单位检查 8,464 条均为 not_evaluated。

候选“股／元、同成交覆盖”口径下，严格量额边界为 105 fail、1 not_evaluated、8,358 pass；按分阈值的条件诊断为 81 fail、1 not_evaluated、8,382 pass。二者使用不同判据，不能相加成异常记录总数。这些结果全部保留，没有删除异常或改金额；未知单位、复权和覆盖仍可能影响解释，条件 pass 不构成标准单位验收。

## 资源与证据边界

五个独立阶段均 complete；每段真实 Python 进程分别记录 PID、创建 FILETIME、可执行文件和 100 ms 样本。实际执行器为 Python314 的运行进程，未以 venv 重定向器代替。系统峰值 Private Commit 最大 773,238,784 字节，峰值 WorkingSet 最大 265,555,968 字节，均低于 2 GiB 观测停止值；各段观测时长约 0.57—2.46 秒。其范围是本次离线任务，不能作为 HTTP 500 ms、浏览器首交互或全市场容量的证明。

[Microsoft 内存计数定义](https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters_ex)支持相应系统峰值含义。自监视与采样不能证明硬隔离。精确创建 FILETIME 在资源汇总中用字符串保留，原资源日志中的完整整数不经 JavaScript 数值重编码。

全行审计与固定窗口、幂等审计分别运行。[019 结果反方](../reviews/019-tdx-current-cache-import-results-review.md)已接受本轮结果，无新增 P1：独立核原件、全部条件质量计数、三条 JSON／Parquet 及资源日志；全库 50,784 个值对账依据已核根方代码与日志，未重新打开数据库。真实手动导出、商业版本、标准单位、分钟和全市场自动更新仍待验收，完整目标继续保留。
