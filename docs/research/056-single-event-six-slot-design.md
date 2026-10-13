# 单事件 h=5 六槽证据：编码前最小详细设计

编者注：下文保留编码前设计时态；同编号 design-review 的 §7 最终 r2 GO 已获接受，已进入最小实现。下列验收条目在原设计时尚未执行，实际执行状态以 056 主记录为准。

2026-10-13 UTC。源码基线：`70f68ef1dcb33fe45e895b01ea8861446d648bc9`。状态：**详细设计完成，提交独立设计审查；尚无实现准入**。

## 0. 授权、依据与交付

本次全文读取：本项前置工作流调研、本项独立任务走查。通过 `git show` 读取该固定提交的根 AGENTS、SingleResearch、research-types、research-model、event_study、research_series、numeric、adjacent-source，定向读取 signal_research、research_api、App、model、types、api、group-endpoint-model、group-source-path-model。未读取 Store/数据库/行情文件，未请求网络行情，未运行产品、测试、模拟或浏览器，未写仓库。这里的事实依据是源码静态阅读。

本目录三个文本交付：本设计、`fixtures.json`（手写且冻结的概念卡）、`expected-answers.md`（固定预期/验收矩阵）。卡中所有日期、源序号、价格、ID均为**合成说明数据**，并非历史观测。卡是必要字段的投影，不是完整研究 DTO，不声称通过已有 validator。后续若获实现准入，须先由审查者按现行 DTO 补齐合法合成响应，再执行测试；不允许用强制类型断言使投影冒充已验响应。

## 1. 唯一产品动作及最小性复查

用户在现有事件账本的最近100条中，点击一条事件的“查看6槽原价”，就地看到该事件日及后5个来源日期组：固定顺序、精确收盘字符串、真实日期/源序号、原标签和评价归属。一次最多展开一条。适用条件是本次已接受的单股研究 horizon=5。h=1/10/20保留现行界面，不提供此展开入口，并写“六槽原价查看仅适用于观察跨度5；切换跨度会重新研究”。不自动修改h或调用更新。

B0现有原图/原表与相邻详情能人工回答价格顺序，含有C不提供的原OHLC和质量明细。B1只连接当前已加载真Row，能省去找事件起点；相邻详情仍给t−1/t0，无法直接提供t0..t5与事件标签/统计归属。给B1加入完整窗口与状态绑定就已经承担本设计的主要逻辑。原始Row与日期组也不一一对应。C的边际价值仅为免去手工重建这个绑定；未证明省时、易用性或金融效果。

第一版**完全不做源回查 callback**：不新增 onChoose/onOpen，不调用 chooseRow，不构造Row，不改变图表截止，不自动翻页/聚焦。显示真实定位信息即可。现有图表分页/默认60根之外但仍在query.rows的行，不能称为“不存在”；本版不增加该存在性诊断，以免额外扫描、错误承诺和接线。固定说明：“下列位置属于本次研究响应。当前原图范围可能不同；此处不自动定位原图。”这不声称某行确实不在原图。原图入口功能原样保留。

不增加：极值、百分比、涨跌标签、曲线、评分、预测、排序、自动择事件、全事件分页、导出、持久保存、跨报告缓存、网络请求、Store读取或后端API。已有事件表的原价格变化百分比继续原样显示；六槽详情不重复/新增该计算。

## 2. 身份：两类Q、两类截止、一次响应代次

### 2.1 固定上下文

本地接受记录 A 包含：
- `ownerQueryId`：当前图表Query的query_id，只用于归属/失效。图表可有ordinal范围。
- `snapshotId`：query.snapshot_id，须等于report.inputs[0].snapshot_id。
- `researchQueryId`：report.inputs[0].query_id；独立展示，不要求等于ownerQueryId。研究API取完整prefix，未传图表ordinal范围。
- `methodId`、完整 `analysis_id`、已验请求参数（cutoff/lookback/horizon/test_start与固定model）；analysis_id只标识method+inputs+parameters，**没有result内容哈希含义**。
- `requestedCutoff`：report.parameters.cutoff，ISO日或null。null显示“请求未限截止”。不替换成今天/最后日期。
- `evaluationAsOf`（D）：events.evaluation_as_of。显式cutoff时必须等于请求cutoff，即使最后来源日期更早；无cutoff且series非空时必须等于最后series.date；无cutoff且series空时必须为null。所有series.date≤D；非空事件的evaluation_as_of必须等于D。
- 当前实例唯一 `acceptToken`（本地对象令牌，非业务ID），以及请求Generation。本地令牌不显示、不持久化。每次成功接收，包括同analysis_id、甚至同一对象引用重复接收，生成新的acceptToken并清选择。

