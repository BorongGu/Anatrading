# 日线免导出 U1/U2 实现合同 v0.3

2026-10-08，项目已由用户恢复 active。承接[自动取数方案 v0.2](UNATTENDED_ACQUISITION_PLAN.md)及[022 方案反方](../reviews/022-unattended-acquisition-plan-review.md)，本合同须经独立反方后才能解冻下列文件。整体全市场、分钟、研究与分析目标保留。

## 最简接入路线

增加一次性 CLI `acquire-tdx`：`--root <工作台数据根> acquire-tdx --client-directory D:\tdx_64 --symbol 600059.SH --target-date 2026-09-30 --port 8765`。无需用户下载或导出；保持已登录客户端与指定 root 的工作台运行。有限采集程序读取客户端缓存，经既有 `/api/import` 发布。采集程序不构造 EvidenceStore、不打开 DuckDB、不另起写者。工作台及当前界面无需新的采集服务或导入路由。

现有 config 缺目标根身份，新增不透明 `data_root_id`（Windows 已解析绝对根路径 casefold 后 UTF-8 SHA-256）；CLI 核与 `--root` 一致，保留该 config 会话 token 在内存，提交时按既有 Origin/token 边界。日志不保存 token。发布后再次核 config token/root；会话改变保持发布结果未知，不能换库重试。此身份防误投库，不承诺对抗伪造本机服务。

## 范围与预算

- 首批只接受显式单个 `600059.SH` 或已验 `000001.SZ`，仅 `1d`；目标日期显式 ISO 日，核合法且不晚于本机 Asia/Shanghai 日期。后续扩大清单另审；分钟白名单不变。
- 每次最多一次 TQ `refresh_kline` POST、一次工作台 import POST；禁止 get_market_data 浮点量路径、其他行情／交易方法、SDK导入及 GUI 控制。刷新只能限定证券／周期，不能限定日期或客户端后台总量。
- TQ 请求连接 2 秒、整个请求绝对 deadline 45 秒，工作台每次请求绝对 deadline 15 秒（连接最多2秒，后续逐次读取剩余时长）；HTTP正文最大 1 MiB、零 retry、无代理／重定向。工作台每次最多5个GET（首尾config、catalog、attempts、目标单行query）和一次import POST，核账不轮询。身份探测 subprocess 各 8 秒，隐藏窗口。阶段串行，超时停止，不承诺已取消客户端后台任务。
- 每份 `.day` 最大 1 MiB，长度非零且整除 32；客户端 exe 最大 32 MiB、SDK 最大 1 MiB；哈希流读。保存前后原件各一份，及有界请求/响应/收据。每次原件捕获两次读取，中间 250 ms，大小/mtime_ns/文件身份一致且 bytes 哈希一致；不轮询、不等待无限写盘。该证据证明稳定捕获，不能证明交易数据完整。
- 一次运行固定资源守卫另在实测启动器监测实际 Python 子进程，120 秒、2 GiB private usage；控制采集进程，禁止终止客户端／工作台。限制不约束客户端自身内部下载。两次真实执行验证新缓存与重导，合计最多两次 refresh；遇未知结果不得继续第二次。

## 顺序与终态

