# 共同端点单组入口：最小工程方案

2026-10-12 UTC。状态：经独立反方审查与范围准入进入限定实现。下文保留编码前契约；实际结果见[验收记录](../qualification/group-endpoints.md)。

## 1. 用户新增能完成的任务与范围

在现有“多股研究”选择器中，勾选一个明确的 **4–50 个数据版本单组**，选共同日线日期 a<b，不需 A/B 分组、目标股或训练历史，即可看到：原组 N、有效端点 K、每个原成员的源收盘变化/失败原因、精确正/零/负数、完整组的均值/中位数/Q1/Q3，并回查原端点。仅两日期的合格源记录即可完成描述。

这补上一般明确版本名单的可达性；020已经能做的通达信固定池后续观察继续使用020。不新设导航工作区、平台、模型、图表、排序评分、贡献/集中度/删留功能、采集、预测或性能实验；不改旧 Universe 的 lookback 语义，不改043，不声称效率或金融效果已验。4–50沿本轮批准的030范围，4的下限只属首片工程限制。

## 2. 已核代码与边界

- 已读根 AGENTS.md；本checkout无 .agents 目录、未找到仓库 SKILL.md。
- 静读030研究/实施/评审、020研究与 daily_followup.py、UniverseResearch/universe-request、043模块/API/前端，以及 Store._research_query 的源码；没有调用Store、读行情文件或旧DB。
- 当前 HEAD 89db7c0edf36e1cb34b035ee6d86658aa28527db；tree 547bf49da95a35cbe03cc8b8b12a2359c578700b 等于 origin/main e06d75986a39f22371a277893f679d3c1e464441 的tree；开始时工作树干净。442文件与主方基线逐项SHA-256一致、tracked集合一致（本轮静态重新核验）；本计划不把旧全套测试记录当本轮证据。
- 已读同目录 research.md 最终“最小验收约定”（SHA-256 d439f35392d9909699c8006099f6beca583e67f2418fba9348a3e64a249f1bd6）及 independent-review.md；研究审查的完整来源查询与不完整组四统计全null两项修订已落实。两日期记录足够仅指完整原来源本来可短，不准手工裁两行。

## 3. 唯一来源资格，保持030原义

复用 peer_relative_research._source 的完整资格：完整、可信 Store query 或 daily_ohlc_input_v1；retrospective且cutoff/ordinal均空；原件仍由Store逐请求核验；snapshot/batch/query/manifest/selection/counts/ordinal对应。仅腾讯 tencent-daily-capture-v1、version=1、既有strict/legacy capture、day分支、requested_period/period=1d、requested_adjustment=none；范围A股/CNY/中国日线日期仍标 assumed，不凭SH/SZ认证资产或币种。已知身份、调整、结构、范围反证不进入算术。

源资格与端点复用方案：

1. _source 不修改行为、参数、错误顺序或允许清单。仅把其已有header/IDs/selection、counts、rows/ordinals/checks结构段机械提取为少量同模块helpers，原_source在原位置按原顺序调用；原030、043来源路径保持原样。新入口在捕获来源拒绝之前先完成这些结构段、batch_checks形状及_source实际使用的contract.source_semantics/fields容器形状核验，再调用_source。semantics提取只需读取fields与单field两个极小helper，旧_source仍在原位置/循环内调用，保留既有source_semantics非dict→{}行为和先price_unit语义后adjustment形状的优先级；新入口只预检其实际使用的形状，不判值或猜缺字段。另仅在新入口检查metadata.interpretation若存在须dict（缺失沿默认{}），异常归invalid_query；原_source的身份错误映射/顺序不改，不递归metadata。不能因_source早报unsupported_source/known_negative等就跳过晚段结构检查；同时包含拒绝源与坏counts/ordinal的输入必须整请求失败。预检仅复用必要结构，不重算Store哈希链、不遍历任意嵌套metadata、不修复030/043其他问题。
2. 将 _member 的无目标依赖部分原样提取为同模块的 `_endpoint_member(query, identity, a, b, events)`；旧 _member 调它后添加原target/peer role，确保原报告逐字典相等。新单组直接用无目标核心，绝不虚构target调用peer_relative_report或使用N−1。
3. 日期定位、无法定位、重复端点、正且完整OHLC、token/精确值、DECIMAL范围、局部冲突/未知check与异常作用域继续复用原核心；不换成020的close-only口径，末价0在本入口无效，不借020允许0扩大资格。量额失败继续按030处理。
4. 每个有效来源单次调用端点核心；区间内部正常记录不要求相邻，可靠定位在区间外的数值异常保留披露但沿030不阻断端点；日期未知/区间内身份或未分类反证阻断。无需60区间或取日期交集。
5. 已知事件处理不另发明规则：从原 _descriptor 中机械提取小型事件校验段为 `_events(events, identities, a, b)`，旧_descriptor仍执行原成员/target检查并调用同一校验。新纯函数先调用原_auxiliary(events)检查16KiB/深度/节点/类型预算，再调用同一事件校验；不能把原_descriptor未自带_auxiliary误当已有预算。可接同结构events；停牌/公司行动原诊断不消失。HTTP首片与043当前路由一致不接受事件附件，传空列表并显式保留“公司行动覆盖未知、未提供事件附件”；不读取外部研究文件或自动推断事件。若后续需要把既有事件附件接入UI，另审最小事件输入范围；不能声称该入口已核对它们。

