# 多股条件筛选界面整合计划

日期：2026-10-11。状态：**最小 web 已实现，全前端 128 项及 TS/build 通过；独立实现复审 §8 已通过，真实浏览器仍未验。** 面向实现者与独立评审，目标是让已有明确成员的研究组完成“设条件、看入选与失败、回查来源”的小闭环。

依据：[032 筛选研究合同](../research/032-explainable-stock-filters.md)、[032 设计批准](../reviews/2026-10-11-explainable-filters-review.md)、[032 实施计划](2026-10-11-explainable-filters.md)、[030 同区间研究](../research/030-peer-relative-research.md)、[030 纯函数合同](2026-10-11-peer-relative.md)、[030 独立实现审查](../reviews/2026-10-11-peer-relative-review.md)。本轮实际读了现有 `CrossResearch.tsx`、`App.tsx`、`research-model.ts`、`research-types.ts`、`ResearchResults.tsx`、`api.ts`、`styles.css`、现有前端测试和 HTTP 约定。下述 032 响应字段已与作者逐项沟通；05:45 UTC 按作者确认的最终去重结构复核 `stock_filters.py`（SHA-256 `345b54b8683ffaf487b277931f46a550dcbe2d559fba313a423d5542d94dc571`）及其 `_member/_counts/filter_report`。API 安全错误同时核对 `research_api.py` 和 `workbench.py`。短引用/共享来源只改变响应表示，算法政策及规则哈希不变；仍须独立实现复验与本 UI 复审。

## 1 首片取舍

**先把 032 的有限 AND/OR 筛选接进现有“多股研究”。** 保留同一份成员选择、截止日期和来源窗口，一次新请求同时获得原集合结果与三态筛选结果。用户新增的操作只有添加条件和查看原因，不增加工作区、第二份选股池或综合分数。

030 已有单目标纯函数、独立实现审查，以及[八个真实案例和 200,000 行资源验收报告](../qualification/peer-relative-research.md)；本文已读报告但未重跑，不将这些证据记作 HTTP/UI 通过。030 仍缺完整快照 API、可信组说明入口以及声明/证据的交互。现有界面的自由集合名称无法提供 group descriptor，更不能认证行业、A 股品类或 CNY。因此本片不展示未接通的同行按钮，也不把原 `universe.momentum` 相减冒充同端点比较。后续入口边界见 §10。

选择 032 的直接价值是少做手工比对，并明确回答：哪些成员满足哪组条件；哪些确定不满足；哪些仍待核；已经入选或排除时还有哪些条件未知。032 的 API 实现/独立验收仍是接线依赖，不能因设计获批便假定路由可用。

范围固定：日线、当前明确成员、同市场兼容组、2–50 份不同证券版本、三字段、最多两组条件。只读本地研究；不新增数学、买入分数、预测概率、自动交易、规则脚本、自动选组、数据采集、云同步、导出协议、新依赖、数据库表或通用状态管理库。长期 TradingView 目标沿用 [031](../research/031-tradingview-advanced-roadmap.md)，本片不宣称完成竞品替代。

## 2 最小完整流程

### 2.1 从现有明确成员开始

1. 打开“多股研究”，继续使用当前已导入日线选择器。把现有“筛选已导入日线”改成“搜索代码或名称”，区分名称搜索与数值筛选。搜索只改变候选列表，不改变已选成员。
2. 已选数量和“查看已选版本”常驻。每股显示证券声明、版本短 ID；展开可看完整 ID。集合名称可选，仅为当前页面标题，不发送给算法，不赋予行业归属。API 拒绝重复证券版本时请用户选择保留哪份，不自动替换。
3. 指定截止 D 和 N，N 默认沿用 20、允许 2–252；标注“来源区间”，旁边一句“每股实际起点可能不同”。D 不默认回退到各股末日，不以浏览器时区计算日期。
4. 未加条件时保留原“研究所选股票”流程。点击“添加条件”才展开组 1：选择字段、填写阈值；首次阈值留空，不预设最优参数。组内固定“同时满足”，最多三项且字段不重复。需要第二条备选标准时点“或，再加一组”；最多两组。无 AND/OR 任意切换器或嵌套规则树。
5. 运行前逐行显示单位和整句条件预览；主按钮为“按条件研究”。空阈值、空组、重复组或越界输入原位提示，不能请求空规则。关闭条件后重新运行原集合研究；旧筛选报告立即失效。

### 2.2 看结论并复核

请求成功后顺序固定：范围及条件摘要 → 全组计数 → 全成员列表 → 按需展开的证据。成功播报“已完成，共 M 只；入选 S、排除 E、待核 U，其中 P 只仍有条件待核”。P 与三类有重叠，不能相加成第四类。