事件选择 E 为 acceptToken + event在events.rows中的数组位置 + event.index/date/ordinal。事件数组位置与series索引明确区分。展开前必须仍属当前A，当前h=5，原事件位于当前最后100项，所指对象仍是A拥有的event。不得用date或analysis_id跨响应找回旧选择。

### 2.2 唯一支持合同：只读报告拥有＋独占六槽投影

独立审查R1与母任务已选择本合同；原整响应冻结提案撤回。接受入口仅处理jsonRequest解析的JSON和可信测试构造的JSON数据；不承担任意getter、Proxy或恶意JavaScript对象图的防护。旧assertResearchReply不变。h≠5不执行新捕获或账本关系检查。

SingleResearch是已接受report的只读拥有者，发布后的原报告、原事件和series不得原地写入。现有onReport消费者以及新详情都必须只读；任何更新通过完整重新接受。可以用局部readonly接口及注释表达，不要求全仓库类型迁移。每次成功接受生成新的acceptToken并清E，即使analysis_id相同、内容相同、甚至同一对象再次提交；新响应代次和原对象身份是不同概念。

点击时，在同一同步过程先核A/Generation/当前query归属及选定事件，再校验并逐字段复制固定身份、参数标量、事件显示字段和最多六槽字段，形成局部独占投影。所有字段均为原始不可变string/number/boolean/null；容器由此处新建，缺少的槽用本地未知槽对象表达。投影不持有raw event、series行、数组、parameters、counts或statistics等可变对象别名。冻结投影自身的根、身份/参数/事件子对象、槽数组及每个槽对象，不能只冻外壳。捕获大小为固定6槽＋有界标量，不复制完整report，不做JSON.stringify快照、hash或全树访问。

E持有这个投影及acceptToken；原表/统计继续读同一次接受且按支持合同保持不变的report。当前train/test说明只由投影中的原partition/selected/evaluation与当前实际显示分段产生，不改投影。渲染与点击仍核token、report实例、Generation和当前上下文。未来若增加异步捕获或原地更新需求，必须重新审设计，不能静默绕过。

强制类型转换后原地修改raw report属于不支持操作；独占投影本身不会随其改变，但不承诺这种违规修改后原表与捕获保持一致。当前实际消费者均只读，没有产品上的原地更新需求；不用假想恶意消费者引入整树freeze、新全局资源预算或每次render全报告比较。后续源码审查必须确认无新增mutator。

捕获/局部校验失败时，保留旧validator已接受的原报告与账本，新详情进入本条错误态，不展示部分六槽。接受级关联失败则禁本次所有新详情，旧响应选择不保留。不自动取数重试。所有支持操作都必须保持原report的深度值与可写属性描述符不变；只有独占投影容器冻结。

## 3. 详情UI精确约定

### 3.1 入口与布局

现有最近100条账本增加一个末列按钮，所有原事件状态、正负变化均可尝试展开，不只开放valid或上涨事件。展开为该行紧邻的跨列详情行；同条再点折叠，另条替换旧详情。按钮原生button，aria-expanded与aria-controls准确，键盘Enter/Space沿用原生语义；不把整行做第二套交互。收起按钮及Escape关闭详情，焦点回原按钮。外层“查看事件记录”details关闭时清选择；再次打开不自动恢复。无自滚动、无模态框、无浏览器历史记录。

标题：“事件日与后5个来源日期组”。说明：“按本次研究响应的日期组顺序保留6个位置；日期间隔可以不连续，5步不代表5个交易日。”

定位区域显示完整V、完整研究Q、完整analysis_id；图表Q在可展开的同一区域标为“当前图表查询归属”。ID用可换行文本，不裁短到无法核对。列出lookback、h=5、test_start（null为“未设置”）、请求截止与原评价截止D，事件index（明示零基来源槽索引）、事件日期、源序号。不要显示未核的证券名/交易所/货币推断。

原状态区域显示四项原值与现有researchReason中文：
- “原贪心去重selected：是/否”（与界面展开选择完全分开）
- “原分段partition：descriptive/train/test”
- “原标签label_status：valid/invalid/immature”，原label_reason（null显示“无”）
- “原评价evaluation_status：valid/invalid/immature/purged/overlap_excluded”

