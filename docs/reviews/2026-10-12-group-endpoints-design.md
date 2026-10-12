# 共同端点单组入口：独立工程反方审查

日期：2026-10-12 UTC。审查阶段：编码前方案审查。

## 最终结论

**可进入限定实现，没有剩余研究或方案层阻断。** 主方已在本审查成文期间确认准入，并要求先将研究、方案和独审文件写入仓库，再开始产品代码。 此结论只覆盖修订后的来源/分母/DTO/现有多股入口方案，不代表实现、测试、真实来源兼容、浏览器、Windows、性能或金融效果通过。

最终回读并核对的文件：

- implementation-plan.md：SHA-256 `e03d32ef3581d4dfdff0010270d71cecd9a0d4ec6459df4a362e9e5ce464a9f2`
- research.md：SHA-256 `d439f35392d9909699c8006099f6beca583e67f2418fba9348a3e64a249f1bd6`
- independent-review.md：SHA-256 `e49b715cca4c57baaaf1dba2759c86e88ca9023c684d8d88051ad69c54cab93d`

本审查先报告关键阻断，再由作者修订并回读确认。以下R1–R4均已写入最终方案，不能在编码时退回初版。回查和客户端信任边界两项追加澄清亦以R5写入最终方案，已回读确认，无新增工程范围。

## 审查方法与限制

已读仓库AGENTS.md、上述三份文档，并静读peer_relative_research、two_group_explanation、research_api、Store查询投影、numeric、symbol_identity、UniverseResearch、universe-request、ResearchRequestController、App回查链、020摘要及相关测试代码。仓库没有可读的.agents目录。最终方案回读时git status为空；写本报告期间主方开始新增研究/方案文档，故后续状态已出现两份未跟踪文档。本审查者没有修改仓库。

只读取源码和研究文档，只写本仓库外审查文件。没有读取真实行情、Store内容、旧DB或私有fixture，没有运行测试、采集、浏览器、性能实验或外网操作。没有重复作者的442文件基线检查与远端身份核验；这些仍属于作者证据。

## R1：来源拒绝不能遮蔽结构错误（原阻断，已关闭）

初版仅捕获_source的若干错误后保留行，存在确定的检查顺序漏洞：

- peer_relative_research.py:226–227在counts检查前即可抛unsupported_source。
- 235–244的known_negative_source、身份/调整/结构失败等发生在全部行结构检查前。
- 249–282的scope/source/period拒绝也发生在283–298的ordinal、OHLC容器和checks检查前。

因此同一DTO同时带有“已拒绝来源”和错误counts/重复ordinal/畸形checks时，初版会把应整请求拒绝的输入降级为普通无效成员。即使HTTP输入来自Store，纯函数合同也不能这样表述或接受。

### 采纳的最小修订

选择保留源拒绝行的方案B，避免选择器中的一份其它合法日线直接关闭全部可用成员；未退回“所有_source失败都整请求失败”的方案A。B仅机械提取既有检查，不建第二套递归来源验证框架：

1. header/IDs/selection：现_source 202–225。
2. counts与实际两表长度：228–233。
3. rows、两表全局唯一正真int ordinal、label位置、tokens/values容器、OHLC值类型、checks：283–298。
4. batch_checks继续用原_checks。
5. contract.source_semantics.fields及price_unit/adjustment单字段容器：264–270，可各用一个极小读取helper。
6. 仅新入口增加metadata.interpretation若存在必须dict；缺失沿默认空dict。错误归invalid_query，不递归其内容。

旧_source仍在原位置调用这些段，严格保持原异常优先级。特别是保留现有source_semantics非dict时按空semantics处理的行为，以及先price_unit语义、后adjustment字段形状的顺序。旧_source对非dict interpretation通常先经symbol_identity映射为invalid_source_id；不要顺便改变此行为。

新入口在任何可保留来源拒绝之前执行上述必要结构检查，再调用_source。只有冻结白名单中的来源资格拒绝可保留；结构、身份引用不对应、未知异常、Store读失败仍整请求失败。不得重新计算Store的哈希链、修复DTO、增加来源白名单，或把原件损坏伪装成一只缺失。

这会新增一次有界结构扫描，接受此明确成本。源码提取若改变030/043原输出或多错误优先级，须回退局部提取并重新审查，不能更改旧测试期望以消除差异。

## R2：每个无效成员必须诚实留行（原阻断，已关闭）

_source拒绝后没有进行端点定位与异常归类，初版的统一端点/异常结构容易误报“缺端点”或“零异常”。最终方案已冻结：

