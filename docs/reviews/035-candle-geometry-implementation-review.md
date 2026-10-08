# 035 · 单根源 K 线几何实现与真实审计复核

2026-10-08。独立反方 `/root/candle_contract_rebuttal`，承接 [034](034-candle-geometry-contract-review.md)、[v0.2合同](../contracts/CANDLE_GEOMETRY_IMPLEMENTATION.md) 及 [开工决定](../contracts/CANDLE_GEOMETRY_DECISION.md)。审查后端 `candle_geometry.py`、CLI/HTTP 接口、新 Python 测试和最终前端 types/model/api/App/RecordDetails/styles/tests。只新增本审查记录；没有更改产品或源文件，没有请求真实行情、执行 SDK、重开真实服务/数据库或清除原分钟状态。

**结论：当前被审实现未发现 P0/P1。CG-01/02 的实现路径与合同一致。后端/API/CLI真实单根数学证据成立；浏览器实际交互门槛仍 pending，完整量能/PIT/分钟/预测与竞品目标继续未完成。** 根方最终全套回归和构建结果需在资格文档独立登记，本审查不以其他 agent 报告代替本次实际运行。

## 数值、身份和接口

- 四价格逐个复用 `decimal_value`，缺值/非法/负价/包含关系按冻结顺序拒绝；整个派生行 null，源行和量额保留。`exact_sum` 配合 `copy_negate/copy_abs` 避免外部 context 舍入；没有 Decimal 除法或 float 中转。合法公式代数保证三段非负、和为 range；有限38位系数远低128位局部精度。比例由 Fraction 约分，显示由整数 divmod 的 half-even 实现，零分子0/1、零range比例全null。
- 行函数不读取其他行；报告保留两个 scope 的原序，Q/method生成独立 geometry_id，继承 manifest qualification，不改原 query/Store/schema/源导出或规范单位。具体方法参数全部被冻结在 method_id；未来公式/舍入变化必须换方法版本。
- HTTP查询及新导出在原唯一 owner 内运行。导出 `_bounded_query` 重新核原件与两 scope 合计20k预算，然后重算同Q；预期Q/G分别拒绝409，路由检查ID格式、空体、参数白名单并继承Origin/Host/token。新导出不落盘或调用源导出器。CLI复用原Store持锁生命周期及原selection，真实CLI从正常关闭后的库读取。
- 新测试实际覆盖异常价格优先级、上下文/38位边界/half-even两侧、零实体/零价/零range、量额失败独立性、平移/缩放、未来行与方法身份；API测试包含两scope/重复标签/零定位非零unlocated、旧源JSON及Parquet字节一致、原件坏、错误身份、空体/权限及20k总预算。这些临时合成库只证明边界行为。

## 前端复核与本次运行

共享 `assertGeometryEnvelope` 检查固定报告/entry/ratio键、Q/G64hex身份、方法/资格/assumption/display_policy、selection/counts、两scope顺序及安全唯一ordinal、unlocated标签、六源nullable字符串、canonical有界长度/分数与状态/null/zero-range组合。前端不重算业务几何/GCD/比例/舍入；数值恒等式通过后端及独立原整数验算取得。`assertReply` 先走共享校验，再检查图形映射；floatCollapse继续占位，精确几何仅进入详情。

`verifiedGeometryExportBlob` 先验原Blob的SHA与Q头，再验G头、固定{query,geometry}正文、共享validator和预期Q/G；通过交付原Blob，无重序列化。App在导出请求及Blob核验的await之后分别检查Generation；当前代次失败使Q/选中详情/图/export状态失效，迟到代次不能下载或回写失败。固定详情保留源资格、近似标记、权威分数与无法定位限定；compact详情没有新增长表。旧源导出helper未改语义。

本反方运行 `node --test tests/model.test.mjs tests/geometry.test.mjs`：**18/18通过**。包含两scope/固定版本/异常null/canonical字符串/结构导出错正文映射或身份/空JSON/原Blob字节，以及原Generation和显示边界。它们为模型/helper测试，**没有实例化真实浏览器交互、组件竞态或下载行为**；静态React渲染、其他33项总测试和构建报告也不能替代浏览器门槛。当前根方已记录 browser/iab 不可用，应在资格文档保留未验。

最终报告复核：根方告知完整Python回归474项通过、114.23秒、仅1项既有Starlette/httpx弃用提示；根方运行全部前端33项通过，前端builder报告构建通过。这些结果据执行方报告登记，本反方没有重复运行全套或构建。[资格文档](../qualification/candle-geometry.md)的有限源结构/API/CLI结论与本审查一致，真实异常样本、空旧导出分母、浏览器交互及完整目标未完成均明示，未发现需要阻断的过度推广。私有“完整API”材料按本页限定为全部行的解析后envelope，未授予完整原HTTP字节捕获资格。

