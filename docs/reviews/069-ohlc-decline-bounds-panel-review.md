# 069 单窗 API / 双日期面板：独立设计审查

2026-10-14 UTC。

## 决定

**GO：允许按冻结设计进入最小实现与合成验收。** 没有发现要求扩大范围或改动068数学核的阻断问题。该决定不代表产品实现、浏览器视觉、真实数据或金融价值通过。

审查对象：design-v1.md，SHA256 `3787d20ad8d5f50e80a6832fc1680cb5a65ea6f079dfb359b1a105b19faebf54`。
实际仓库 HEAD：`b89b2fae479354ad6d8121af3ab4670957ac1232`，与设计基线一致。

## 对实际源码的核对

- 核读 AGENTS.md；068纯核与完整适配器、research_series、numeric、symbol_identity、Store可信投影与身份函数；065局部HTTP编码器、请求路径、前端DTO/流读取/组件、App接线；068/065相关研究和限定验收记录。
- 068成员ordinal确实为规范十进制字符串或null，合法范围含0且最高至2^63−1。068 identity.selection只有mode/cutoff/ordinal_start/ordinal_end；不含snapshot_id。065的数字ordinal与额外selection.snapshot_id规则不能移植。
- `_load(store,[sid],end,error)`先计完整前缀预算，再经 `_research_query`逐请求核验原件。NULL-label保留；空查询仍核验。end是本次研究截止，不能拿图形query_id、ordinal切片或start后片段替代。
- 068 source_qualification保留原manifest值，不能替换成065三态qualification。symbol_identity沿用来源声明映射及市场别名规则，不根据股票代码推测市场。
- lower/upper/close_only的约分分子、分母最多38位；width分母及中间交叉积最多76位。设计的有界BigInt、极小正数显示、非零假想见证、零值null与收盘见证分离符合源码。
- 完整报告加view_method_id后再用既有_identity绑定，明确排除analysis_id自身；比065旧选择身份绑定更强且不改旧接口。身份不是真实性签名。
- owner内有界保护、最终同一UTF-8 bytes响应、客户端全响应流限额以及结构深度/节点限制，覆盖了新增HTTP字段和核心原256KiB上限之间的缺口。最终上限的动态测试必须真实执行，不能只重述068静态检查。
- 首render/commit上下文与日期门卫、generation、abort、关闭后不得复活，以及父上下文变化立即关闭/清空日期的要求，足以避免只依赖effect清理的旧数值/旧资格闪现。不可逐字复制065现有组件的开放状态清理时机。

## 实现时必须按实际合同解释的三个细节

以下是设计中“依068”“沿现有边界”的具体解释，不新增功能或扩大验收范围：

1. **coverage与invalid_members不能直接等同。** daily_coverage先按daily_bars分类；068在随后成员构建阶段才追加invalid_source_ordinal。因此合法报告可能coverage.invalid_groups=0而invalid_members.length=1。禁止复制065中的invalid_members.length≤coverage.invalid_groups断言，或据此拒绝合法068报告。保留coverage原口径，单独验证成员ordinal首因与invalid_members全等。既有坏价等首因不能被重复ordinal覆盖。
2. **参数预检与来源资格分层。** start/end格式、必填/重复/未知参数、snapshot词法在Store调用前拒绝；20,001行预算在_research_query前拒绝。当前_load是在可信读取后检查period，设计不要求凭请求伪造/猜测期间，也不应把非日线测试误写成“任何Store方法都不得调用”。
3. **结构限制覆盖实际最终树。** 服务端与客户端采用同一深度/节点计数定义，最终新增的view_method_id及analysis_id也计入成功输出；零边界与超一单位夹具应依这一定义冻结。资格、原因和成员不能为通过限额而截短。全报告身份哈希自身使用既有完整序列化，资源成本须包含，不能声称端到端仅一次序列化。

建议把第1点加到实施测试说明中，作为防止误用065验证器的显式回归；不需要重新设计入口。

## 浏览器与权限门槛

设计§1、§6G、末段已清楚允许API与真实ReactDOM/jsdom工作继续，同时保留独立真实浏览器准入门槛。若既有无头浏览器/socket EPERM仍是已确认限制，记录BLOCKED/未验，不重试绕过拒绝，不换环境或改权限规避，不下载新浏览器。浏览器不可用时可提交有限的实现与合成证据，不能声称截图、中文字体、响应式布局、键盘实际交互或主线程长任务指标通过。

## 本次执行与限制

仅额外运行一次现有纯合成fixture的只读Python探针，设置PYTHONDONTWRITEBYTECODE=1：
- ordinal=0得到computed，输出字符串“0”；
- identity.selection恰四个规定字段；
- 重复ordinal导致unavailable/invalid_source_ordinal，同时coverage.invalid_groups仍为0、invalid_members长度为1。
三项断言均通过。未跑全套回归、API实现、浏览器或资源矩阵；这些属于后续实现验收。没有产品文件修改、旧DB/原始行情读取、网络获取、发布或权限变更。