结构性/可信边界错误（invalid_query、invalid_counts、invalid_selection、full_query_required、invalid_source_id、source_identity_mismatch、invalid_source_ordinal、invalid_source_checks等）整请求失败，不将伪造DTO降级成普通缺失。

仅既有非结构来源拒绝码（known_negative_source、source_identity_conflict、source_adjustment_conflict、source_structure_failed、unsupported_source_check、scope_conflict、unsupported_source、unsupported_period）可形成保留行：记录snapshot/batch/query、空变化与原码，不扫描其行作算术。显示身份单独经既有symbol_identity核对；若原拒绝码为source_identity_conflict或解析失败，强制symbol=null、以完整数据版本定位，即使单独解析出source_code也不回退为无冲突身份；不拿未核metadata作认证身份。已解析且无冲突的重复证券整请求拒绝；未解析身份行始终K外。重复snapshot亦整请求拒绝；不悄悄去重或删除。

## 4. 算术与输出合同

在 peer_relative_research.py 增加一个独立入口 `group_endpoint_report(queries, start_date, end_date, *, events=None)`，保持同模块、少量专用代码；没有通用注册表、可插拔资格或新引擎。METHOD固定为explicit-group-source-endpoints-v1；RULE固定为peer-eligibility-complete-group-type7-v1，明确source-close-ratio、030资格版本peer-relative-eligibility-v1和complete-group分母政策。

- N=提交原成员数，K=source_change非空行数；missing=N−K。每个原成员必有一个结果行，来源/端点诊断不能被摘要覆盖。全组按snapshot_id稳定排列，报告身份对输入重排不变。
- r=C(b)/C(a)−1，用Fraction。精确符号按r比较；A+ + A0 + A−=K。coverage=K/N；正/零/负比例为A/K并显著标“有效K中的比例”；K=0时三比例均null、计数仍为0。
- 冻结 **完整组分布政策**：仅K=N时返回mean、median、Q1、Q3；否则四值null，原因incomplete_group。即便K=N−1且全正，也不显示原组“全部上涨”。本片不自动生成多数、普涨、驱动等结论标签。
- mean=sum(r)/N；偶数中位数取中间两值均值。Type7按h=(N−1)p、p=1/4,1/2,3/4精确插值。020原有Type7已经覆盖此算术；此处共享定义及独立手算测试，不为跨来源复用而导入它的原生缓存采集链。仅加一个小型专用分位数辅助函数（无外部库）。
- JSON仅返回约分分子/正分母整数字符串、unit=ratio；零0/1。不返回float副本。服务端继承decimal_value价格界限。每个合法正价格乘10^18为1..10^38−1的整数，单行r分子绝对值/正分母最多38位，50行mean可保守限于2000十进制位以内。汇总分数可超过单行256位；单个整数传输文本上限4096字符，先做长度检查，超界受控失败，不改Python整数安全设置。
- 每行：snapshot_id/batch_id/query_id、可核symbol或null、source资格/evaluation状态、两端日期/ordinal/close_token/close_exact/端点reasons、source_change或null、全部已执行检查产生的本行失效原因、异常总数/各码计数/前20例/是否截断。来源拒绝行evaluation=not_evaluated、endpoints=null、anomalies=null、source_change=null，显示首个来源拒绝码；未执行端点/异常检查，不得标missing_endpoint、0异常或全部原因已穷尽。端点核心完整异常只在内存内压为有界输出，不能只取20例就决定资格。诊断事件不删源值，状态必须显示diagnostic_only；缺失与诊断并存仍优先不可算。
- 组级包含parameters(a,b)、规范来源引用、scope assumed、events、N/K/缺失与符号/比例/分布、method/rule/analysis_id、固定限制。analysis_id用现有canonical JSON+SHA256，绑定完整source IDs/规则/日期/scope/events/分母政策；显示组名不入身份，不假定a/b是成员选择日。
- 常驻限制：current_members_retrospective、来源经济语义/复权/known_at/公司行动覆盖/日历/闭合未核；相邻交易日未保证；等权源价格均值没有投资组合/行业指数/总回报/风险/预测资格。