显示原label_end；null标“未成熟，终点尚无来源槽”，仅在通过局部一致性后使用此文案。原start_close/end_close供一致性核对；六槽t0/t5已显示其内容，不另算比值。

### 3.2 固定六行

列为：位置t0..t5、来源日期、源序号、规范精确close、原系列状态/原因。只有t0标“事件日”，t5标“五步位置”；未成熟时t5不标“已观察终点”。位置严格是series[i+k]，不按price排序，不跳过null/坏值，不用ordinal+k，不补日历。

已存在槽：date为其真实ISO日；ordinal=null显示“无唯一源序号”；close=null显示“∅（本槽未保留可解析收盘）”；其余close以原字符串逐字显示，不格式化、不四舍五入、不加货币单位、不加千分位。0、负数若格式合法照样显示，并写“响应保留值，不赋予标签资格”。所有已存在close都视作响应保留值；不得把正数默认标合格。

越过series末端的位置：日期“未知”、序号“未知”、close“未知”、说明“原评价截止下尚无此来源槽”。这是一个缺少整个槽的状态，与存在槽的null不同；不编未来日期、不用0、不拿最近close补齐。显示“已有4/6个来源槽”等存在槽计数，仅属布局信息。

系列栏明确标题“原系列状态（含估计层）”。使用现有researchReason渲染reason；未知代码安全显示“未识别状态”，不赋予新资格。不将series.status、reason、breakout_reason当完整OHLC核验。Kalman numerical_failure不改事件label/evaluation。没有新逐槽OHLC认证徽章。

固定边界说明：“本表转述原响应及规范收盘值，未重验完整OHLC、复权、公司行动、历史可得性或成交条件。收盘序列不能确定柱内触发先后、可成交收益或未来路径。”

### 3.3 上方当前分段的实际事件归属

确定上方实际分段必须采用与现行part相同的解析：有test_start时当前train/test；无切点时实际descriptive，不能把state默认test当显示分段。有切点时缺任一预期分段视为局部关联失败，不能悄悄fallback冒充test。

局部一致性通过后，定义“计入上方有效事件统计”为原selected=true AND 原evaluation_status=valid AND 原partition=实际显示分段。只转述原响应的有效事件样本归属，无需重算价格变化、去重或突破。文案分三种：
1. 满足三条件：“按原响应，此事件计入当前[分段]的有效事件样本。”
2. evaluation=valid但别段：“按原响应，此事件属于[原分段]的有效事件样本；当前上方显示[分段]，本条不计入该分段。”
3. evaluation非valid：“本条未计入当前上方的有效事件样本。原评价状态：[状态]；原分段：[分段]。”可补充它属于该分段的对应排除/未成熟计数，但不新增数值。

固定附注：“以上仅指事件样本；全部日期基线另有规则，可能包含该日期。”不从overlap_excluded推断基线排除。切换上方train/test只刷新这段说明，不改事件selected/partition/label/evaluation，不重新取数，不收起六槽。

## 4. 校验边界与价格合同

### 4.1 两道门，不削弱旧validator

门一仍是现有assertResearchReply完整成功；任何旧有拒绝继续走原错误流程。新功能不更改singleResult、pairResult、universeResult的旧验收范围，不通过宽化旧DTO修复新失败。门二为局部纯校验，不调用API/Store，不重运行event_report、Kalman、突破、贪心选择或任何统计估计。

新门有两级：接受时O(N)的原事件账本关系核验（N≤20,000）以及展开时最多6槽证据核验。接受级失败只禁用新详情；原账本和上方报告仍可查看，附注“六槽关联校验未通过；原报告按原响应展示，未重新认证”。所有新失败不得修改或删除原事件、过滤series、重算分母、自动重试取数。

### 4.2 精确字符串，不创建新数值引擎

源域沿用numeric.decimal_value的DECIMAL(38,18)与decimal_text规范，及现有group-endpoint-model的price词法规则：可选负号，整数为0或无前导零的1..20位十进制；可有1..18位小数且最后一位非0；禁止`-0`，`-0.1`合法；最大40字符（符号+20整数+点+18小数）。允许0。拒绝空白、加号、指数、NaN/Infinity、前导零、末尾小数零、逗号、非ASCII数字、超范围。null作为缺值另行处理。

本设计只需要规范字符串相等、是否正数（规范字符串不为`0`且不以`-`开头）及已有数组次序；**完全不需要BigInt、有理数、排序比较、Decimal运算或百分比**。新增小型局部词法断言与group-endpoint既有规则保持逐字符一致，用冻结边界卡防漂移；不抽取/重构050/054数学引擎，不引入依赖。不调用Number/parseFloat/closeNumber，不将字符串字典序当数值大小。日期与整数索引用原有域，不经过价格转换。

