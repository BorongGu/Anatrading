# 023：日线免导出实现合同反方

2026-10-08。独立核 [U1/U2 v0.1 合同](../contracts/TDX_DAILY_ACQUISITION_IMPLEMENTATION.md)、[011 研究卡](../research/011-unattended-source-capture.md)及既有 CLI、Store、工作台源码。未取数、未打开产品数据库、未编码。合同 SHA-256 `12d0444732e5e727e4dcce9a37be34197b14807f17593174f42e6007bf742a6f`；研究卡 SHA-256 `2632b9199006e30dc5757a1933bde5a8164823c08be867a4d5f9ca6447eab1ea`。

## 结论

**v0.3 合同通过：1 项 P1、2 项 P2 已关闭，解冻仅限合同所列 U1/U2 文件。** 一次性 CLI → 既有 HTTP import → 现有唯一写者的路线合适，无需新增服务、数据库或 GUI 自动操作。下列记录保留 v0.1 发现及修订依据；合同批准不构成实现或真实来源验收。

## 必须修改

1. **P1：刷新互斥与未知结果 journal 的作用域过窄。** 第 1 步仅锁 `root/acquisition`；两次命令选择不同数据根，即可并发请求同一个通达信客户端，或绕过另一根保存的 `refresh_unknown`。这违反合同“未知客户端任务停止追加”的约束。将唯一采集锁与未终结运行 journal 绑定解析后的客户端安装目录，在用户私有状态目录保存；同客户端不同 root 也共用。记录内固定 `data_root_id`、证券、周期、目标日期和客户端会话；恢复只准使用原 root，异 root 请求在任何 POST 前停止。复用 `_DirectoryLock` 于该小目录即可，不需要第二套锁框架。增加跨 root 并发及跨 root 未知刷新负例；原 root 的产品锁仍只由工作台持有。
2. **P2：catalog/attempts 匹配不足以证明原件仍可读取。** `store.snapshot_catalog:347–358` 明确只读目录元数据、不校验 raw；`store.query:400–405` 会核真实 raw。第 6 步确认 committed/reconciled 时，应额外读一次目标附近的有界 `/api/query/{snapshot_id}`，核返回 manifest/解释/hash 与指定副本一致且目标日期实际可读。raw 缺失、损坏、query 超时或服务会话变化不能凭旧 catalog 晋级成功。无需新增路由；catalog 选到目标 ordinal 后查询小窗口。无回执的 matching committed 只证明内容已发布，不证明本次尝试完成，也不能伪造 `reused`。
3. **P2：失败终态、预算与 journal 绑定需要固定到可测试行为。** 写明 `not_covered`、客户端离线、拥塞、刷新/发布 unknown 及稳定捕获失败均返回非零退出码；现有 `cli.main:112–118` 只识别部分状态，新增命令必须显式映射。明确所有 HTTP 的绝对总 deadline，慢速分块响应不能每块重置 45/15 秒；HTTP 正文上限之外，还要列有限 GET 核账次数。恢复使用持久化记录中的 raw/hash/解释/原 root，不能使用新命令参数替换；journal 缺失字段、内容损坏或原件缺失停止，不清空后重新 POST。第二次真实执行只在第一轮已发布并可读后进行；不将目标缺失后的第二次调用当作免费重试。

## 已核可复用事实

- `cli.py:53–66` 现有 serve/restore 在 `EvidenceStore` 上下文前分支；新 acquire 分支放同一区间，可在工作台持产品锁时执行且不开第二数据库连接。
- `workbench.py:70–109,288–333` 已有单线程 Store 所有者、上传互斥及 `asyncio.shield`。断开等待者会留下可能继续运行的导入，应核账本；合同对此分界正确。
- catalog 的 manifest 包含 raw hash、格式合同和完整 interpretation；attempts 有 attempt/raw/batch/snapshot 关联，可通过二者联合核对。无需给 attempts 增解释字段或改 schema。
- 现有 `.day` 解码保留原 UInt32 Volume 与 binary32 Amount 的精确数值；合同不走已发现量舍入的 HTTP 值，不混源修正、不升级单位/身份/复权/PIT 资格。
- 单证券、目标日期观察、两次稳定读取、未知刷新不重试、无服务根 fallback 均可执行。两次稳定读取只证明这份捕获，未证明历史完整或当天收盘终值。
- 安装 EXE/SDK 固定指纹限制本次兼容范围。GUI 时间拒绝、分钟空结果、全市场规模与自动调度都仍未验收；当前合同无需增加其实现。

## 修订后解冻边界

只在上述项闭合并复核后，解冻合同所列 `tdx_acquisition.py`、CLI 分支、config 根身份、相关测试与使用说明。保留现有格式/schema/Store/分析指标；复用 Store 的目录锁类不修改其实现。真实验收必须在受控目标工作台运行中发布古越龙山日线，以既有 query 核可见，再独立按32字节记录核全部量额和三条目标窗口。端口/root 拒绝、发布后断连、跨 root 防重入、损坏原件及慢响应的注入测试只证明本工具边界，不替代真实来源资格。

## v0.2 部分复核

合同 SHA-256 `b99bc056bedc27262cfd9a7095c9629152c8f2ff0eea0539b637f06e20fb8cc8`。规则 1 已改为客户端路径作用域的私有锁/current journal；同客户端跨 root 共用，恢复固定原 root，**P1-1 关闭**。两项 P2 尚待落入合同及复核，产品代码仍未解冻。

## v0.3 闭合复核

合同 SHA-256 `e3edd36a41ab7d58942f7e25aa9aa449c084b5419958c3ac1bba4019b4484cfa`。本次只读复核修订合同，未执行请求或修改产品代码。

- **P2-2 关闭：** 规则 6 增加按实际原件和既有版本规则计算批次／快照身份，并以目标单行 query 核 raw 可读、日期、token 和精确值。无回执时只记录可读 matching committed 的 reconciled 结果，保留本次尝试未知的边界。
- **P2-3 关闭：** HTTP 固定绝对 deadline 和最多5 GET/1 import，禁止核账轮询；规则 7 固定失败非零退出码、原 journal 参数绑定、损坏或原件丢失停止。真实第二次请求以首轮 committed 且 query 可读为前提。
- 客户端全局锁与原 root 发布恢复规则保持，P1-1 未重新引入。合同仅解冻原列文件及必要测试／使用说明；分钟、调度、全市场扩展、schema、Store 和分析指标仍不在此批准范围内。

执行验收仍须按合同真实取数／运行工作台发布、独立全量原件对账和相关负例测试完成；本评审不声称这些已通过。
