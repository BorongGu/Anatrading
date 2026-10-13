# 单事件 h=5 六槽设计：独立反方审查

2026-10-13 UTC。固定源码：`70f68ef1dcb33fe45e895b01ea8861446d648bc9`。

## 决定

**最终 GO（r2静态复核）；R1–R3均已关闭，可由母任务授予本设计范围内的编码准入。** 已采用“小型独占投影＋已发布报告只读拥有合同＋每次接受新令牌”，已删除整响应两遍冻结、新节点/字符总预算和任意 JavaScript 对象图防护。正文、概念卡、矩阵已同步，两类卡片矛盾已修正；最终文件哈希与关闭证据见§7。此结论没有宣称产品、性能或运行验收通过。

实际产品范围维持：当前已接受单股 h=5、现有最近100事件入口、一次一条固定六槽、只读同响应、精确字符串、原标签/评价/分段归属；零新请求、零源回查 callback、零新价格算术、零后端/统计修改。B1没有现成组件完成相同绑定任务，暂不替代C。

## 1. 输入冻结与核读

读取并核对设计作者提交后的最终 SHA256：

- design.md：`b6cdf8ee9b03bc5598361cb062aa3522d9971abd41025f2735a132d8d3c6acab`
- fixtures.json：`ab6f00301a945426d292945e1f124a47cc32f843721b97c24c6641740940d054`
- expected-answers.md：`090e83821d2a7bdaddb5b614b2086a9ff00032266dc81939729974062020032d`

已读前次 event-path-workflow-review 报告。源码以 git show 核读根 AGENTS、event_study.py、research_series.py、numeric.py、signal_research.py、SingleResearch.tsx、research-model.ts、group-endpoint-model.ts、adjacent-source.ts、ResearchResults.tsx，定向核查 App 接受/失效接线与 research_api 的 envelope 身份。没有读取 Store 实现、数据库或行情文件，没有请求行情、运行产品/测试/模拟/浏览器、改仓库或公开评论。命令仅用于读文本、核对文件哈希和写本报告。

## 2. 必须修订 R1：收敛为最小支持合同

### 裁决依据

analysis_id由 method/inputs/parameters 得出，result不进入身份；任何新响应都必须清旧选择。SingleResearch获得新 JSON 后先执行现行 validator，然后 setReport/onReport；当前下游接线保存/读取报告，adjacentSource返回引用供读取，ResearchProvenance读取/序列化，EstimatePlot接收map生成的投影。未发现产品需要对已发布报告原地更新。对没有实际 mutator 的所有未来恶意写入做运行时阻止，不构成本功能准入要求。

整树freeze并非逻辑错误，但会改变共享对象的运行时可写性、扫描所有未知附加字段，并新设未经校准的2,000,000节点/32,000,000字符门槛。它扩大影响面，却不增加本次六槽阅读任务所需的信息。拒绝该成本选择，不要求测完它才允许缩减。

### 唯一合同应写明

1. 接受入口仅处理 jsonRequest 解析的JSON和可信测试构造的JSON数据；原 validator不变。h≠5无新捕获/账本关系工作。
2. SingleResearch发布后拥有只读报告；现有消费者及本功能不得原地写 report。更新必须完整重新接受。此约定可用局部只读接口/注释表达，不要求全仓库Readonly迁移。
3. 每一次成功接受生成全新本地acceptToken并清E，包括同analysis_id、内容相同、甚至同一对象被再次提交。Generation、report实例、当前query上下文共同拦截旧响应/点击。不能用useEffect([analysis_id])替代。
4. 点击时同步校验并复制固定身份、参数标量、事件字段和最多六槽的显示字段，保存为本功能独占投影。投影不持有raw event/series行引用；冻结其所有自身容器与六个槽对象，避免“只冻结外壳”的假保证。只读字符串/数值无深层外部别名。
5. E绑定acceptToken；当前train/test仅决定说明，说明使用已捕获原partition/selected/evaluation与当前实际分段。原表/统计继续消费同一次接受且按合同不变的报告，无须改造两套数据路径。
6. 强制转换后原地改raw report属于不支持操作；小投影本身不变，但不能承诺原表与投影在这种违规操作后仍一致。未来增加原地更新需求必须先改合同/实现，不能悄悄破例。
7. 只保留有界账本关系扫描和点击时最多六槽校验/捕获。无整树freeze、JSON.stringify快照、内容hash、逐render全报告比对、新worker或新总预算。不声称消除了原safeJson/响应解析的既有资源局限。