有效格式的非正close是允许保留的证据。它可出现在原invalid/immature窗口；只在原label=valid时构成必要条件矛盾。格式非法的close不能显示为可信精确值，也不能默默变null：阻断本条展开，保留账本并给安全错误码。原字符串不进入HTML或异常堆栈。

### 4.3 接受级字段与账本关系核验

以下均以已通过旧validator的报告为输入。局部投影只读取列出的字段，不信任TS声明代替运行时校验；未知额外后端字段不导致新功能失败，仍受门一safeJson约束；新功能不扫描未知附加字段。

- identities：唯一input；V/Q/analysis均64位小写hex；method=`daily-causal-research-v1`，mode=`retrospective`。ownerQueryId、V、请求cutoff与当前Query相等；researchQ可与ownerQ不同。参数与捕获的request.expected完全匹配，h=5，lookback整数2..252；test_start/null规范ISO日。events.mode必须与是否切点一致（descriptive或time_split_descriptive）。
- 数组series/events.rows各≤20,000；events≤series；日期严格递增。事件index为0..series.length−1安全整数，ordinal为1..MAX_SAFE_INTEGER；每条event的index/date/ordinal/breakout=true连回series；index随事件严格递增，无重复。保留完整账本，入口限最后100。
- 每条event.signal_as_of=date，evaluation_as_of=D；start_close/end_close必须是自身字段，类型为规范精确字符串或null，start_close必须正数并与series[index].close逐字一致。end_close须与series[index+5].close逐字相等，若无槽则为null。这里最多检查两端，不物化全部窗口。
- partition只能descriptive/train/test；无切点为descriptive，有切点按event.date < test_start归train，否则test。partitions键集合须恰是{descriptive}或{train,test}。
- label_status只能valid/invalid/immature，evaluation_status只能valid/invalid/immature/purged/overlap_excluded；selected为布尔；label_reason为null或下列已知标签原因。拒绝“未知资格状态”，不作合格映射。
- 完整性只由i+5是否在series内决定。越界必须immature，label_end=null、end_close=null、price_change=null、label_reason=insufficient_future_records；前面即使有坏槽也保持immature优先。i+5存在则不得immature，label_end必须为该槽date。
- 成熟valid：label_reason=null、price_change为有限number（只验证类型，不重算），两端原close正且一致。成熟invalid：price_change=null、label_reason只能invalid_label_window或numerical_failure；端点字段仍按实际series值核对，允许null/非正末端。不要求invalid必有坏close：完整OHLC失败、源冲突或原数值失败可能未体现在收盘上。
- evaluation优先级：selected=false必须overlap_excluded，无论label或跨切点；selected=true时，partition=train且非空label_end≥test_start必须purged，否则evaluation必须等于label_status。purge可覆盖成熟invalid，不能只允许valid→purged。没有label_end的immature不能purge。不从这些检查重新选择selected，不认证贪心算法正确性。
- **只校验已有事件归属计数一致性，不计算新统计**：一遍对每条event的原partition/selected/evaluation做有界整数计数，核对总events和每个partition中的counts.raw_events/selected_events/overlap_excluded/valid/invalid/immature/purged；existing statistics.count须等于原evaluation=valid的条数。允许整数计数和比较，结果不输出为新报告。candidate_dates/rule_computable、统计数值和baseline仍由原validator负责，绝不从最近100或六槽重算。原valid价格变化正负分布、均值、分位与基线不重新认证。此处是支持“计入当前有效事件”的必要关系核验，未宣称全报告数学复现。

### 4.4 展开级最多六槽核验

上下文有效后按i..i+5读取，至少t0存在。每个已存在槽必须有规范ISO date、安全正ordinal或null、close规范字符串或null、status∈{computed,warming_up,invalid}、reason为null或非空≤4096字符串。日期顺序及截止沿门一/接受级验证。所有字段以text节点呈现，reason显示沿用researchReason的安全/128字符可见限制；该限制不改原存储值。

ordinal=null须close=null、status=invalid、reason=duplicate_date；reason=duplicate_date也须满足此前结构。这是daily_bars的现有重复槽结构，并非恢复重复原记录。已有唯一ordinal但close=null可以保留（如missing_ohlc/unlocated）；不凭null建立新原因。status=invalid须reason非null；computed/warming_up须reason=null。允许status=invalid、reason=numerical_failure、close>0，与原valid label兼容。

