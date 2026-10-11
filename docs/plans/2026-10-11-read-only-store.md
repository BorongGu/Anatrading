# EvidenceStore 显式数据库只读模式

日期：2026-10-11。状态：编码前独立审查通过（15:22 UTC）后获主任务放行；现已实现并通过独立代码/合成审查，最终产品3103通过/49跳过、前端150通过及build通过，见[实现验收](../reviews/2026-10-11-read-only-store-review.md)。

1. **问题与最小范围。** `store.py` 的普通构造会 mkdir、取锁、读写连接、执行 `_initialize` 的 DDL/INSERT，以及恢复 attempts 的 UPDATE；`cli.py` 的业务读取也经过该构造。因此普通读取可能改变数据库物理文件，此证据不能解释或归因旧 first30hash 变化。仅增加 `EvidenceStore(root, checkpoint=None, *, read_only=False)` 和 CLI 读取开关，默认及现有调用行为不变；不改 041 算法、HTTP、workbench、schema 版本和依赖，不建设快照/备份平台。

2. **打开与拒绝。** 只读不建根目录/数据库；已有目录仍先取得原 `_DirectoryLock`，锁内检查库文件和 `.restore-incomplete`，再用 `duckdb.connect(..., read_only=True)` 打开。缺目录/库报 `database_missing`；恢复标记沿用 `restore_incomplete`。允许引擎只读加载已提交 WAL，不因 WAL 非空拒绝；连接错误沿用 `database_error`，不修复或读写重试。只用 SELECT 检查当前 schema 版本、六张必要表的读取所需列/类型；缺版本、版本不符、必要表列缺失/类型不符报 `unsupported_schema`。不初始化、迁移或恢复 attempts；容许额外表/列，不要求 DDL、索引、约束、列顺序完全一致，不扫全库/全部原件。失败释放连接与目录锁。

3. **只读边界。** 连接、查询和关闭不改数据库/WAL；保留目录排他锁、实例 mutex 及 POSIX 锁文件不删除规则。`.operation.lock` 仍以现有方式打开，可能新建，Windows 空锁文件可能补字节；不承诺完全只读目录、并发读实例或跨 OS 网络共享。`import_bytes`、`import_file` 与共同导入入口、`backup` 在文件读取、建目录、写 SQL、关闭连接或进入恢复逻辑之前报 `read_only_store`，确保 backup 的 finally 默认读写重连及 `_resolve_attempt` 重连不可达。不执行 SQL CHECKPOINT 或 `_checkpoint` 注入回调；不因传入既有 checkpoint 参数而拒绝读取。

4. **命令与结果。** 仅 `snapshots`、`attempts`、`query`、`export`、`candle-geometry` 接受子命令级 `--read-only` 并传给 Store；其他命令不接受，不让无效组合先打开库。既有读取、逐请求原件验证、NULL、计数、原序号、精确值、身份和结果格式不变；`attempts()` 原样返回落盘 `running` 等状态。export 仍写默认 `exports/...` 或指定目标，帮助文本说明副作用；**仅新只读模式**在建目录/发布前拒绝目标等于或位于六个保留文件路径之下：`research.duckdb` 及其 `.wal`、`.wal.checkpoint`、`.wal.recovery`，另加 `.restore-incomplete`、`.operation.lock`；双方经 `resolve(strict=False)` 规范化/解析符号链接，报 `export_destination_reserved`。这防止导出创建数据库旁文件或把保留文件位置建成目录，保护后续打开及锁 inode；普通目标内容/ID/发布规则与旧默认不改，不做通用路径沙箱。

5. **合成验收。** 仅在新临时目录生成合成库，结束写进程后取基线。先覆盖缺目录/库、空库/旧 schema/缺表列/错误必要类型、恢复标记、连接失败；另验额外表列、无/空/有效非空 WAL 可读与已提交数据可见。核对锁互斥、失败释放、POSIX inode 保留和 Windows 既有锁分支。spy 确认无 DDL/DML/读写回退；导入/backup 早拒无输入读取/目标创建/回调/重连；running attempt（有/无 snapshot）不变。JSON/Parquet 均验六个保留本名、`..`、符号链接别名、尚不存在保留路径的子路径早拒，正常内外部目标允许。打开、重复读取、拒绝、关闭前后比较 DB/WAL 的 SHA256、长度、mtime_ns、存在性及原件内容；不验 atime，单列锁/导出变化。与旧路径比较全部读取结果/ID、NULL、原序号、cutoff、空选集、原件缺失/篡改、JSON 字节和 Parquet schema/值/元数据；验证 CLI、旧默认恢复并跑受影响回归。Windows 原生未跑须保留未验证。

6. **审查证据与停止条件。** 独立审查纠正了“非空 WAL 一律拒绝”的初稿限制：Linux / Python 3.14.0 / DuckDB 1.5.6 合成实验中，271 字节已提交 WAL 的新增/更新数据可读，DB/WAL 在打开前、中、关闭后及 reader 退出后哈希、大小、mtime 均不变，无恢复文件。初始脚本误判 access_mode 大小写而失败；保留报告的独立核验 13 项通过，未重开库（report SHA256：`edcc5fd0c09d0bce64670f8b70401a131f4a86afdcb56bde3e0e33a3986630ff`）。该编码前实验未验证损坏/截断 WAL、中断 checkpoint、Windows 原生及产品实现；产品实现的后续验收见本文顶部链接，其他未验边界不变。若后续发现 DB/WAL 变化或语义差异，先查明报告，不自动复制/修复。编码前阶段仅写计划，不触真实库、041 运行输入/文件、安全权限/网络；已在终核通过并获放行后实施。

依据：[Python DB API](https://duckdb.org/docs/current/clients/python/dbapi#read_only-connections)、[并发说明](https://duckdb.org/docs/current/connect/concurrency)、[1.5.6 保留文件名源码](https://raw.githubusercontent.com/duckdb/duckdb/v1.5.6/src/storage/storage_manager.cpp)；沿用锁定 `duckdb==1.5.6`，引擎支持多读不扩为应用并发承诺。