正文§2.2、§4.1、§4.3、§5接受流程、§6改动位置、§7攻击清单、§8索引都须与之同步。矩阵B02改为独占投影防变异；B03去掉“冻结原对象”；C03保留既有validator边界并删除新预算；C04收窄入口而不承担getter/代理任意对象防护；C05改为一遍关系扫描＋最多六槽捕获；D02检查支持操作不改原报告值，不再改变原报告描述符；D04改为既有只读消费者回归。P7_SAME_OBJECT_MUTATION须同步修改，或移到清晰标明“不支持”的说明组。不能仅追加一段让正文与矩阵继续矛盾。

## 3. 必须修订 R2：重叠卡目前后端不可达

P5_OVERLAP及P5_OVERLAP_PURGE继承 common.event.index=20、lookback=20。event_report在index<lookback时history_insufficient，不可能产生事件；index=20是第一个可计算起点。因此此时不可能已有更早的selected事件，selected=false/overlap_excluded无法由该后端产生。卡里的“完整账本补更早selected事件”不能修复这个索引矛盾。

这些卡应作为正常重叠正例，故建议把目标事件移至index≥21（同步说明series窗口位置和前置组数），明确更早选中事件index≥20，且目标index≤前一selected.index+5。合成前缀须保证两个事件均有有效此前高点与突破条件，前一selected可在目标前一天，价格/高点可选为小于目标100以保持两次突破。完整化时必须补双方及其他真实产生事件的账本/分段/计数，不能只手造selected标志假装检测器可达。不必现在运行检测器或生成完整DTO。

若选择保留原index20，则须把它归类为“检测器不可达/畸形输入”，不能再让A05用它证明正常重叠路径可验收；另须有一个可达正例覆盖重叠优先于purge。建议修正正例，避免测试缺口。

## 4. 必须修订 R3：估计重置与概念卡分类

P3_BAD、P4_DUP/ZERO/NEGATIVE/OHLC、P5_INVALID_PURGE在t2无效后，t3起估计重新初始化，余下t3..t5至多3次观察，status必须warming_up，不能继承slot_default_status=computed。KALMAN_ONLY_FAILURE同样使下一有效槽重新warming_up。t2故障本身可以与事件label valid分离；未证明正常有界价格必然触发该Kalman故障，不把纸面故障注入当自然出现的数值案例。

要求：为相关卡补明确t3..t5（或已存在部分）的warming_up/null reason覆盖；或明确删除未承诺的状态默认，说明完整化时按源规则补齐。并为卡组清楚区分：

- 可由完整合法合成OHLC/前缀实现的正常内容正例（仍未执行/未通过validator）；
- 估计故障注入的合同案例，不声称已证明自然数值可达；
- M01–M12等故意矛盾负例，按门一/门二预期拒绝；
- 单纯词法或结构上限的孤立边界输入，非后端正常报告。

现有总声明“不完整、未证明kernel可达”有用，但不能让所有固定computed值在补DTO时原样留下。完整化不得靠强制类型断言掩盖这些矛盾。20,000事件与20,000槽不可同时成为lookback≥2的正常报告；C01已经承认异常输入，这点保留。

## 5. 其余实质审查结果

### 价格、槽序与来源

DECIMAL(38,18)规范与现有price词法吻合：最多20整数位/18小数位，小数末位非0，负号可有，-0禁止，0允许。带负号最大40字符。仅规范比较/正性检查，不需要BigInt、Decimal计算、百分比或大小排序。保留0/负数用于invalid/immature证据；valid窗口要求正close是必要条件。存在槽null与未出现槽未知分开，原index+i切片，重复日期组占一个槽，无ordinal加法、过滤坏点或日历补齐。

start_close必为正符合后端真实事件起点必须来源有效且突破的规则。成熟end_close可以null/非正且保留invalid；不应仅检查valid端点或丢失这些坏终点。原valid六槽正价、唯一ordinal、无明确来源失败reason只是必要一致性检查，不能重新认证完整OHLC。numerical_failure来自估计层时不改变label/evaluation；后续breakout_reason的history问题不可替代本窗口资格。未知reason下局部不可用属于保守兼容策略，不得重写原标签。

### 状态、统计及分段

成熟度先按i+5存在与否：已有坏槽且窗口未齐仍immature。selected=false的evaluation永远overlap_excluded；selected=true且train成熟终点≥切点时purged，可覆盖invalid；无终点的immature不能purge。设计与event_report一致。

无test_start实际显示descriptive；有切点按当前train/test；某valid train事件不能声称进入test统计。只做原账本归属与计数一致性比较是允许的，能够支持“按原响应计入有效事件样本”的窄措辞。不得将这些检查描述为对统计数值、检测器、贪心选择、基线或来源资格的重算认证。最近100只是入口范围，不影响分母；排除事件可能仍参与全部日期基线。

### 身份与失效