- 原N及全部snapshot/batch/query引用保留，source_change=null。
- evaluation=not_evaluated、endpoints=null、anomalies=null。
- 显示首个来源拒绝码，并说明尚未执行端点/异常检查；不承诺穷尽所有隐藏原因。
- source_identity_conflict或显示身份解析失败时symbol=null，不能因source_code可单独解析就洗成无冲突身份。
- 正常完成端点检查的成员保留全部已产生失效原因；异常全集先决定资格，再压缩为总数、各码计数和前20例。不能先截20例再判断是否有效。
- 解析成功且无冲突的重复证券、重复snapshot整请求拒绝；不得静默去重。

“可核symbol”在本报告中只表示经过现有声明归一化的一致性检查，仍不认证实际证券、品类或币种。拒绝来源上的显示声明不获得价格算术资格。

## R3：events共享须保持负证据和输入预算（原阻断，已关闭）

允许把_descriptor 162–181的事件段提取到小型_events；原_descriptor仍完成成员/target校验，不能用伪target创建一个不必要的完整descriptor。

_descriptor本身没有_auxiliary预算。030在外层先验证descriptor，043当前调用路径又不同。新入口必须独立先调用_auxiliary(events)，再调用事件段；不能借“共享原函数”省略16KiB、深度、节点、类型、refs与列表上限。

保持原事件成员与snapshot对应、日期相交、去重、规范排序、引用要求。scope_conflict仍整请求拒绝；halt及未解决公司行动仅保留原诊断语义，不能令其它无效成员恢复可算。给无法解析/绑定的成员提供事件须受控拒绝，不能无声丢弃事件。旧030/043事件输出和错误优先级均需回归。

HTTP首片不接附件、始终传空事件，UI常驻“未提供事件附件/覆盖未知”。不新增事件管理器、来源关联器或外部文件读取；也不声称该入口已核查公司行动。

## R4：BigInt需从合法端点建立实际界（原阻断，已关闭）

单独把每个整数字符串限制为4096字符，不足以说明50行累计运算的实际范围。最终方案已采纳先约束端点、再重算行比值的顺序。

### 静态上界与协议

合法正DECIMAL(38,18)价格乘10^18，得到1至10^38−1的整数A、B。r=(B−A)/A约分后，分子绝对值、正分母各至多38个十进制数字；负号另计一个字符。50项总和及除N后的均值，使用分母乘积作最保守界也低于2000位；Type7只需两个邻值和固定有理权重，远小于此界。4096传输上限因此有足够余量，不需调整Python全局整数安全设置。

客户端先验证canonical close_exact的正值、20位整数/18位小数范围，再用BigInt得到行分数并核对响应。汇总只累计这些受约束的派生分数，不能直接累计50个任意4096位响应分数。所有外来整数字符串先检查长度和规范语法，再BigInt；约分、正分母、零0/1、计数、比例及完整组四统计都需核对。

服务器整数上界应在危险转换前建立；若对通用输出helper测试超界Fraction，先用数值/bit-length等安全方式拦截，再str，不能先触发Python的整数字符串限制后泄露原异常。实际合法端点已由上述证明限制在安全范围。

百分比四位显示用整数半偶舍入，不能借Number改变精确符号或排序；极小正负值即使显示为0.0000%仍保留符号提示。ordinal和各计数应验证安全整数，不能沿用仅Number.isInteger的宽松检查。

## 保留的合同与去重结论

1. **来源资格可保留。** 完整可信Store query或既有OHLC projection、cutoff/ordinal为空、逐请求原件校验、腾讯strict/legacy日线白名单、正且完整OHLC/token核查都保持。两日期足够指原来源本来完整且短；不准裁两行隐藏全局反证。量额异常和日期异常作用域沿030。
2. **不伪造target。** _endpoint_member仅承担共同端点资格及原变化，旧_member补回role。新单组不调用peer_relative_report、不使用N−1。
3. **分母政策明确。** N为原名单，K为source_change非空，正+零+负=K。coverage=K/N，符号占比=A/K，K=0时占比全null。只有K=N才显示mean/median/Q1/Q3；K<N四者全null并有incomplete_group。不把有效4只全正写成原5只全涨。
4. **020没有被重复立项。** daily_followup.py:84–94已有广度与Type7，且使用有效子集。新片补任意明确版本单组的入口、共同a/b和完整组分母政策；不复制通达信固定池，不暗称新算法。
5. **043/Universe不改数学。** 043要求两个参考组和训练结构，Universe按每成员lookback取起点。新入口不降低lookback、不复用043训练失败输出当组摘要，不新增模型、排序、贡献或平台。

## API与生命周期审查