原label=valid另需：六槽全部存在、close全部正、ordinal全部非null。对明确的原系列来源失败reason（duplicate_date、unlocated_label、missing_ohlc、invalid_price、invalid_ohlc、known_negative_source、source_identity_conflict、source_adjustment_conflict、source_adjustment_check_failed）与valid矛盾则阻断；numerical_failure例外，不升级无效。valid遇未来未知reason也不自动放行新资格：局部阻断并保持原标签；已知估计层reason数值失败被明确允许。series.breakout_reason不作为后续槽价资格：history_insufficient/invalid_history_window与本事件后窗资格不是同一件事。

原label=invalid/immature不得用六槽正价或series估计成功恢复valid，也不因已有坏槽把immature改invalid。原OHLC标签资格只能转述；这些条件只能发现必要关系矛盾，不能重新证明完整来源合法性。

失败文案统一：“本条六槽证据与原响应的关联不一致，暂不展开（event_path_inconsistent）。原事件和原报告仍保留。”内部原因码可在局部详情诊断区显示固定枚举：identity、cutoff、event_link、endpoint、label_state、evaluation_state、partition_counts、price_text、slot_structure、resource；不回显任意服务器内容。失败时保留此次被点的原事件身份与原四状态摘要及错误，不展示部分可信/部分不可信六槽，不自动换选其他事件。

## 5. 状态机与所有中断路径

局部状态只有：unavailable（h≠5/接受级失败）、ready-closed、ready-open(E)、ready-error(E)。无独立异步取数，展开校验同步最多6槽，禁止新增加载请求。

1. 任一lookback/horizon/test_start输入的onChange，在同一次事件中先调用invalidate：Generation前进、abort、清report/A/E/error、onReport(ownerQ,null)。即使输入暂时非法、未提交，也立即隐藏旧详情；不得只监听已提交值或analysis_id。
2. 点更新：同上；loading期间无旧详情、按钮不可触发旧事件。重复提交前者失效，旧成功/旧失败均不得落入新Generation。
3. 新响应：先核Generation，再门一与同步局部接受检查；以只读拥有合同发布新report，生成新A或新unavailable，必清E；若检查将来加入await则必须重新审查每次await后的代次门，第一版不允许。
4. 查询V/cutoff/ordinal范围变化、重新查询相同参数：App.invalidate先清reply/sourceResearch；SingleResearch卸载。新query_id由key重建；同query_id重新挂载仍生成新本地所有权，旧选择不恢复。query对象仅换引用但不换query_id时，渲染门还比V/cutoff/ownerQueryId与A，矛盾即不显示证据；此非正常注入不得等useEffect才隐藏。
5. Workspace、数据导入、图形错误导致App.invalidate/卸载，旧Generation失效；卸载清所有局部所有权、abort。回到单股重新加载，旧选择不恢复。组件cleanup不调用旧query的异步回写去清新query；原bindSourceResearch的queryId保护保留。
6. 原API失败、登录/本地会话失效、连接中断/abort：沿原issue/phase流程，不显示旧报告详情。不自动发恢复请求；用户正常更新后才有新A。首次加载无报告，空series无入口。
7. 同事件重复点击切换；换事件只保留后者；校验失败只保留本次错误，下一次合法选择清错误；Close/Escape/外层details收起清E和局部错误。不清原report或上方统计。
8. 切换评价分段保持E，只按§3.3刷新上方归属；原字段不变。图表选别的原Row、原表翻页、图缩放、打开其他无关details不改变研究上下文，E保持，不装作同步焦点。
9. 浏览器Back/Forward无新增history。若引起页面卸载/Query变化，依对应invalidate清理；否则不产生隐藏选择迁移。页面刷新不能恢复E。StrictMode重复挂载/cleanup不得接受第一次旧响应。
10. 所有渲染与点击入口均要求E.acceptToken===A.acceptToken、A.report===当前report、Generation一致、当前context字段一致、h=5；从错误/折叠旧DOM排队点击也不能重开旧事件。令牌对象避免数字计数溢出/ID复用。

## 6. 改动位置与不变项

