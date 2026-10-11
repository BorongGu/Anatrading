# EvidenceStore 显式数据库只读模式：实现与独立验收

日期：2026-10-11。依据[冻结计划](../plans/2026-10-11-read-only-store.md)。实现基线为 `83f9a9a8a5e5fab5fdb3c29ccfd7de0b33e1085c`。本片不读取真实数据库或行情原件，不解释旧 first30hash 差异。

## 1. 范围与决定

独立代码审查、仓库外合成资格及最终产品回归通过，未发现阻断。Node首轮有工作目录命令错误，修正命令后完整150项通过；失败记录保留，详见第4节。提交与发布由主任务统一处理。

- `EvidenceStore(root, checkpoint=None, *, read_only=False)` 保留默认行为。显式只读只打开已有数据库，以 DuckDB `read_only=True` 连接，只用 SELECT 验证当前版本和六张主 schema 基表的必要读取列/类型。
- 接受额外表、额外列、不同列序和无原约束的同读取结构；不要求写入专用的 `attempts.interpretation_json`、`snapshots.manifest_json` 或当前读取结果未使用的 `observations.volume_shares/amount_cny`。版本必须为唯一一条当前 `schema` 值。
- 不初始化、迁移、恢复 running attempts、主动 CHECKPOINT 或执行 checkpoint 回调；连接错误不读写重试。构造失败关闭已取得连接并释放目录锁，重复 close 保持可用。
- `import_bytes`、`import_file`、共同 `_import`、导入恢复 `_resolve_attempt` 和 `backup` 早拒 `read_only_store`；backup 不进入关闭/复制/finally 读写重连。
- 仅 `snapshots`、`attempts`、`query`、`export`、`candle-geometry` 的子命令接受 `--read-only`。其他命令在参数解析时拒绝；HTTP、workbench、041界面不变。
- 只读模式的 JSON/Parquet 导出仍写指定或默认文件；在序列化/建目录/发布前，拒绝规范化并解析符号链接后的六保留路径及其子路径：数据库、`.wal`、`.wal.checkpoint`、`.wal.recovery`、`.restore-incomplete`、`.operation.lock`。正常内外部目标及默认导出可用，旧默认模式不扩大限制。

## 2. 先红后绿与合成覆盖

新入口实现前先加入4个用例，结果为4个预期失败：Store 不接受 `read_only`，CLI 不识别 `--read-only`。实现后相同4项全部通过。随后扩为109项产品内合成用例；包括既有相关测试的受影响回归为264通过、0失败、0跳过（20.44秒）。

新增覆盖：

- 不建缺失目录/数据库；目录占据数据库路径、空库、缺版本/旧版本/重复版本、缺表/列、错误类型、view替代基表、restore marker和连接失败。
- 额外表列、不同列序、删去写入专用/未用列仍可读；构造失败后重新取锁/读写打开，显式只读仍排斥其他只读和默认实例。
- spy只允许 SELECT，连接仅使用 `read_only=True`，初始化/回调/读写重连不可达；导入拒绝发生在输入读取前，backup不建目标、不关闭当前连接。
- 无 WAL、空 WAL，以及专用合成写进程提交并直接退出后保留的有效非空 WAL。提交的新数据版本可见，已有 running 状态原样返回；默认打开仍执行旧恢复。
- DB/WAL及两个引擎保留旁文件在打开前、中、close后和独立reader退出后比较存在性、SHA256、大小、mtime_ns；不以 atime 判变化。原件内容另行核对，锁文件允许创建并保持 POSIX inode。
- 六保留名 × 两种导出格式 × 本名/`..`/符号链接别名/子路径/别名子路径；默认 exports 目录符号链接、保留数据库本身指向外部的反向别名均阻断。普通目标和旧模式行为单独验证。
- 4组选择范围逐字段比较旧默认路径和新只读路径：完整/截止/空选集/超大序号，含 NULL、精确值、原始序号、计数、全部 query ID、查询目录/计数/导航和研究投影。JSON字节相同；Parquet schema、值和元数据相同。
- 原件缺失或篡改仍逐请求拒绝，空选集也不跳过核验；五个CLI读取命令等价，CLI缺库/空库/坏库/restore marker为无traceback的机器可读错误。

## 3. 独立审查