## 5. API：有界、只读、单次请求

在现有 research_api.register_research_routes 增加GET `/api/research/group-endpoints?snapshot_ids=...&start_date=...&end_date=...`。仍用owner线程、parse_parameters、safe_store_call和既有错误映射；不改Store schema/导入/查询/写锁/导出。

- 校验未知/重复参数、字符串长度、4–50不同合法snapshot ID、严格日期a<b，再进Store。排序IDs固定身份。
- 使用现有 `_research_budget(store, ids, None, error)` 对所有完整来源先计数（每股≤20,000，总≤200,000），然后逐股 `_research_query(sid, cutoff=None)`，每次验证原件。不可调用带cutoff=b的旧Universe路径，不用其完整日线列表先行全局period异常覆盖成员记录。
- 本入口加载不复用 `_load` 的全请求period拒绝；直接复用其预算/精简查询两步，让period来源拒绝由上述源资格保留行明确承接。原件损坏/消失/Store失败仍整请求失败，不在结果中假装普通缺一只。
- 结果序列化前限制2MiB，沿043已有量级；超限返回group_result_limit，不能丢成员/缩分母/只返回首屏。参数、budget拒绝在加载前；结构边界异常受控失败，不返回原始异常路径。
- 请求不会采集或持久化分析。客户端取消只停止等待，服务端已开始的只读核验可能完成。失败后保留输入并明确重试，不转到Universe/043/020或沿用旧报告。

## 6. UI与生命周期，复用当前路径

沿用 UniverseResearch 的选择/搜索/成员详情、App持有draft、ResearchRequestController和universe-request单路由分派。研究方式加一个group_endpoints值；只在原分派处作必要扩展。若采用existing/explanation/group_endpoints明确枚举，须机械迁移既有explanation.enabled、createUniverseDraft及测试fixture，旧两模式的初始化、日期、roles、filter草稿与返回行为均保留；不顺带重构控制器或全部draft。不得出现两个enabled开关互相矛盾的状态。

- 新模式只显示共同起点a、共用终点b和显示组名；不显示lookback/筛选阈值/A-B roles/target。入口文字明确仅支持已核腾讯日线，4–50；选择器不自动删除当前不支持来源，也不伪称全日线都合格。
- 4–50且可用版本才可提交，客户端严格日期验证定位起点/终点；源资格最终以服务端为准。改变日期/成员/模式立即清旧结果和旧错误并取消等待，重复提交只有一个有效请求；搜索/改显示名称不改变算术身份。离开工作区、pagehide/bfcache restore、unmount沿原控制器失效；返回保留draft但须重跑。不以迟到fetch/hash结果覆盖新输入。
- 新 `GroupEndpointResults.tsx`只是现有多股页的一块结果：共同日期、N/K/N−K、精确符号数、有效占比、完整组四统计；全体≤50行无分页，失效行与原因始终保留。采用现有panel/table/details/CSS，不建重复工作台。无新增筛选/排序控件。失败文案使用本功能的源价比值语义，不能照搬043的“对数/模型解释”错误文字。
- 独立小型 `group-endpoint-model.ts`负责本DTO类型/请求/严格验证/本地BigInt格式化。复用canonicalJson/jsonRequest。验证method/rule/成员集合与顺序、日期、源ID形状、端点、有限原因枚举、事件、counts、null政策、分数约分与精确恒等式；先限长并验证两端close_exact为DECIMAL(38,18)正值，用BigInt从端点重算≤38位行分数并与响应对比，然后只累计这些受约束的派生值核对计数/比例/mean/Type7；不能把50个任意4096位响应分数直接累加。另核对analysis_id，核验跨请求成员/日期及内部算术一致性；analysis_id绑定来源引用，不是端点载荷签名，不能凭客户端复算独立认证合法ordinal/token确属该原件。原件归属仍依可信Store逐请求核验；不增加逐行远端请求。close_token只限长/类型并原样显示，不加小数格式新限制，科学计数等旧资格允许的token继续保留；复算只用规范close_exact。不用Number来决定符号、次序或比值。
- 百分比显示4位、整数半偶舍入；零与微小正/负分开显示精确符号标签，舍入到0时明确“正/负，显示舍入”，不把非零归零。详情保留完整分数与两端close token/exact、ordinal、snapshot/batch/query。
- 首片原始回查冻结为现有onOpen(id, cutoff)，分别提供“打开此版本至起点日期”“打开此版本至终点日期”，当前结果直接展开两端精确close/token/ordinal。回查打开对应snapshot至该日期的查询；不宣称自动聚焦原行，不加App/CrossResearch的ordinal链。完整来源query_id与回查前缀query_id属于不同selection，界面不得假称二者相同。缺失端点也可打开该日期前缀核查，但没有最近值替代本报告的缺失。