- 计数直接展示服务端 `counts.selection`，分母为 `selected_members`。默认显示全部，成员每只一行。入选、排除、待核页内筛选只是视图，不发送研究请求，也不改变总分母。
- 列表沿 `result.universe.members` 的既有动量顺序，按 snapshot_id 关联筛选成员。显示原集合名次，不根据可见子集重编号。条件模式仅从旧 universe 取排序、名次、基线数值/原因与广度；列表和证据的实际起止统一取匹配筛选成员的 member.window，绝不以旧 universe.end_date 或请求 D 补空。字段为“状态 / 证券 / 收盘变化 / 来源区间波动 / 收盘路径回撤 / 实际起止 / 原因”。无值写“—”并紧邻原因，合法零值照常显示。
- 每行的 `partial_evidence=true` 都有“仍有条件待核”文字，入选和排除行也保留；紧邻显示首个相关未知原因。主要结论不靠红绿或悬浮提示传达。筛选摘要从已启用原子的 `reason_refs` 取相关原因；不能直接拿可能属于未启用 V 的 member.primary_reason 当作筛选阻断。未启用字段失败留在基线对应项，清楚标明用途。
- “查看条件与来源”在行内展开，不跳页即可完成复核。按组列服务端组真值及全部启用原子，显示实际值、阈值、比较方向和真/假/未知；共享原子可在两组引用，证据只保留一份。全部成立组、每组所有失败原子和所有未知原子都能看到，不能只给一个方便的理由。
- 证据区依次呈现真实来源窗口、首末 close、回撤峰谷（适用时）、未知/失败原因、来源说明。缺 D 时实际 start/end、first/last 均为 null，actual_groups=0，显示“缺少截止日期记录，未形成此次窗口”；D 仅出现在单独的请求截止位置。存在 D 的短历史保留已有实际窗口与不足原因。原因总数与最多八个日期/ordinal 示例一起显示；`omitted_count>0` 明示“另有 X 个日期槽”，不能显示成已列全部原始缺陷。重复日期的 ordinal=null 保持不可唯一定位。
- 来源摘要在当前报告内可读，不另发请求。需要原始行时使用既有“查看个股”入口，传相同 snapshot_id 与 D；该页的公开来源查询是另一次原件核验。筛选事实的 query_id 留在证据区，不把新页面的 ordinal 裁剪查询冒充原筛选查询。

### 2.3 回来继续研究

当前 `CrossResearch` 会随切换卸载，草稿也随之丢失。本片只将多股草稿（版本 ID、D、N、集合名称、条件输入及是否启用）提到 `App` 持有的局部状态；不建全局 store、不写浏览器持久存储。切至个股或数据管理时取消等待并清除研究报告，返回多股保留输入，提示“条件已保留，重新运行可核验当前数据版本”。不自动重发。

草稿中的已选版本若不再出现在目录，保留该选择并标“版本暂不可用”，要求处理后再提交；不能静默缩小集合。页面刷新允许草稿丢失，明确没有保存研究任务或全部历史尝试。当前应用没有 URL 工作区路由，本片不新增 history 条目、不拦截浏览器 Back/Forward；整页离开按卸载清理，bfcache 恢复时清除报告/请求资格并要求重跑。真实导航和恢复行为单列浏览器验收。

## 3 条件输入与数值展示

仅有下列三种行，操作符固定，不给无效组合下拉项：

| 显示文案 | 用户输入 | 发送原子 |
|---|---|---|
| 收盘变化至少 | −100～1,000，百分比 | momentum / gte；输入精确除以 100 |
| 来源区间波动至多 | 0～1，log 单位/来源区间 | volatility / lte；十进制字符串原单位 |
| 收盘路径最大跌幅不超过 | 0～100，百分比 | max_drawdown / gte；输入精确除以 100 再取负号 |

“最大跌幅不超过 10%”的实际条件预览必须同时写“回撤 ≥ −10%”。波动不得套用当前 `formatPercent`，不得写年化波动或年化 2%。动量在主界面称“收盘变化”，公式/字段名在详情保留。阈值仅为用户给定标准，无优越性或交易建议含义。

阈值用受控文本输入，输入/编辑中间状态可为空或只有负号；提交时严格校验。M/DD 百分比最多 16 位小数，转换后精确比例最多 18 位小数；V 最多 18 位。采用有限十进制字符串移位和符号处理，规范尾零/负零，不经过 JS Number、parseFloat、toFixed 或科学计数。UI 允许范围、规范结果与 032 十进制语法一致；超精度直接提示，不截断。日期继续严格 ISO 字符串，不经 Date 转时区。软键盘提示不能阻止负数或粘贴输入，需真实设备验收。

结果数值和真值来自服务端：