1. 校验参数；在 `%LOCALAPPDATA%/Anatrading/acquisition/<已解析客户端路径SHA>` 使用独立 Windows 文件锁和原子 `current.json`，同一客户端跨数据根共用，防止换 `--root` 绕过进行中／刷新未知，不占产品根锁。原件／响应仍在 `root/acquisition/<UUID>`；journal 固定该 root 身份、symbol、目标及证据目录。未终结发布恢复须匹配原 root，禁止换根。已有未终结运行阻止再次刷新；发布未知先核账本／目录同原件、格式、解释是否已有 committed 快照；仍未知停止。刷新未知须证明客户端会话已改变或另审人工核实，不能按时间经过重试。
2. 先核工作台 config/root/格式及上传预算，再核 TQ localhost 17709 监听拥有者、exe 已解析路径、PID/UTC启动时间。核 exe 与 SDK SHA 为既有已验指纹；读取 AMD64 PE machine。重解析路径及符号链接／reparse point 不得越出可信客户端目录。初始化失败不发刷新。
3. 定向路径 `vipdoc/sh/lday/sh600059.day` 或 `vipdoc/sz/lday/sz000001.day`。可捕获已有原件；不存在明确记 absent，读取不稳定／超限停。持久化刷新请求和“已发送／结果可能未知”标志后发一次关联 id 严格 JSON POST；拒绝重复键、非有限常数、错误 id、非字符串业务码、错误业务码与非200。保存响应及请求前后监听身份。无法核结果或身份改变保持未知，不追加请求。
4. 刷新后再次稳定捕获指定文件并核监听身份。全量复用现有 `tdx-public-day-v1` 解码；日期合法、严格递增无重复、数值都可精确表示；未知标准单位与条件金额检查不造成删行。目标日期须实际存在才能发布；目标缺失保留原件并记 not_covered，不补零、不改值。目标存在只表示该日期观察，不授予完整历史／当天闭合资格。
5. 区分 `new_content`、`unchanged_target_observed`、`not_covered`、`refresh_unknown`。无变化不能称本次下载取得新数据。将同一副本 bytes 送已有 import，解释仅 `instrument=<symbol>,venue=<SH/SZ>,asset_type=stock`，全为 assumed；量额单位未知，不写规范股数／元。
6. 发布前持久化 `publication_unknown`；只发一次 import。非200或断连不能笼统判入库失败。回执 committed 须校验 SHA/id形状，再读既有 catalog 与 attempts 核同原件、格式、解释、关联 snapshot、attempt终态；按原件及现有 manifest/版本规则计算预期批次／快照身份。用既有 query 限定目标日对应单个源序号，确认原件可读、查询身份与目标日期／原token／精确值一致（catalog单独不验证raw）。核 config 会话未变，才记 `committed`。无回执时可有限读账本核匹配提交，发现 matching committed 且query可读时单列 reconciled，不声称本次网络尝试已成功；无证据继续 publication_unknown。拥塞保留原件；无换库／CLI import fallback。
7. 已有未终结 publication 只核原journal的同原件／解释，不刷新不重复POST；恢复不以新CLI symbol/date/port覆盖原任务，port或root不符直接停。journal结构损坏／缺字段、原件缺失／哈希错、证据路径越界均停，禁止覆盖旧journal以重试。终结运行可开始新有限任务。磁盘写失败、Ctrl+C或进程中止留下已持久化阶段，下次以最保守未知状态处理。标准输出只含安全状态、原件hash、证据目录、日期观察、快照/尝试id；不回显原始服务器错误、账户、token。只有 committed（含可读核账reconciled）退出0；not_covered、未知、失败、拒绝退出2，Ctrl+C退出130。

## 解冻文件与验证

仅 `src/anatrading/tdx_acquisition.py`（新）、`cli.py`（新增命令且先于 Store 生命周期分支）、`workbench.py`（config根身份）、`tests/test_tdx_acquisition.py`（新）及必要 CLI/workbench既有测试、README使用说明；不改 schema、formats、numeric、Store、图表、指标或调度。

先写负例：非法股票/未来日期、身份指纹变化、客户端离线、重复JSON键/NaN/错误id/业务码、空/截断/变动文件、目标缺失、并发锁、错误数据根、刷新结果未知后重复触发、发布回执丢失前后、服务会话变化。故障注入只验证处理，不授予源资格。

真实验收：受控启动目标 root 工作台，执行古越龙山单日线自动获取；既有界面API可查已发布快照，独立按原件32字节记录核全部成交量与金额位表示以及三条目标窗口；首轮 committed 且目标query可读后才允许第二次真实执行，同源内容验证复用／新快照判断。旧快照不变，原件/请求/响应保留，关闭服务后数据库正常关闭。通过相应 Python 回归、CLI帮助/错误退出码；无UI代码变动不重复浏览器构建。实际结果与源单位、手动导出语义、预测效果分别报告。

定时调度 U4、全市场 U5 尚待后续合同，不能将此一次性自动获取称为无人值守已完成。