## 7. 验收计划（准入后执行，当前全部未跑）

仅使用纯合成DTO与 **新tmp_path EvidenceStore**，现有fixture的capture→decoder→新Store过程可复用。禁止读取旧DB/真实Store；不以合成数据替代真实来源兼容。

1. 纯算术：研究A/B五成员案例、正零负/全0/净零、奇偶中位数、Type7插值、极小±值、大精确分数；独立手算期望，不引用被测helper产生答案。覆盖N=4/50、K=0/1/N−1/N和每只失效位置。
2. 资格反例先写：缺a但有前日、缺b但有后日、重复端点、未定位日期、错token、无open/低高关系/0负非有限越界价格、批/行身份复权冲突、已知负样本、未知check、unsupported source/period、重复证券版本；所有失效成员/原因与N保留，结构伪造整请求失败。已知halt/corporate events保留诊断；source_change不能让invalid成员复活。
3. 旧行为保护：原030/_source/_member/_descriptor（含事件）的返回、异常和检查顺序保持；043既有相关回归。增加同一DTO同时含多个错误的原030/043差分回归；新入口中unsupported_source/known_negative等与坏counts/ordinal/checks/semantics容器并存时必须结构错误整请求失败，不能留行。输入不变、重排不变、每股正数缩放不变、可靠b后价格追加/更改数值不变；完整源IDs变化可改变analysis_id。日期未知/批级反证不伪称前缀不变。
4. API：合成capture→新Store→HTTP→精确报告、同版本a/b前缀回查与报告端点对账；预算/日期/非法参数在任何加载前拒绝；逐请求原件损坏/缺失→错误→修复后显式重试；确认来源投影与公开query资格/数值等价；全部原成员保留、输出2MiB拒绝受控。不触及真实Store。
5. JS模型：黄金DTO，以及破坏跨请求身份/日期/成员、端点结构、计数/比例/分数恒等式、summary/null/events/hash的负例；自洽伪造合法ordinal/token不能由客户端单独认证，保持可信Store边界，不声称这类篡改均可检出。原token科学计数等旧格式原样保留，不另限语法；4096边界先限长后BigInt；微小正/负与显示舍入分离；跨Python/JS固定身份与精确分数一致。
6. 实际组件使用的prepare/load/controller路径：三模式只选一个endpoint，模式切换、重复点击、取消、迟到成功/错误、hash等待中编辑、unavailable成员、卸载/返回、失败后重试。SSR检查输入控件、N/K/全部失效行/符号标签/两个回查目标及限制文案。SSR和纯控制器测试不冒充浏览器React挂载/键盘/视觉。
7. 最终受影响测试：新tests/test_group_endpoint_research.py与API用例，旧peer/peer-adversarial/two_group/universe/research_api；新JS model/interface与universe-request、two-group、research-interface、语言检查；所有Node与TS/Vite构建；最终合成范围Python回归。全tests包含条件读取私有真实fixture的用例，因此先静态列清并显式排除真实fixture/旧Store读取用例或文件，不能依赖“文件大概不存在所以会skip”；不访问私有路径确认是否存在。报告被排除项并明确不能称未过滤全套。实施时记录实际commit、命令、通过/失败/跳过/未跑，不能使用旧3218/49和214通过数字。
8. 新浏览器、真实行情、Windows原生、性能、真人效率、预测/收益全部明确未验；本轮浏览器禁止不尝试、不绕过。