- M/DD 紧凑显示可用现有估计格式，但明确为舍入展示；详情保留服务端 `exact.numerator/denominator`，源 close 保持字符串。两个值都显示 5.00% 而结论不同是合法情况，提示“按精确值判定；显示值已舍入”。不得从舍入值重判或修改徽标。
- V 显示 `≈`、log 单位、未年化；详情保留 `estimate_text` 和 `float_hex`。不在前端重算标准差、容差或 epsilon。
- 前端只做输入单位表示转换、显示格式和响应结构核验，不重算 M/V/DD、AND/OR、source_gate、selection_state 或排名；合同冲突使整报告不可展示，不自行修正服务端结论。

## 4 资格与 partial 的可见合同

结果标题下常驻：“基于当前所选版本回顾历史；来源价格条件，复权、历史可得性与交易日历仍有未核项。”具体值以各来源原摘要展开，泛化提醒不能替代 `applicability` 等字段。

| 服务端情形 | 主行和展开后的必要表现 |
|---|---|
| gate=pass，logical=true，证据完整 | 入选；列全部成立组，称“满足条件”，不称已验证信号 |
| gate=pass，T OR U，partial=true | 入选 + 仍有条件待核；说明已成立组和另一组每个未知原因 |
| gate=pass，所有组已知为 F，但有 F AND U | 排除 + 仍有条件待核；每组已知失败和 U 同时保留 |
| gate=pass，F OR U / 全 U | 待核；保留已知失败组，并说明尚不能确定的组 |
| gate=unknown | 待核；优先“来源中存在无法定位日期的记录”，所有价格条件 U；底层原 universe 数值只作诊断，标“未用于此次筛选” |
| 日期 gate=pass 但缺 D、历史不足、坏 OHLC、局部身份/调整冲突 | gate 只表明源日期可定位；展示实际事实失败，不把 pass 翻译为来源已认证 |
| 只有未启用 V 数值失败 | 保留基线 V 的失败；不因此增加已启用 M/DD 条件的 partial |
| Store 原件、全局身份或未归类内部异常 | 整请求错误，不给部分成功名单、不自动删成员 |

`source_gate` 的中文含义只限“源日期可定位性”；不能称交易日历完整、行情覆盖 100% 或证券身份已核实。`CN_A` 仅为市场兼容分组，新增列表不沿用当前 `UniverseResults` 把它直接写成“A 股”的品类认证；显示“沪深北市场分组 · 来源声明”，实际品类/币种根据来源摘要呈现。已知反证依后端拒绝，未知资料保持未知且不额外封掉合法来源算术。

六个来源语义字段逐项保留 value/status/reason/applicability 的 absent、显式 null 和原值；例如 `known/CNY + documented_meaning_only + applicability=unverified` 展示“文档含义为人民币，本样本适用性未核”。`requested_adjustment=none` 只称请求未复权，不改成已核未复权。详情保留 legacy/transport/provenance/interpretation 标记以及公开查询/来源合同标识。

## 5 API 和响应接线

### 5.1 请求及预算

使用已批准的只读 `GET /api/research/universe-filter`，唯一参数 `snapshot_ids,cutoff,lookback,rule`。snapshot_ids 为排序后的不同 64 位小写十六进制 ID，逗号连接；D 必填，N 为 2–252 整数；rule 是 UTF-8 JSON 经过 URLSearchParams 编码，不接可执行表达式。开启条件时仅发这一请求，不能先调用 universe 再调用 filter。关闭条件时走原 universe，旧响应合同不变。

- 规则仅 `any_of[1..2].all_of[1..3]`，原子精确为 field/op/threshold；最多六次出现，组内字段不能重复，两个规范组不能完全重复。规则解码后、JSON 解析前最多 2,048 UTF-8 字节。
- 2–50 成员；每股截止前缀连同未定位行最多 20,000 行，总计 200,000 行。N 小不能绕过完整前缀预算。服务端先验证规则，再计数全部来源，超限时不加载、不算指标。
- 同次至多 M 次计数、M 次紧凑读取/原件核验和 M 次归一化，共享窗口一次。没有前端原件缓存或后台自动预取；展开本报告的证据无需新研究请求。
- 沿用 032 的响应工程门槛：新增条件/来源摘要 ≤256 KiB、总响应 ≤512 KiB；真实达到情况由实现性能验收决定。新请求窄封装对成功和错误正文都以 512 KiB 的解码后累计字节为上限，再解析 JSON；不只相信 Content-Length，不先调用会在错误分支直接 response.json() 的旧 checkedFetch。超限立即取消正文流。超限明确错误，不截断后展示。仅作用新端点，旧 single/pair 响应不受此限额变更。
- 同源、Host/Origin 检查、cache=no-store、原件每次核验、owner 串行线程和既有安全错误形状不变。GET 不接受路径、账户权限或外部行情地址。

