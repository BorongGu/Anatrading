# 共同端点单组入口：独立代码反方审查

日期：2026-10-12 UTC。最终回读约05:19。基线：`89db7c0edf36e1cb34b035ee6d86658aa28527db`，分支`feat/common-endpoint-group-20261012`，审查对象为作者尚未提交的候选工作树。

## 结论

限定工程范围内，最初发现的问题已由作者修订，并经本审查者独立复现脚本回验关闭。最终回读未发现剩余实质阻断。可以进入主方最终验收、整理与提交流程；此结论不代替最终受影响回归，不授予额外发布或数据访问权限。

重点判断：新入口没有扩大030算术来源资格，没有借043训练失败输出替代单组摘要，没有修改020或Store；保留原N、失效成员和未评估状态；只有完整组进入四项分布统计；客户端从有界规范端点派生行分数，不累计任意4096位响应整数；回查仍只是现有版本日期前缀。前端身份校验与端点恒等式不构成对原件归属的独立认证。

## 范围与方法

已读AGENTS.md、048研究、2026-10-12实施方案、编码前设计审查，静读本轮完整产品差异及新增后端、API、Universe分派、GroupEndpointResults、group-endpoint-model与新测试。回读必要的既有numeric、symbol_identity、研究控制器、Store研究投影、旧030/043实现与公开合成测试源码。

审查者未修改仓库。仅写本报告与自己的`/tmp/review_group_*`合成测试脚本、DTO及临时Store。所有运行输入均由本次新建脚本生成，无真实行情、旧Store/旧DB或私有fixture读取。没有浏览器、采集、外网、依赖安装、凭据或权限变更、性能实验。使用既有Python环境与Node。

## 发现与修订闭环

### C1：拒绝源的非A股身份导致前端丢弃整组（已关闭）

原`group-endpoint-model.ts:98`把所有成员的symbol限制为六位SH/SZ/BJ。后端可按既有symbol_identity归一化HK或US身份，在来源资格拒绝后留下not_evaluated行。新合成4成员DTO中一只AAPL.NASDAQ，后端返回scope_conflict、N=4/K=3，前端却拒绝整个合法报告。

修订：新增有界sourceSymbol规范语法；evaluated仍仅限SH/SZ，not_evaluated可显示既有归一化HK/US/BJ身份，不获得价格资格。独立Python→JSON→JS复验现在接受该报告并验证身份。源资格本身未放宽。

### C2：报告暴露可变模块常量（已关闭）

原group_endpoint_report直接把_GROUP_SCOPE与_GROUP_LIMITATIONS交给调用者。修改前一份返回的scope.asset_type或economic_return_qualified，会污染后续相同输入报告、限制说明与analysis_id。

修订：每次构造独立scope子字典和limitations字典。独立复现重新运行后，后续报告仍为stock与economic_return_qualified=False，不受前份返回值修改影响。

### C3：DTO内部可判定矛盾通过验证（已关闭）

最初三种变异均通过assertGroupEndpoints与analysis_id：不同共同日期复用同一非空ordinal；已披露inside_interval/local_source_conflict却没有member阻断原因、仍计入有效K；未截断两例同一异常代码而总计数为1。

这些是载荷自身的矛盾，不能归入“合法ordinal/token无法独立认证原件”的已知信任边界。

修订：两端非空ordinal须不同；unknown例必须保留完整性阻断，区间内/unknown已披露local与unclassified阻断须进入成员原因；未截断例逐码计数须完全相等，截断例计数不得超过总计数。三种原变异均已独立回验为invalid_group_endpoint_response。

### C4：异常计数补验引入原型名与Unicode误拒绝（已关闭）

C3初次修订用普通对象计数未知代码，`__proto__`、`constructor`、`toString`命中继承属性；同时以仅接受ASCII的既有canonicalJson比较异常字典，合法未知代码“未知核验”抛invalid_filter_rule。后端冻结合同允许未知异常名称被披露，不能为前端方便新增名称白名单。

修订：计数器使用Object.create(null)，未截断计数直接比较own key集合和值；未扩改通用canonicalJson。groupReason也采用own属性查询。上述四种名称均用本次新合成DTO经Python报告、JS断言及身份验证独立通过。

## 独立运行证据与实质判断