## 8. 复杂度、文件预算与错误恢复

N≤50，R≤200,000。加载与_source扫描O(R)，新入口增加一次必要的有界结构扫描；原_member异常稳定排序最坏O(ΣRi log Ri)，单组统计O(N log N)，有理数代价取决于有界整数位数；不宣称严格O(R)或性能提升。内存为完整既有投影O(R)、当前成员完整异常及O(N×20)输出；不建N×T训练面板、不复制全部原文。预检预算、整数界与2MiB都是防无界输入，不是本轮性能实验。

预计产品改动局限：peer_relative_research.py（结构/端点/事件的小范围机械提取+单组摘要）、research_api.py、universe-request.ts、UniverseResearch.tsx、GroupEndpointResults.tsx、group-endpoint-model.ts；不扩App/CrossResearch回查签名。Store/formatter来源资格、package*.json/lock、pyproject依赖、020与043实现不改。另补docs/research、plan/review/qualification与README/研究状态的最小准确链接；不宣称新算法。

恢复：失败不写库不改名单；保留draft，旧报告清空，用户更正日期/成员或恢复原件后显式重试；不静默自动重试、不换来源、不填价、不删坏行。代码若使原资格/旧报告改变，回退该局部抽取并重审，不给已有测试改期望来迎合实现。

## 9. 失败停止点与准入门槛

- 先独立反方审本方案，逐项答复并修订；主方明确确认后才改仓库。编码前先提交限定research合同与审查决定到拟修改工作树，再写产品。此处“提交”指写入候选文件，git提交/推送由主方后续统一安排。
- 未能保持030原来源/端点资格、不能在失效时保留N/成员/原因、BigInt/DTO不能清楚绑定原端点、回查定义仍含糊，停在方案，不能以可运行绕过。
- 若被迫新依赖/凭据/权限/采集/真实Store/浏览器或显著改Store，停止依赖部分并向主方报告，不换路线绕过拒绝。
- 受影响测试有失败先诊断修复；不能复现或恢复需扩大权限时报告具体阻断。测试通过只获得有限工程证据，不补填浏览器/真实/效果状态。
- 若独审发现此输入任务已可由既有入口等价完成，停止重复实现；目前静读明确020受固定池约束、Universe异起点、043两组且训练形态，均不能直接接此单组两端点任务。

## 10. 独立审查与决定记录

已由独立反方静读提出下列实质修订，作者全部采纳并修订对应正文，最终回读已接受：

- R1：_source先资格拒绝会跳过后续结构检查。增加新入口完整必要结构预检；机械提取原段并保持原_source检查位置/顺序，增加多错误差分回归。
- R2：未检查的拒绝源不能伪报missing_endpoint或零异常；明确not_evaluated及null端点/异常，保留首个源拒绝码；身份冲突强制null，不用单独可解析代码洗成无冲突。
- R3：events须在新入口自行调用_auxiliary预算，再复用原事件段；保留HTTP未接事件附件与覆盖未知，不引入事件管理器。
- R4：4096只是传输上限。客户端先验证DECIMAL端点，再从端点重算≤38位行分数并汇总；50行均值保守<2000位，不直接累加任意4096位响应值。
- R5：回查验收只称同版本a/b前缀对账；客户端内部恒等式验证不冒充原件归属认证，原token语法资格维持服务端既有规则，客户端原样披露。
- 主方收窄：回查只用原onOpen(id,date)，结果内保留精确原端点，不扩App/CrossResearch；模式变更不顺带重构。
- 作者静态自查：旧测试含条件私有fixture读取。最终回归先显式排除全部此类用例/文件，不能靠不存在假设；未过滤全套保持未跑。

实质审查见[设计决定](../reviews/2026-10-12-group-endpoints-design.md)。此审查状态不等于代码实现或测试通过，也不代替主方范围批准。