### 5.2 最终接线结构

下面按 05:45 UTC 作者确认的最终去重源码盘点字段；不是 UI 已验收声明。`ResearchEnvelope` 的旧严格顶层校验不能直接套用；为新方法加专用类型/验证器，旧验证器继续原样通过。

- 顶层：`method_id, inputs, parameters, rule_id, source_metadata_id, analysis_id, base_analysis_id, mode, qualification, limitations, result`。method=`selected-source-price-filter-v1`，mode=`retrospective`，qualification=`conditional_source_price_filter`。
- parameters：`cutoff,lookback,canonical_rule,policy_versions`。当前 policy_versions 为 `rule_schema=bounded-price-filter-v1, window=daily-source-date-groups-v1, logic=strong-kleene-eager-v1, comparison=fraction-and-binary64-v1, source_gate=source-date-locatability-v1`。
- canonical_rule 保留 `any_of/all_of/field/op/threshold` 形状；原子按 field/op/规范阈值排序，组按规范 JSON 排序。UI 的组 1/2 是作者操作顺序，响应按组内容标识映射回原组名；不能假定数组第 0 项永远是编辑器第 1 组。
- result：`universe,sources,source_contracts,conditions,reason_example_fields,members,counts`。`universe` 与旧纯函数结果相同；其排序和身份由原算法负责。不能把它加上新顶层字段后冒充旧 envelope，展示复用只做显式适配。
- member：`identity,snapshot_id,source_ref,window_ref,window,source_gate,logical_truth,selection_state,evidence_complete,partial_evidence,facts,atoms,groups,reasons,primary_reason,proof_groups`。
- member.window：`snapshot_id,query_id,cutoff,lookback,method,start_date,end_date,id,unit,expected_groups,actual_groups,n_prices,n_returns,first,last,drawdown_witness`。unit=`source_date_groups`；first/last 和 peak/trough 是 `{date,ordinal,close}` 或 null。window_ref 必须等于 window.id。条件列表接受旧 universe.end_date=D 而新 window.end_date=null 的合法差异；新 window 自身为空时若伪造实际端点则拒绝报告，前端不修正 API 响应。
- facts 以三字段为键，每项 `value,reason,comparison_type,exact`；M/DD exact 为分子/正分母字符串或 null，V 另有 `estimate_text,float_hex`。facts 有值不自动表示可以用于筛选，仍须依据服务端原子/gate 状态。
- result.conditions：唯一原子定义 `{id,field,op,threshold}`，按规范 `(field,op,threshold)` 排序编号 `a1…a6`；最多六项，跨组相同条件共享。member.atoms 只含 `{id,truth,fact_ref,reason_refs}`；通过 id 查本报告 conditions，再查本成员 facts[fact_ref]，其中 comparison_type 在 fact，窗口通过 member.window_ref 取得。不得仍读取旧 atom.threshold/window_ref/comparison_type 字段。
- groups：`id,atom_ids,truth,false_atoms,unknown_atoms`；`g1/g2` 对应本规则 canonical 顺序，proof_groups 引用全部已成立组。aN/gN 只在当前 rule_id 内有效；rN 只在当前成员内有效。先完成规则绑定，再解析短引用；React key 和证据索引必须带成员/规则作用域，不能把另一股的 r1 或另一规则的 a1 当成同一证据。编辑器组名按规范组内容反查，不能依短ID固定叫第1/2编辑组。
- reasons：`code,scope,field,count,examples,omitted_count,id`；按固定顺序生成本成员 `r1…rN`。examples 每项严格为 `[date,ordinal]`，顶层 `result.reason_example_fields` 必须精确等于 `["date","ordinal"]`；保持 null 不补造值。拒绝错列名/元组长度或孤立引用，不再按旧对象形状读取 example.date。primary_reason 是首个原因 code 或 null，只用于相关摘要，不替代完整 reasons。
- source：`snapshot_id,query_id,identity,raw_sha256,metadata,id,contract_ref`，每来源身份/元数据保留一份。result.source_contracts 每项为 `id,source_contract_id,format_id,contract_version,versions,semantics_scope,semantics`；只共享六项投影完全相同者，不因 format_id 相同就合并。先以 member.source_ref 找同一 snapshot/query 的 source，再以 contract_ref 找完整共享合同；原有 absent/null/applicability 包装全部保留。source.id、contract_ref 仍为服务端内容身份，客户端不据它们认证来源。
- counts：`selected_members,selection{selected,excluded,undetermined},logical{true,false,unknown},evidence{complete,partial},source_gate{pass,unknown},atoms{id:{true,false,unknown}},groups{id:{true,false,unknown}}`。