图表Q和完整研究Q可以不同；V、请求参数、ownerQ用于归属，研究Q原样展示。显式cutoff时D保持请求截止，即使最后来源日更早；null cutoff时D取最后series.date，空series为null。analysis_id不认证内容。参数编辑即清、更新前abort/Generation失效、新接受必清、卸载/重新挂载不恢复、旧成功与旧失败都不能回写、旧DOM点击要核令牌，均为正确要求。切上方分段或图表选别的Row无需清六槽，只要研究上下文未变。

### 最小性

B0/B1能人工还原，拥有更多原OHLC，不应贬低；C只消除六槽与原状态的手工绑定。现有adjacentSource仅前一槽/当前槽，补成六槽＋事件归属已要承担本设计核心逻辑。零callback避免新截止切换、Row伪造和图表范围误报。h≠5与空事件无入口；近期100限制明确。无需新图、min/max、排序、持久化或网络。

## 6. 编码前关闭条件与后续验收

母任务应先收到修订后的三个文件新hash，确认R1唯一合同、R2重叠正例和R3重置/分类都已同步，再决定编码。该检查是文本复核，不授权现在执行测试。

以后获准的最小验收应包括：

1. P1/P2顺序、P3与P3_BAD未知尾槽、重复组/非正值/正close坏OHLC、成熟末槽null/0/负数、Kalman单独故障与重置。
2. 正常可达重叠、purge、overlap+purge优先级、invalid+purge、immature+overlap；当前分段与descriptive回退准确。
3. 同ID不同内容新接受、同对象再接受、连续请求乱序/abort/失败、参数非法未提交、所有上下文卸载/重挂载、旧DOM点击、折叠/焦点、最近100边界。
4. 独占投影无raw可变别名、其所有容器被冻结；支持的所有UI操作完整report深度值与原statistics/baseline DOM不变。禁止将rawreport违规变异列为必须抵御的产品行为。
5. 原validator拒绝不被绕过；门二失败保留原报告与账本；非法价格不转null；0/负数合法保留；h=1/10/20无新捕获影响；新增请求数为零。
6. 用合法完整合成响应与明确畸形卡分组验收；正常大响应测实际耗时/内存才谈性能。无毫秒/SLA/无卡顿保证。若需要worker/全树缓存/新数据，停止扩大并回设计。

本轮结果：静态审查已完成；发现3类必须修订事项。产品、合成测试执行、浏览器、本地服务、Windows、真实数据、性能与金融效果均未跑；不存在“测试全通过”结论。

## 7. r2 最终复核与关闭（2026-10-13 11:21 UTC）

重新读取修订正文、卡片与矩阵，实测文件SHA256与作者交付一致：

- design.md：`70417b47c16eee0c171464a3131a7c79250d7138ff24dffadb6af34a9fb36f49`
- fixtures.json：`1b149d8aa6625e44699ee657b3ec2c6c9cacf269aad6f35e6d826c9b8036a365`
- expected-answers.md：`274c549058f22910ee646bc1ab8d9d87cfd61885639701e820f12aa4c36a404c`

R1关闭：§2.2已是唯一窄合同，整树freeze及新总预算撤回；接受/失效流程、改动位置、索引、P7卡和B02/B03/C03–05/D02/D04均同步。投影自身根/嵌套容器/槽数组/槽对象冻结，无raw可变别名；原报告违规原地写明确不受支持，same-ID及same-object完整再接受仍清选择。

R2关闭：两张重叠卡目标index21，前一selected index20，lookback20；前20组高85，前一事件close/high90，目标close100，构成两个可计算突破，21≤20+5明确重叠。前一标签终点在目标t4，目标终点在t5，跨切点优先级可达。要求完整化补全部后来实际事件与计数，未把投影当完整DTO。新增immature+overlap卡明确两个标签终点均未出现。

R3关闭：坏槽后及估计故障后的有效槽明确warming_up/null reason；分类区分正常投影、故障注入、故意矛盾和孤立边界，未声称Kalman故障自然可达。成熟末端null/0/负数三个新增卡同步原end_close及invalid状态，A04/A05/A10验收已跟进。卡继承仍是文本说明，完整化必须按位置局部覆盖且保留父卡未被覆盖槽，不应将它当自动加载格式。

**最终裁决：GO。无剩余编码前设计阻断。** 允许母任务在既有授权内开始此最小本地UI实现；实现后仍须执行§6与冻结矩阵验收，独立代码审查后才可称实现通过。GO只覆盖设计，不等于代码/测试/性能/Windows/真实数据/金融效果已验收，也不扩大为Store、新数据、后台请求或后端改动。

本报告§2–§6保留初审问题与要求以便追溯，其“待关闭/不准编码”时态由本节r2最终裁决取代。