独立审查者未修改实现或测试，仅阅读最终 diff 并在仓库外运行6个独立合成用例，结果6通过、0失败、0跳过（1.14秒）。核验额外 schema 同名表不污染主 schema 检查、重排列/额外列、正常WAL和两种 running attempt、完整保留路径/别名/子路径矩阵、正常导出、导入/backup早拒，以及失败释放。

独立日志 SHA256：`4cbbaefb687bc9f679e9e216a1dcc798bff6e0d522d16dfa4abe63dfe82b16f8`。其结论为：Linux合成范围无阻断，可以冻结源码并执行统一回归。未经运行的场景保持未验。

审查源码 SHA256：

- `src/anatrading/store.py`：`841869b341f659e46f858fc08132b2e5f77b97d9377e09a8c5f22ea1ebffadc5`
- `src/anatrading/cli.py`：`c7dfdb9ba1d2762e53ee4b8e302dcd2b76cd4c3f936d3bddc5822cd08e749ce3`
- `tests/test_store_read_only.py`：`1c5e98acfc00c77e72c2d3ebd19d293863f44bafefc22d989b8d06e5f050a121`

## 4. 最终统一回归

环境：Linux、Python 3.14.0、DuckDB 1.5.6、PyArrow 25.0.1、Node 24.19.0、npm 11.9.0。复用既有锁定产品环境，没有安装依赖。临时目录与pytest basetemp均为仓库外新工作目录。

回归前冻结213个产品源码、测试、前端、资格脚本和依赖配置文件，规范化文件哈希清单 SHA256 为 `94bb82942cead23ed5d0d5a979cadc13c682b71a9e46fae31fa643261886aed3`。产品命令为 `python -m pytest tests -q -rs`；前端正确命令为 `cd web && node --test tests/*.test.mjs` 和 `cd web && npm run build`。统一运行后及Node命令修正后分别重新哈希，213文件与冻结前完全一致。

实际结果分列如下：

- **产品通过：** 3103 passed，0 failed，49 skipped，1 warning，116.86秒。相较既有2994通过/49跳过，新增109项全部通过。
- **跳过：** 49项为缺私有/真实样本和Windows原生当前进程证据；不升级为通过。没有为补齐样本联网或打开真实库。
- **前端通过：** 在README规定的 `web` 工作目录下，150 passed，0 failed，0 skipped，1.61秒。
- **构建通过：** TypeScript与Vite生产构建成功，54 modules；保留超过500 kB chunk的既有提示。没有改分包、依赖或构建阈值。
- **运行命令失败并纠正：** 首轮从仓库根目录执行 `node --test web/tests/*.test.mjs`，7个Vite SSR测试文件找不到 `/src/...`，仅100项通过，不能计为完整套件通过。定位为工作目录错误后仅重跑正确前端命令，未改源码，不重复Python/build。首轮失败日志SHA256：`9024f18bc66d7d9df6c4bfb98e458a69769dd0e930152c8f7566bae598cd13e9`。
- **警告：** 产品1条既有Starlette/httpx弃用提示；npm环境配置提示及Vite大块提示不改变退出成功状态，没有据提示安装新依赖。
- **未运行：** 既有无关qualification整套、浏览器/HTTP只读验收、真实来源、Windows原生和性能/预测验证。独立新增资格6项与产品109项已单列，不能替代这些未验范围。

最终产品日志SHA256为 `d83af5bdc54b25bc5bfe77e7aed21a5c75e293bee4ab468c5cfe49a30042e236`。源码清单JSON文件本身SHA256为 `b3f438dfc5593fec05462b85607ef203535a2f1f56d8a10845617a5e65fdf4e4`，回归前、回归后、Node纠正后均相同。`git diff --check`通过。

## 5. 明确边界

通过的证据限于上述Linux合成数据与实际执行的检查。`.operation.lock` 仍采用原有目录排他锁，可能创建，Windows空锁文件的旧分支可能补字节；不承诺整个目录零写或应用并发读。导出保护限于六保留路径，经静态resolve验证，不构成通用路径沙箱或对非协作进程符号链接竞态的防护。

Windows原生运行及原生符号链接权限/语义、跨OS网络共享互斥、损坏/截断WAL、中断checkpoint组合、真实来源兼容、性能及预测/交易增量均未由本片验证。既有Windows锁分支单元测试的模拟通过不升级为Windows原生通过。本片不改变旧计划或研究的来源资格，不启动HTTP只读服务，不公开部署。