`rule_id = SHA256(规范 JSON {canonical_rule,policy_versions})`，与目前实现一致。前端为请求身份可对这个仅含 ASCII 字段/数字字符串的有界对象生成排序键、紧凑 JSON，并用浏览器原生 Web Crypto 得 expected rule_id；不引入哈希库，不重算数值/证据身份。冻结 golden 见 §12，实际 Python/Node 规范字节已核对；产品前端实现后仍须将同一 golden 纳入测试。排序使用 ASCII 码点次序，不能使用 localeCompare；不以普通 JSON.stringify 的插入顺序作依据。哈希只是内容身份，不能称来源认证。若安全上下文不支持 Web Crypto，阻止新请求并给明确环境错误，不能静默跳过规则绑定。

响应发布前核对 generation、method/政策版本、D/N、规范 rule 与 expected rule_id、完整排序 inputs、唯一 conditions 与 aN/gN/rN 作用域、成员/来源/共享合同/窗口引用、有限估计、数值文本形状、必备限制和计数结构。允许用计数/引用一致性核验防止损坏响应；不以客户端逻辑重新算一份真假结果。query_id/analysis_id/source_metadata_id 使用服务端身份，仅校验结构和相关引用，不遍历原件再认证。未知协议/缺字段/孤立引用/非法枚举均使整报告失败，不能补默认值恢复入选。

## 6 请求生命周期和错误恢复

状态保持局部且明确：`idle / dirty / loading / ready / error / cancelled`。提交时冻结 requestSpec 与编辑器组映射；结果标题、条件、D/N、成员来自该请求的绑定响应，不能混用尚在编辑的值。

| 事件 | 必须行为 |
|---|---|
| 修改成员、D、N、规则、启用状态 | 立即 invalidate generation、AbortController.abort、清报告/行展开/错误；保留新草稿，进入 dirty，不自动请求 |
| 修改集合显示名称、搜索词、显示类别、展开证据 | 不改变数学请求；不重发、无数据身份升级 |
| 提交、Enter、双击同时触发 | 同步 ref guard 在异步 hash/fetch 前锁住；loading 按钮禁用，最多一个当前有效请求。依赖 React 下一帧 disabled 不足以去重 |
| 请求过程中取消 | 先失效 generation，再 abort；报告清空，草稿保留，进入 cancelled，不弹连接错误。提示“已停止等待，可修改条件后重新运行” |
| 取消后的 owner 工作 | 已被服务端接受的只读计算可能继续；不声称停止 CPU 或撤销入队，不承诺下一次立即完成。重复重试不绕过既有有界 owner 队列 |
| 旧成功、旧失败、旧 finally；A→B→A | 只能当 generation/current requestSpec 同时匹配时改状态；旧请求不得恢复报告、覆盖错误或解锁较新请求 |
| 切工作区、卸载、整页导航 | 失效并取消等待；draft 按 §2.3 保留范围处理。返回不复用旧报告作当前值 |
| 网络中断/HTTP 错误/响应不匹配 | 报告整体清除，草稿保留；安全中文说明和可复制短错误码，用户显式“重试”。不自动循环或回退旧值 |
| 请求慢 | loading 提供可访问状态与取消，无伪造百分比、逐股进度或“即时完成”承诺；不以短超时把最大预算合法计算当坏数据 |

UI 不宣称全服务仅剩一个作业：本地 abort 不取消已入队工作。同步 guard、无自动重发和服务端现有队列上限共同限制误操作；不在本片新建任务管理器。显式重试是新 generation，仍完整核验原件。

错误分流以 当前已核的 API 映射为准，不更改 HTTP 状态：七种规则错误 `invalid_filter_rule/filter_rule_limit/unsupported_filter_field/invalid_filter_operator/invalid_filter_threshold/duplicate_filter_field/duplicate_filter_group` 均为 400；未知或重复 URL 参数是 400 `invalid_request`；既有成员/日期/N/预算与 safe research 参数错误沿用 400；`snapshot_not_found` 是 404，`raw_object_corrupt/raw_object_missing` 等 Store 冲突是 409，未归类计算异常、存储 I/O/数据库错误是受控 500。权限和队列等 HTTP 外壳错误继续沿用既有映射。恢复动作：前端本地参数/阈值/重复规则校验可聚焦具体输入；后端仅有 {error: code}，无法唯一定位时聚焦规则区错误摘要，保留全部输入，不猜测字段路径；重复证券让用户选版本；预算说明完整来源前缀超限，可减少成员或显式调整截止，不能建议只改 N 或静默裁行；source/hash/storage/internal 失败说明整组未完成，并保留重新核验入口。正常的逐成员待核属于成功报告中的证据状态，不能变成全页网络错误。未识别错误使用既有安全回退，不展示响应原文、路径或堆栈。

