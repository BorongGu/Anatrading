# 034 · 单根源 K 线几何合同反方审查

2026-10-08。独立反方 `/root/candle_contract_rebuttal`。初审对象为 [实施合同 v0.1](../contracts/CANDLE_GEOMETRY_IMPLEMENTATION.md)、[014](../research/014-relative-volume-and-baselines.md)、[015](../research/015-candle-geometry.md) 和现有 Store/numeric/HTTP/前端状态代码。只读审查并新增本记录；没有修改产品、原始行情或分钟任务状态，没有请求行情、运行 SDK 或打开真实数据库。

**初审结论：无 P0；两项 P1 待修订，当前合同尚不可编码。** 本记录不替根方作解冻决定。修订后需由本反方复审，根方另写决定与有限解冻文件范围。

## 必须修订

| ID | 级别 | 证据与失败路径 | 最小修订及验收 |
|---|---|---|---|
| CG-01 | P1 | 合同31行只概括字段类型、状态与 ordinal 校验。现有 `web/src/model.ts:65–84` 只逐项检查 located，query_id 只要求非空，未检查 unlocated 的正安全整数/跨组重复；不能把它直接复用后宣称新结果严格校验。错版本、not_evaluated 却带值、computed 却比例全 null，或 unlocated 错映射，都可能成为成功详情。 | 明确共享 `assertGeometryEnvelope`（名称可调整）的完整结构要求：query/geometry 的 query_id 匹配且 ID 为64位小写 hex；固定 method/qualification/assumption/display_policy/source_qualification；两组长度与顺序逐项一致、ordinal 正安全整数且两组合并唯一、unlocated label=null；状态/原因/方向/全部 null 组合合法；长度为有界 canonical 非负十进制字符串；分子分母为有界 canonical 整数字符串、分母正；percent_display 明确为不含 `%` 的固定两位字符串。浏览器仅做结构/身份验证，不重算价差、分数或近似百分数。为每类错误、两组重复及零 located/非零 unlocated 写拒绝用例。 |
| CG-02 | P1 | 合同33行要求 Blob SHA 与 GeometryId header。现有 `web/src/api.ts:74` 和 `App.tsx:129–151` 的源导出机制验证字节 SHA/头，未解析正文。错误 envelope 若携带当前正确头和自身正确 SHA，仍可下载；新几何导出必须证明正文 Q/G 同当前身份。 | 仅新结构 JSON 导出，在 SHA/两个预期 ID 头通过后解析**这些已验证原字节**，调用同一 envelope validator，并核 query_id/geometry_id/selection 与本次预期一致，再下载原 Blob。解析/映射/身份失败清空当前 Q/G 并禁用导出；await 校验前后均服从现有 Generation，迟到不能下载或回写错误状态。增加正确头+正确 SHA+错误正文 ID/映射/版本、坏 JSON、迟到导出用例。保持旧源 JSON/Parquet 载荷与路径语义。 |

CG-01 无需建设通用运行时 Schema 库或浏览器业务公式。应以小型直接 validator 明确新字段和两 scope 身份约束；不要借此扩展任意格式或全仓重构。canonical 细节可以使用既有序列化约定，但必须落在合同中，避免实现者各自选择。

## 已可支持的部分与限定