## 私有真实证据的只读复核

目录 `artifacts/qualification/candle-geometry/20261008-g1/` 不提交个人行情。反方读 `audit_import.py` 源码，随后用AST仅抽取 `canonical_cents/ratio/audit` 三个纯函数，结合当前原.day读字节重新核已存 API/export；未导入执行该文件的Uvicorn/HTTP主流程。

| 项目 | 本次复核所得 |
|---|---|
| raw | SHA `f9271218e4ae49729d4b38976552432da7bf529aa677a2c89358fa5df6887f30`，7068×32字节；用 `<5I` UInt32原价和原日期/byte定位生成独立整数几何 |
| 全分母 | API及geometry-export两份每根精确长度/方向/分子分母/百分显示与独立整数结果一致；7068条，up3562/down3316/equal190；该样本zero_range=0、unlocated=0，无非法OHLC |
| 身份 | query `f00e4b0cc212f6c4389b4012c71f6547f035954d6b77c6fd086ad3ce3e570cb2`；geometry `60f2ff573a5ad522ecd286dfba4a73dc9aec909903883b84ab0dbe16f26cce10`；快照 `c3f950f6002fa14ea4569e2e7075722a3c4df897628e6d63e6b4e981cbffd39c`。纯标准库重新算方法/Q哈希相等 |
| 派生导出 | 保存的是真实导出原字节；SHA `e99bd27da50b1fecb2630682831308da660fb0646896ed11c01716cd2c14fe3d`，JSON与API envelope逐项相等，独立重算全7068通过 |
| CLI | `cli-full.txt`按UTF-8-sig读取，与API envelope全对象相等；无需重开真实DB或再次执行命令。CLI资源记录complete/exit0，1.760748s，native峰695566336B |
| API资源与关闭 | 完整审计进程日志complete/exit0，7.066956s，53次100ms名义采样，native峰801611776B，未达120s/2GiB边界；日志含PID5624和创建FILETIME。server-closed记录正常lifespan关闭；反方当前只读检查PID5624已不在、8765监听数量0 |

审计的近似舍入通过相邻整数候选按距离/偶数选优，独立于产品divmod分支；数值预期没有导入产品几何/numeric。API-full.json是HTTP解析后保存的{query,geometry}对象序列化，**不是完整HTTP原字节捕获**，没有display/navigation；不能用于原HTTP字节身份或500ms性能资格。上述7.067s是多次查询/导出/审计的整阶段耗时，不能当单次响应p95。

重复API相等、首128前缀相等、原目标3行Q与早期persisted-query相等、源JSON等旧Q canonical字节且派生前后不变、client-control两文件未变，来自完整审计实际执行的assert及结果/exit0。当前私有原件再次hash复核成立；反方没有重新发请求重放这些历史动作。`preserved_prior_export_files=0`的分母为空，**不能宣称已有旧导出文件全量保存验收**。真实Parquet、真实零区间/坏OHLC/unlocated与新的浏览器交互还没有由本次真实日线材料证明；对应合成边界测试不得升级为真实供应商证据。

## 被审代码锚点

- `candle_geometry.py` SHA `50ddf2308fa95410fe077258ee89b2efcf629b80d59757e25b3a06fff732f804`
- `workbench.py` SHA `54e6a9b2efad1fd9a4050157bff560133a242afea0d2ecf9780db6ef01969417`
- `cli.py` SHA `85606d3394f8517be1d46965b3064bb8b4dcabb2e703eff4d3c16e09d7bb0ba4`
- `model.ts` SHA `c069bb5e1535002f3921cbc5a069656504d0f25e37a0ae3d37455786e7c0e4ce`
- `api.ts` SHA `0adbc80eaff4fdbfd669be63c9b25d1f38b377ec1590a4d0f9754e2d910bdc6c`
- `App.tsx` SHA `69e75dd29f973e8bb65c6b21d75315804e2c02248a11a5be3924fd4c722b9059`
- `RecordDetails.tsx` SHA `bb9e9252d13d80d99d405a22faf6f32e9455e298b0a715027772f2559f4879f9`
- 私有审计脚本 SHA `f319f9de59d9055bd969ee39485653418b005041c7e007936072424250ddee06`

后续若改变被审路径，按实际diff复审；Git换行归一会改变工作树字节SHA时，须区别公式变化与字节换行变化。无必要扩大本切片、放开跨日资格或请求当前未知分钟任务。