## 7 视觉和可访问性

复用既有暖纸、墨色、朱砂视觉和 `--serif/--sans/--mono` 字体栈，标题使用现有衬线，正文/表单使用中文系统无衬线，数值 tabular-nums，长身份仅在详情用等宽。无远程字体、无图标库、无新的图表。文字/控件正文 14px，辅助字不低于 13px，行高至少 1.5；避免为塞列缩小字体。

规则用两个简洁 fieldset/legend 表达“全部满足”和“满足任一组”；添加、删除和切换控件均为原生 button，绑定 label/help/error ID。删除当前条件后焦点回到同组下一输入或“添加条件”；删除第二组回到“或，再加一组”。首个提交错误聚焦到具体输入，错误用 aria-describedby/aria-invalid。状态计数用 aria-live=polite，只在成功/取消/错误时更新，不重复播报整张表。按键可到达全部 checkbox、summary、筛选按钮及原始来源入口；状态选择用 aria-pressed，无仅悬浮操作。

宽屏可用一张紧凑表；600px 以下改成每成员一块的纵向信息布局，状态、partial、证券和实际日期在可见主区，数值与原因在紧邻区域。不渲染两份可聚焦的桌面/手机控件；同一数据和按钮只呈现一套语义。长哈希换行，必要的原始精确表允许局部横向滚动并标明用途；320px 宽度无整页横向溢出。200% 缩放不遮挡控件或原因，触控目标至少 40px。真实字体字形、焦点移动、对比度和触屏体验仍需浏览器/设备验收，源码存在 CSS 不能代替实际通过。

## 8 实现边界和测试顺序

### 8.1 拟改动最小集合

- `CrossResearch.tsx`：仅 universe 分支加入有限规则、请求状态与结果；pair 行为保持。规则编辑/结果证据若超过可读长度，拆为小型 `UniverseFilter.tsx`，不抽通用规则平台。
- 新 `filter-model.ts` / `filter-types.ts`：有界请求构建、精确单位字符串变换、专用响应校验及展示标签；复用 Generation、safeCode、既有网络边界。规则身份仅结构规范化，无来源算法。
- `App.tsx`：只提升多股 draft、恢复入口和生命周期传递。`styles.css` 增量沿用当前变量/断点。
- 不直接用旧 `ResearchProvenance` 泛化“全部模型是 float”解释新 Fraction；可加窄专用来源段或给公用组件显式内容参数。禁止强行类型转换后跳过新响应字段校验。
- `research_api.py`/`stock_filters.py` 的接线依赖由 032 作者冻结；本 UI 计划不顺手改数学、政策版本或 Store。确需合同改动先提回算法评审。

### 8.2 先写的合成验收

| 编号 | 必须覆盖与预期 |
|---|---|
| UI01 | 未加条件仍只请求旧 universe；条件模式一次 filter 请求同时展示基线和筛选，展开零额外研究请求 |
| UI02 | 规则 1/2 组、字段去重、空组、重复组、非法十进制/超精度、−0/尾零、UTF-8 2,048 字节和 +1；无效时零 fetch |
| UI03 | M/DD 百分比边界和精确字符串往返，V 不带 %/年化；同 5.00% 两侧结果保持服务端 F/T；零和 null 区分 |
| UI04 | selected+partial、excluded+partial、F OR U、共同 gate U、未启用 V 失败；全部未知/全部排除不误称没有成员 |
| UI05 | canonical group 重排/跨组共享conditions、aN/gN规则内和rN成员内作用域、proof/false/unknown引用映射回正确组；原有集合名次和全组分母不变 |
| UI06 | 错 method、rule_id、政策、D/N、成员、query/source/window引用、非法枚举、非有限数、损坏数值字符串/计数、空window却伪造端点、成功/错误正文512 KiB边界及+1；整报告拒绝 |
| UI07 | 慢 A/快 B、A→B→A、双击/Enter、hash 未完成就编辑、取消后旧成功/错误/finally、卸载后响应；只发布最新绑定结果 |
| UI08 | 错误后保留草稿可显式重试，partial 不是全页错误；原件错误清屏、无旧报告或自动删成员；404 不假装筛选空结果 |
| UI09 | 原因八例+omitted，重复日期 ordinal=null，全部原子可查，实际端点不同、缺D时旧universe末端=D但filter.window四端点字段=null、存在D的短历史仍有窗口；共享合同完全相等才复用、reason元组列定义、来源 known/applicability=unverified/absent/null 和 legacy 限制不丢 |
| UI10 | 搜索不丢已选；切个股再回保留草稿并重跑；目录变化保留失效成员提示；刷新/Back/Forward/bfcache 无旧结果复活 |
| UI11 | SSR 语义结构/中文标签、label/fieldset/summary/aria；桌面与窄屏 CSS 规则；pair/single/导入/导出既有测试不回退 |