1. **局部描述资格。** 同根四个源数的几何无需股数倍率、股份分母或跨日基线。合同7行明确原样继承 assumed/unknown、retrospective、闭合未知，且没有前收盘、形态命名、主动方向或预测输出，符合014的独立推进边界。这只证明源结构；量能/永久身份/公司行动/PIT/分钟兼容及有效收益的门槛维持。
2. **局部精度128足够。** `decimal_value` 已限最多20位整数、18位小数；以1e-18对齐时，每个非负价格和价差均不超过38位整数系数。合法三段非负且总和等于 range，三段加法中间结果亦受同一边界；128位精度不依赖源全局context。必须用 `copy_negate/copy_abs`，避免一元 `-`/`abs` 在外部上下文舍入。Fraction 从已限界 Decimal 构造即可精确；不采用 Decimal 除法或 float 中转。参见 [Python Decimal](https://docs.python.org/3/library/decimal.html) 与 [Fraction](https://docs.python.org/3/library/fractions.html) 官方文档。
3. **实际只读数值探针。** 在外部 context `prec=1, ROUND_UP, Emax=1, Emin=-1` 且 Inexact/Rounded 开启异常的环境中，复用现有 numeric，最大38位价格减相邻1e-18价所得 `0.000000000000000001`，Fraction 为 `1/1000000000000000000`；最大价减零亦保持全38位。该探针是既有数值工具边界证据，尚未证明新几何实现或真实产品验收。
4. **有理值及显示。** 0/1、正分母、range=0 全比例 null 及 half-even 整数 divmod 路线合理。分数为权威，显示两位和不强凑100%。增加 `n/d=1/20000` 得0.00、`3/20000` 得0.02及各半点两侧独立预期；不用浏览器 Number 构造或验证权威比值。
5. **两 scope 全分母。** rows/unlocated 不删异常、不去重、同序同 ordinal 是正确合同。原 Q 包含 raw/解释/版本；新 geometry_id 绑定原 query_id+固定方法版本，可保持源query身份。详情以 `(scope, ordinal)` 查当前 envelope；无法定位的几何不可赋予市场时点，不能进入 cutoff 统计。非法 OHLC 全派生 null，量额失败独立；floatCollapse 不妨碍精确源几何，也不能据它恢复普通蜡烛。
6. **HTTP与存储。** 新导出必须复用 `_bounded_query`、空体/参数白名单/Origin-token/唯一 Store owner，在 owner 内取得同一 Q 并一次重算；不给任意路径或方法入口。不要调用 Store.export_json 后包装成结构导出，该函数会保存源导出且没有几何。原 Store.query/_identity/schema/原源导出均保持。
7. **验收边界。** 7068根原.day UInt32 独立整数复算可覆盖真实数值链；新方法自己的结果与自己的复算不构成独立证明。原件失效清空、两个scope、20k总预算、前缀及新版本隔离、旧导出字节一致要分别验。浏览器实际交互与性能仍单独验收，构建/ASGI/数值探针不能授予浏览器通过。

## 复审区

同日复审 [实施合同 v0.2](../contracts/CANDLE_GEOMETRY_IMPLEMENTATION.md)，SHA-256 `87b1b3dd0570119afa0e49aa29c54857a072ce7eaf62ddbac59912dafe090658`。

- **CG-01 已关闭（合同层）**：新增共享 envelope validator 的固定 metadata/键集/Q-G 身份、两 scope 长度/顺序/安全 ordinal/跨组唯一、source 六值 nullable 字符串、状态及 zero-range/null 组合、canonical 20+18长度/38位分数字串与固定百分显示。前端不计算 GCD/价差/比例，数学资格仍由后端及独立真实验收证明。
- **CG-02 已关闭（合同层）**：新结构导出须解析已通过 SHA 的原 Blob，复用同一 envelope validator；正文 selection/Q/G 与本代次预期及 headers 一致才交付原 Blob。没有 display/navigation 的导出亦可独立验；失败按当前 generation 清空，旧源导出保持。
- 其余原始数值、同根限定、未知语义/闭合/PIT、两 scope 全分母、唯一 Store owner、20k预算、真实 UInt32 独立验收和浏览器实际交互门槛均保留，未因修订解除。

**最终反方结论：无未关闭的 P0/P1；允许根方写入解冻决定后按 v0.2 有限范围编码。** 允许新 `candle_geometry.py` 及针对性测试、`cli.py`/`workbench.py` 必要接口、`web` 的 types/model/RecordDetails/SourceChart/App/styles 和对应现有验证脚本；不批准修改 Store/numeric/schema、源格式白名单、原源导出载荷、单位/PIT门槛、源任务/原件或新增依赖/服务。`web/src/api.ts` 若需要新增 helper，须由根方在决定中显式列入必要薄层范围；复用原 helper 后在 App 调共享 validator 也可满足合同。

本结论只关闭编码前合同阻断；新实现测试、真实全分母独立复算、HTTP/导出及浏览器交互仍待执行，不授予功能/当前软件兼容/预测效力通过。
