# 日线自动获取与单写者发布：真实验收

2026-10-08。依据[U1/U2合同 v0.3](../contracts/TDX_DAILY_ACQUISITION_IMPLEMENTATION.md)、[开工决定](../contracts/TDX_DAILY_ACQUISITION_DECISION.md)、[024 实施反方](../reviews/024-tdx-daily-acquisition-implementation-review.md)。一次性 `acquire-tdx` 已在实际 x64 通达信和运行中工作台之间自动完成缓存准备、原件保存与快照发布。没有用户手动下载／导出步骤。

## 真实结果

| 项目 | 证据 |
|---|---|
| 客户端 | `D:\tdx_64\TdxW.exe`，PID25140／启动时点及 exe/SDK 指纹与既有资格一致；每次严格 localhost拥有者核验 |
| 股票／周期／目标观察 | 显式 `600059.SH`，只用 `refresh_kline` 的 `1d`；目标日 `2026-09-30` |
| 首次 | `new_content`；7,068条；committed；reconciled=false；reused=false |
| 再次 | `unchanged_target_observed`；committed；reused=true；不同attempt、同原件及快照 |
| 精确对账 | 全7,068条 ×6字段=42,408个源值；量独立UInt32、金额独立位型→Fraction→Decimal；日期、locator、token、保留字节及规范字段null均核验 |
| 目标窗口 | 2026-09-28、29、30，源序号7066—7068；真实query可读，三行精确字段与raw匹配 |
| 旧快照不变 | 第二次后再次全量对账；56份128条窗口与首次逐字节相同，目标三行文件同字节 |
| 数据根与写者 | 实际 `data/local`，Opaque root id匹配；采集不打开DB，仅既有HTTP导入；工作台持同root锁并通过其单线程owner提交 |

原件 SHA-256：`f9271218e4ae49729d4b38976552432da7bf529aa677a2c89358fa5df6887f30`。
快照：`c3f950f6002fa14ea4569e2e7075722a3c4df897628e6d63e6b4e981cbffd39c`。
两次 attempt：`4243f58b251743e6b97d6ea35d42e5a7`、`fba58206e07b41c6b823045307ffa87c`。

原件、请求/响应、单行query及收据分别保存于私有 `data/local/acquisition/ad38b26212eb4e7ba6f58a57dc9e2c78` 与 `41545e9d1a8a407483212050203d56ee`；资源及独立对账材料在 `artifacts/qualification/tdx-daily-acquisition/20261008-u1u2`，均不提交公开git。金额保留源binary32精确表示，不宣称原始货币金额未被供应商量化。完整交易日覆盖、经济单位、永久证券身份、复权与历史可得性仍unknown/assumed；条件金额异常不删改。

## 故障与资源证据

初始临时验证启动器路径少一层，工作台对应 `artifacts/data/local`；真实CLI的root检查返回failed，未发TQ刷新、未产生行情请求文件。正常关闭该服务后修正辅助启动器，再启动明确目标 `data/local`。产品从未回退到其他root。两次实际行情刷新合计恰为2，均关联id和字符串业务成功码通过；没有账户、订单、SDK执行、分钟、全市场或自动重试。

5个守卫阶段包含一次上述初始化失败及4次成功（两次采集、两次全量审计）；实际Python进程PID/原生exe/FILETIME逐次记录，100ms观察；成功均exit0，耗时6.81—8.83秒，峰值private counters不高于577,716,224字节，低于120秒/2GiB停止阈值。初始root拒绝exit2。守卫是观测性控制，不能约束客户端后台下载，也没有把这些时长当作HTTP500ms性能结果。

受控工作台已正常关闭，`server-closed-2`记录存在；8765不再监听，`data/local/research.duckdb`无WAL残留。用户通达信未被终止。

关闭后另起实际Python进程，以既有CLI重新打开同一 `data/local` 查询三目标行，完整行对象与首轮窗口一致，分母仍7,068，原件/快照身份匹配，查询后无WAL。此第6资源阶段正常完成exit0，0.753秒，native内存计数最大631,205,888字节，低于相同预算；它与前5阶段分开记录。该运行证明本次持久快照能由新进程读取，反方只核保存文件，未独立打开DB。

采集边界64项测试及独立实现复跑通过；根方完整Python回归354项通过，只有现有Starlette/httpx弃用提示。随后新增CLI帮助/未来日期退出码两项，CLI文件5项通过；没有声称修改测试后的356项整套重跑。没有UI变更，无浏览器更新验收或新前端性能结论。

## 范围结论

只授予“此固定安装、两个显式单股票入口中的古越龙山日线原件自动获取与发布”实测资格。分钟尚未取得有效样本，同花顺/新版本/全市场/连续日常更新和定时调度尚未验收；真实导出语义对账、标准单位和预测效力仍待完成。整体用户目标保持active，下一阶段仍按方案和反方门禁推进。

独立结果反方：[025](../reviews/025-tdx-daily-acquisition-results-review.md)，核验范围以该报告为准。