使用现有 Node 原生测试、Vite SSR 和 React `renderToStaticMarkup`。请求边界用受控 deferred fetch/原生 AbortController 测试；不新增 jsdom、测试框架或浏览器包。可测试模型、静态 DOM 结构和组件输出；它们不证明 React 点击绑定、真实 layout、焦点、可访问树或浏览器历史。当前依赖不足以执行的真实交互项标未跑，不以静态字符串断言填绿。

冻结源码后执行并逐项记录：`(cd web && node --test tests/*.test.mjs)`、`(cd web && npm run build)`（含 TypeScript 检查）、受影响 Python API/universe/filter 测试、独立反方和最终协调后的全仓回归。前端 SSR 的 Vite 根目录为 web，命令须在此目录运行。具体 Python 集合以 032 实现冻结清单为准，旧 golden 不更新为新值掩盖回退。库外真实矩阵对相同 response 的来源、阈值、守恒和错误逐项核对；合成 UI fixture 不替代真实行情资格。

## 9 验收状态和停止条件

### 9.1 当前真实浏览器边界

[既有浏览器报告](../qualification/research-browser.md) 记录：云 CDP 无法连通本地回环服务；同一执行调用中服务可达，但 Chromium 在创建页面前因 `socket() failed: Operation not permitted` 中止，受支持提权重试也被同样拒绝。本片不再次试安全绕过，不修改系统安全设置、不公开部署或把私有行情传到另一个站点。

因此当前可先完成并报告代码/模型/组件静态结构、TS/build、API 及离线来源核对；**真实浏览器点击、取消、键盘焦点、页面恢复、字体/留白、320/375px 窄屏、200% 缩放和截图全部仍未验**。已有用户本地测试授权不会消除环境权限拒绝。只有在受支持且可运行浏览器、可连同源服务的环境实际可用后，再按 UI01–UI11 补交互矩阵与截图；不要求用户重复同一授权，不更换路径绕过已拒绝的动作。

### 9.2 允许进入编码的条件

1. [独立评审](../reviews/2026-10-11-research-ui-review.md)初审的 R1/R2 关闭，且实读本计划与最新 032 候选响应，确认字段、三态/partial、精确阈值表示、请求取消和来源语义无冲突，记录批准及逐项回复。
2. 032 API 的正常/安全错误合同冻结，独立实现审查关闭阻断；UI 模型合成测试可在批准后先写，实际接线以冻结响应为准。API 不可用时不发布假入口。
3. 所有改动只在本片范围；新增协议/算法选择重新复核。真实浏览器受限不封死纯函数/API/静态界面开发，也不能将 UI 端到端标完成。

### 9.3 用户价值验收

沿用 032 的八个配对复核任务与 B0 原集合表基线，覆盖 OR、缺截止、日期未知、阈值临界、不同起点、回撤负号、数值失败、全未知。冻结正确答案后交错任务次序，记录学习效应和每项失败；先用合成，再用获准的库外固定来源样本。真实用户未作答时记未验，开发者自行读懂界面不能替代。

入选/排除/待核及关键原因须全对；不得出现将未知当确定值、来源步当交易日、来源变化当可成交收益的重大误读。个人试点中位复核时间较 B0 至少减 20%，最慢任务不得因找不到原因显著恶化；达不到则收窄至单组条件/现有排序，不继续堆 OR 配置。该指标沿用 032 的预定个人任务门槛，不代表普遍效果、预测收益或超越 TradingView。

实际状态：初稿只新增计划；05:49 UTC 在 [复审 §7](../reviews/2026-10-11-research-ui-review.md) 批准后开始 web 与合成测试实现，未自行提交/推送。06:17 UTC 后端资源观察结束后恢复执行，最终全 Node 128 passed / 0 failed / 0 skipped，TS/build 通过；独立 15 类实际 Python→TS 合成响应接线亦通过，详见[本片资格记录](../qualification/research-filter-ui.md)。独立代码复审 §8 已通过，代码层无剩余阻断。真实浏览器、Windows、用户任务与预测/交易效果分别待验；后端 RSS 资格仍未通过，本片不改变该结论。

## 10 030 后续同行入口的保留边界

待本片闭环后，再独立设计“同起止日比较”：从**原完整组**选一个目标，明确 a/b，显示目标来源变化、剔除目标后的同伴中位数/均值、两种百分点差、严格异号、固定/有效分母及逐成员端点。筛选入选子集不能无提示替换原同行组；换组须成为新显式成员版本。科创板仍叫上市板块选定样本，不包装成行业。