1. 旧行为差分：在独立命名空间加载基线peer代码，与候选比较返回值或异常类型/文本。270组_source单错/多错、96组完整030含halt/公司行动/scope事件、48组043短历史及62点合成训练面板全部相等。覆盖qualification先于counts、已知负样本/批次拒绝先于行结构、price_unit语义先于adjustment字段形状等顺序。没有通过修改旧期望迎合实现。
2. 新结构预检：unsupported qualification或known-negative与错误counts、重复ordinal、行values/checks、interpretation、semantics字段形状交叠的14组独立反例，全部在整请求层按预期拒绝，没有降级为普通失效成员。
3. 有界精确算术：50成员使用合法DECIMAL(38,18)边界附近端点，均值分母达到1864位。后端结果与独立Fraction求和/50相同，JS从端点派生后核对整份报告与analysis_id通过。未放宽单行38位推导界或Python整数文本限制。
4. 异常截例：某成员前20例为量额异常，第21例为区间内身份反证；输出只列20例，仍保留总计数与local_source_conflict，K从4降为3。前端也接受这份合法截断报告。证明资格判断在输出截例之前完成。
5. 全新临时Store→ASGI API：四份源先全部count再全部load，cutoff全部None；模拟一份20001行预算时仍完成四份计数且零加载；重复/未知参数在任何Store调用前拒绝。同长度破坏原件返回409 raw_object_corrupt，移走原件返回409 raw_object_missing，均为整请求失败，无members伪缺失；恢复后显式重试与原报告完全相等。
6. 实际前端prepare/load/controller：共同端点只命中新路由、绕过旧lookback/filter脏草稿；重复提交锁；取消后发起新请求，旧成功或旧错误均不能覆盖新结果；hash等待中invalidate并dispose不恢复结果。均用本次新合成报告运行，通过。
7. 回查静态核对：GroupEndpointResults两个按钮仍调用onOpen(snapshot_id, start/end_date)，App原签名未变；文案明确日期前缀、不会聚焦源序号、完整query_id与前缀query_id不同、缺端点不前移。
8. 代码静读确认：events在纯函数先经_auxiliary后共享原事件校验；HTTP不接附件、输出空events；UI明确覆盖未知。无新来源/训练模型/导航平台/依赖/Store写链路。git diff --check通过。

本审查自己的可复运行脚本：`/tmp/review_group_endpoint.py`、`/tmp/review_group_endpoint.mjs`、`/tmp/review_group_differential.py`、`/tmp/review_group_api.py`、`/tmp/review_group_boundaries.py`、`/tmp/review_group_lifecycle.mjs`。差分与生命周期日志：`/tmp/review-group-differential.log`、`/tmp/review-group-lifecycle.log`。这些均为新合成材料，不应作为真实来源样本。

## 实际通过、失败、跳过、未验

- 审查者实际通过：上述独立新合成DTO/Store、差分、精确算术、反例、请求控制与静态回查范围检查；C1–C4最终复验关闭。
- 审查阶段实际失败：C1整组误拒绝、C2跨报告污染、C3三种矛盾被接受、C4原型名/Unicode误拒绝均曾独立复现。它们没有被通过总数掩盖，作者分别修订后重新验证。
- 当前未关闭失败：本次限定审查未发现。
- 作者另报最终Node 275通过、TS/Vite通过；过滤Python整目录3262通过、1项Windows跳过、34项deselected，并ignore真实pipeline文件14例。本审查未独立重跑其整套命令，也不将这些数量当作上述实质判断的替代品。主方应保留真实排除清单与最终命令日志。
- 未验：未过滤Python全套、真实行情/真实软件文件兼容、浏览器React挂载/键盘/视觉与bfcache实测、Windows原生、性能、真人效率、预测/交易或经济效果。本次SSR/纯控制器证据不能提升这些状态。

## 最终回读产品文件指纹

- peer_relative_research.py：d560a95a5c8a9c5cc8588ec793cb61277678f1e730d7d1df59e73ec70e6db7aa
- research_api.py：4f0383a8859592695c23b97dfb93c77057bebc58f10900c99c1d5e27b6b47823
- group-endpoint-model.ts：60986f15518c5787b3b1692c147d7461c864515a296fea105ab2d026da5c3bf1
- GroupEndpointResults.tsx：dfafe5ed6cc803e9f2ee39473f6ca8c119479db3e9dd16f50e1970b3e45175a9
- UniverseResearch.tsx：cc017814fd2c5debc4c42ca4cfec859a16412eb020f09a154eed467c684ff23a
- universe-request.ts：a7a3c462883adb5327e6875c0b0b46e0db755996337aa659c72a123a6acff1f6

这些指纹限定本次代码审查对象。后续产品修改需按受影响范围重新验证；最终文档整理不自动改变本报告对产品的范围结论。