若以后另获编码批准，预计最少：
- `web/src/SingleResearch.tsx`：接受时绑定代次、点击时捕获、局部选择清理、现有事件行按钮与详情、分段归属。
- 新 `web/src/single-event-path.ts`：小型纯字段/关系校验、固定6槽投影、局部不可变捕获辅助。没有网络依赖，无通用框架。
- 可选新 `web/src/SingleEventPath.tsx`：纯展示；若内联更短则不增文件。
- `web/src/research-types.ts`：在现有事件行类型补上后端已有的start_close:string、end_close:string|null，或命名该事件类型；不得据此省去运行时门二。不全局改所有研究为Readonly框架。
- 仅必要的现有样式小补丁（长ID/价格换行、详情行），具体样式文件实施前再定位。
- 获准后补局部model测试与SingleResearch交互测试，现有research/adjacent/App回归；具体文件遵循仓库测试组织。

不改Python numeric/research_series/event_study/signal_research/research_api、Store、数据库、API路径/输入/输出、原statistics、baseline、selected、partition、原label/evaluation、现行shared validator、SourceChart、chooseRow、adjacent-source、GroupSourcePath。不复制054 hash、分数或attachment体系。

## 7. 有界验收与审查关口

完整冻结矩阵见expected-answers；本轮仅纸面预期，任何条目均未运行。后续实现准入须由独立审查明确决定，不能把本文件标记为“已通过”。建议审查者先攻击：独占投影无可变别名、同对象再次接受、null cutoff的D、invalid→purged优先级、未知reason、局部失败不毁原账本，以及局部关系扫描对20,000条常规响应的实际成本。

硬停止线：需要新fetch/Store/市场数据、完整行情加载、重算事件/统计、全账本UI框架、内容hash/持久缓存体系、价格运算引擎、来源资格升级，或B1已有组件经复核确能更小地完成六槽+身份+状态时，停下本路线并退回设计，不把扩大范围藏在实现里。

独立审查后的修订应逐项答复。只有母任务明确授予实现准入后才允许产品/测试代码工作。随后也须分别报告静态、合成测试、浏览器、本地运行、Windows、真实来源、性能与金融效果；未做项目继续未做。

## 8. 对独立走查§5七项未决问题的定案索引

1. 精确字符串/价域/null：§4.2；沿用既有规范，零运算，非正保留；无新数值引擎。
2. 三种label、evaluation一致性/失败/OHLC范围：§4.3–4.4；局部阻断，原响应保留。
3. 未成熟布局：§3.2固定六位置，未知date/ordinal/close，不合成日期。
4. report代次、同ID替换/同对象再接受/不支持原地变异/编辑未提交：§2.2与§5，只读拥有、独占六槽捕获并令牌失效。
5. 四状态与当前分段/基线：§3.3、§4.3，只解释原有效事件归属。
6. 入口：§1仅最近100，不称全账本可选，统计仍全范围。
7. B1：§1第一版零callback，真实V/Q/D/date/ordinal，既有图表能力不被贬低，不承诺聚焦或新截止打开。

### 设计审查修订记录（r2）

R1已按母任务决定收敛：撤回整树冻结、新节点/字符预算及任意JS对象防护，只保留只读响应拥有、每次接受新令牌和最多六槽的独占冻结投影。静态核读App.receiveSourceResearch→bindSourceResearch→RecordDetails/AdjacentSourceDetails→adjacentSource均为报告读取；ResearchProvenance读取/序列化，EstimatePlot收到新map投影。未发现原report写入，运行回归尚未进行。

原safeJson允许额外字段、单字符串至4096字符，20,000数组上限不能证明响应总字节小。本功能不新增全树扫描，也不声称修复既有解析/validator资源局限；接受时账本关系扫描有界O(N)，点击最多六槽。实际耗时/内存需日后有授权的合成验收才能报告。

R2修复：正常重叠卡目标事件移到index21，前一已选中突破明确index20，lookback20；前缀及两个起点高价关系明确，完整化须补实际产生的其他事件与计数。R3修复：坏槽和估计失败后有效槽明确warming_up，卡片区分正常合成投影、估计故障注入、故意矛盾及孤立边界；新增成熟末端null/零/负数和未成熟＋重叠的预期卡。

本修订回应独立报告R1/R2/R3，提交复核；尚未实施产品或测试代码，也不自行授予实现准入。

### 实现后的可读性与状态修订索引

默认按钮/标题/状态已按[056最终研究记录](056-single-event-six-slot.md)改为日常中文；完整技术身份、原字段和参数移入可展开来源区，原标签与评价仍分列。独立复审确认无语义损失。完整上下文永久失效及所有旧回调的具体选择身份门已补齐。最终限定本地验收及未跑项见[056验收](../qualification/056-single-event-six-slot.md)，本设计保留原编码前历史时态。