后续 adapter 必须加载 030 要求的完整未裁剪 Store 查询，不能复用 032 的 cutoff=D 前缀；4–50 成员、每股 20,000/总 200,000 行及 descriptor 16 KiB 预算先检。descriptor 的 selection_date、group_axis、scope 的 declared/assumed/证据来源由真实用户输入或已存在可追溯组记录提供，不能从名称或 CN_A 自动造齐。需要另审准确 HTTP 输入/返回协议，本片不预先指定或实现一个未经审查的路由。

结果沿现有纯函数精确 Fraction/ratio/percentage_point、`source_price_comparison_only | diagnostic_only | unavailable` 三态；全组比较因任一成员不合格而为空时不删同伴重算。保留未知来源语义下的来源算术、已知停牌/公司行动诊断与已知冲突拒绝，不把 032 的 gate 套给 030，也不把 030 的局部端点规则放宽到 032 完整窗口。只有同行 API、descriptor 来源、响应绑定与真实界面各自获审并验证后，才开放入口。

## 11 独立初审答复

依据 [UI 初审](../reviews/2026-10-11-research-ui-review.md)，05:34 UTC 修订如下；作者答复不替代 reviewer 关闭决定。

- R1 接受：§2.2/§5.2 明确条件列表及证据只读 member.window 实际端点，旧 universe 仅供基线与排序；缺 D 保留请求日期且实际窗口为空，短历史保留实有窗口。UI06/UI09 加对应正反 fixture。032 I1 修复已在候选代码见到，等待实现 reviewer 复验。
- R2 接受：032 §6.2 已同步 `{canonical_rule,policy_versions}`；§12 的两组、共享原子、尾零/负零合成 golden 已完成 Python/Node 字节及哈希核对。05:45 UTC 作者确认最终去重 schema 后，§5.2 同步 root conditions/shared contracts、aN/gN/rN作用域和reason二元组。政策集合不变，477字节 golden 保持有效；等待本 reviewer 复核。
- 实施说明 1 接受：本地错误聚焦具体输入，后端无法定位的错误聚焦规则摘要，不新增字段路径协议。
- 实施说明 2 接受：512 KiB 同时约束成功/错误响应的读取和解析；新端点窄封装先限流读取，不经过旧 checkedFetch 的无界错误解析。旧端点保持。

上述答复已由 UI 复审关闭，后端 schema/I1 独立实现复验完成；05:49 UTC 开始最小 web 编码。后续实际测试与独立实现检查另记，不回填为本次设计评审已验证。

## 12 R2 跨语言身份 golden

032 §6.2 已同步为 `{canonical_rule,policy_versions}`。以下固定合成输入在 05:36 UTC 用 Python 实际 normalize_rule/_json/_identity 与独立 Node 十进制字符串规范化、递归排序键及原生 Web Crypto 验证；未写产品或测试文件，也未启动浏览器。05:45 UTC 作者确认最终响应去重结构及规则政策集合保持不变，本 golden 继续有效。

原编辑顺序：第 1 组为 volatility ≤ `0.0200` 且 momentum ≥ `-0.00`；第 2 组为 max_drawdown ≥ `-0.1000` 且 momentum ≥ `0.00`。规范组顺序反转，momentum 条件共享；UI 必须映射回原编辑组的名称。

以下代码块内单行内容为确切规范 JSON。UTF-8/ASCII，共 477 字节，不含 BOM、首尾空白或末尾换行；数组保持规范顺序，键递归按 ASCII 排序，紧凑逗号/冒号：

```json
{"canonical_rule":{"any_of":[{"all_of":[{"field":"max_drawdown","op":"gte","threshold":"-0.1"},{"field":"momentum","op":"gte","threshold":"0"}]},{"all_of":[{"field":"momentum","op":"gte","threshold":"0"},{"field":"volatility","op":"lte","threshold":"0.02"}]}]},"policy_versions":{"comparison":"fraction-and-binary64-v1","logic":"strong-kleene-eager-v1","rule_schema":"bounded-price-filter-v1","source_gate":"source-date-locatability-v1","window":"daily-source-date-groups-v1"}}
```

SHA-256 rule_id：`ed05c4aef00f6130eda8d84f5046cecb2734e9059469be4fd481bb0b4c64272d`。

实际探针通过：Python 与 Node bytes/hash 完全相同；输入组/原子反序、尾零/负零规范化后同 ID；阈值变化、window 政策版本变化均得到不同 ID。这里只验证有界内容身份及序列化；真实浏览器 Web Crypto、后续 UI 模型和组件代码仍未执行。这些代码实现后必须再次通过同一 golden，不能用这次文档探针替代。