现有研究路由预算和Store._research_query可作为接入点。API须在加载前完成参数、日期、重复ID及行预算检查，使用cutoff=None读完整源；不要使用_load的全局period拒绝覆盖新行级来源状态。原件缺失/损坏、解码与数据库错误保持整请求受控失败。2MiB超限整请求失败，不能丢成员或改变N。

保留ResearchRequestController的generation、取消、dispose、单请求锁和提交时draft复制。新模式只加必要分派；三种研究模式中，existing仍分普通universe/filter两个既有端点，因此“每次唯一端点”须覆盖这四条请求分支。原lookback/filter脏草稿不得阻止新模式；新模式也不能破坏返回旧模式后的日期、roles和filter草稿。搜索/组名仅显示，日期/成员/模式改变即失效。

迟到fetch成功/失败、hash等待期间编辑、取消后新请求、unmount与pagehide/pageshow失效都须验证。现有纯控制器测试只验证失效原语，SSR不执行hook或真实点击；本轮浏览器禁止，因此不得把这些检查称为已验浏览器生命周期。

方案使用jsonRequest，2MiB是服务端结果预算；本轮不据此声称客户端已实现流式字节预算，无需顺带建设通用请求层。

## 原端点回查：最终最小范围已确定

主方最新明确收窄为现有onOpen(id,date)，本审查接受该范围：

- 结果内直接保留两端close_exact、close_token、ordinal和来源引用。
- 两按钮明确为“打开此版本至起点日期/终点日期”，打开对应snapshot的日期前缀。
- 不扩App/CrossResearch签名，不增加ordinal导航链，不宣称自动聚焦原行。
- 完整源query_id与回查前缀query_id属于不同selection，不能声称二者相同。
- 缺失或重复端点可打开前缀继续核查，但不能自动取最近值替代缺失。

App.tsx:128–146及340的现回调会清除selected并加载前缀，确实不聚焦ordinal。因此“单击精确原行定位”明确未完成且不属此片；没有留待实现时决定的callback扩展。本次工程准入验证的是同版本、同日期的可回查来源和报告内精确端点披露。

最终计划§7.4已将初版“公开原行定位”修正为“同版本a/b前缀回查与报告端点对账”。此项澄清已关闭，不扩大回查完成声明。

## 不可遗漏的验证与停止点

编码准入后至少保留以下反例，且先写异常输入用例：

- 拒绝源与坏counts/重复ordinal/非法checks/畸形interpretation或semantics容器同时存在；新入口整请求拒绝，旧030/043异常次序不变。
- 4、50成员；K=0、1、N−1、N；每一失效位置；A/B手算例；奇偶中位数、Type7独立期望、全零、净零、极小正负、大分母。正数缩放测试只在缩放后仍满足既有DECIMAL/OHLC/token合同的范围内声明不变性。
- 来源拒绝与端点拒绝两种DTO；诊断和失效并存；第21条以后的异常不得被截断隐藏；未知检查名应作为有界异常标签保留，不能误用闭合的成员reason枚举过滤原异常。
- events的refs、重复、错成员/版本、scope_conflict、空覆盖、16KiB/节点/深度边界。
- 合成capture→真实decoder→新tmp_path Store→HTTP，完整公开query/内部投影的资格与数值等价；原件破坏后受控失败、修复后显式重试。没有真实行情替代或旧库读取。
- 四条实际请求分支、旧模式草稿、DTO/分数/null/hash错配、迟到结果、取消、返回、按钮的版本/日期参数与限制文案。

客户端重算close_exact和analysis_id只能核验结构、恒等式及声明引用，不能独立认证一个合法ordinal/token是否确属原件。同一ID载荷的真实性仍依赖可信Store边界。原close_token可能使用科学计数、前导零等旧Decimal允许的表示；不为客户端检查新设源token语法限制。客户端对原token做类型/长度检查并原样披露，算术用规范close_exact，来源token对应性由共享服务端资格负责。相关篡改测试应区分结构/数学错配与无法脱离原件独立核实的内容，不能承诺检测一切任意字段变更。

全Python目录含按条件读取私有数据的真实样本测试，单靠“文件应不存在而skip”不安全。最终方案已改为先静态列清并显式排除这些用例/文件，且不访问私有路径确认存在性。未过滤全套保持未跑。还须保留共享提取受影响的peer、peer-adversarial、two_group、universe、research_api及必要Store projection合成回归，所有Node与TS/Vite构建；不拿历史通过数替代本轮结果。

如实现不得不扩大来源资格、改Store/schema、引入依赖/采集/真实库/浏览器、修复无关043逻辑，或旧输出/异常无法保持，停止相应部分并报主方。限定实现完成后仍须独立检查最终改动与实际测试证据，方可形成工程完成结论。
