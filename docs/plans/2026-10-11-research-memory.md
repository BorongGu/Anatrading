# 集合研究逐源准备：内存优化实施候选

日期：2026-10-11 UTC。状态：**候选B已获[独立编码前批准](../reviews/2026-10-11-research-memory-review.md#7-作者回应与最终复核)；实现及独立实现审查已通过，最终回归/真实矩阵已完成，正式矩阵共享内存/时延通过，但筛选RSS增量未达，原整体保留条件未通过；08:03 UTC经独立后验审查与主方决策，分阶段保留B并准备发布，失败项保持开放。进度与证据见[本片验收](../qualification/research-memory.md)。** 依据[033内存研究](../research/033-research-memory-cost.md)、[现行筛选资格](../qualification/stock-filters.md)与[紧凑读取合同](2026-10-11-compact-research-reads.md)。本片独立于第四片冻结发布，不重写已有失败记录。独立反方及逐项决定见[设计审查](../reviews/2026-10-11-research-memory-review.md)。

## 1. 选择与范围

选033候选B：全部预算以后，每来源一次完整读取和完整前缀归一化，只保留来源header、coverage及末N+1窗口；全组身份、错误裁决、指标和汇总遵守旧顺序。候选A的fetchmany保留为后续独立小改动，**本片不做、不以A为前置条件**。先去掉全组展开query的主要驻留，再看实测；不将SQL取批和调用方生命周期改动混在一次归因中。

实现最多涉及：

- `research_api.py`：两条集合HTTP入口的逐源准备、延期错误控制，以及现有两种计算错误映射的局部提取。
- `universe_research.py`：提取一个完整前缀→coverage/window准备helper、一个共享指标/汇总内核，以及必要的共享成员校验。纯函数入口语义不变。
- `stock_filters.py`：提取既有规则/输入前置与最终组装；纯函数和新的私有prepared入口使用同一计算/解释实现。
- `workbench.py`：仅研究路由注册处传入现成 `_safe_store_call`；其实现、owner、码表、状态映射及其它路由不改。
- 对应的合成异常、差分、对象存活和HTTP测试；正式性能脚本/结果与私有数据放仓库外，仓库只存合成测试及验收摘要。

不改Store、SQL、fetchall、数据库schema、normalizer/numeric、公开query/导出、原件核验、数据来源/采集、预算、单股/双股路径、UI或依赖。不建缓存、队列、插件引擎、异常序列化框架。若实现需要扩大这些范围，停止并复审。

## 2. 输入与私有准备结果

### 2.1 准入和读取

两集合入口沿用参数/规则解析、排序后ids及现有全部count→统一预算检查。不能在发现首股超过20,000时早退，从而遮住后续count异常。成员2–50、单源20,000、总200,000、N2–252均保持。

每个来源仍完整调用 `_research_query(sid,cutoff=D)` 一次。不得把调用放入捕获准备错误的安全包装器：read/count异常直接沿旧owner边界立即终止；首个读取失败后不额外读取剩余来源。规则无效和预算失败仍零物化。

### 2.2 每来源保留内容

用小型私有记录承载以下内容，具体可用普通dict/小dataclass，不引入通用schema：

- `header`：`snapshot_id,batch_id,query_id,selection,manifest,metadata,batch_checks,counts,read_projection`。这些字段完整保留值及absent/null，不更改完整来源选择身份；明确没有rows/unlocated。
- `selected_count`：经过原 `_at_cutoff` 后的rows+unlocated总数。
- `selection_error`：若选择阶段出现异常，保留经现有映射得到的 `(code,status)`；否则空。
- `prepared`：既有 `daily_coverage(selected_query,full_bars)` 的完整结果及实际末N+1 `window`；缺D时window为空。绝不在window上重算coverage。
- `preparation_error`：normalize/coverage/取窗阶段失败时相同的小型错误对；否则空。

没有完成的字段显式空，仅由私有控制流读取。不得把该记录传给 `daily_bars` 伪装为完整query，或直接作为HTTP/导出载荷。

原query及 `_at_cutoff` 浅拷贝只存在于一个单来源函数作用域。读取、准备返回后，在调用下一源前退出该作用域；不能让外层 `q = load(next)` 的旧q绑定保留上一源历史。完整bars、grouped、tokens/checks不加入header或prepared。window为既有bar列表slice，bar无原始row反向引用。

目标活数据为 O(Tₘₐₓ+M(N+1)+ΣHᵢ)，单源完整rows及fetchall仍保留。此为对象可达性目标，不能直接宣称RSS已降至相同比例。

## 3. 最小共享计算边界

下列为职责，名称允许实现时局部调整；不允许生成第二套指标/筛选公式。

### 3.1 universe

1. 把现有成员前置提取为小型共享函数：lookback→D→数量/容器→全部symbol_identity→market mismatch→duplicate symbol→duplicate snapshot。读取header足够；返回identities。不得边读边提前跨成员拒绝。
2. `_prepare_window(selected_query,D,N)`：仅执行现有daily_bars一次、daily_coverage一次、target和window选取，返回coverage/window。保留全前缀所有坏槽及日期语义；不执行指标、排序、source摘要或filter。
3. 共享 `_evaluate_members(headers,identities,prepared_iterator,D,N,with_evidence)`：原逐成员行构造、momentum/Fraction、volatility、drawdown见证及证据收集，之后原排名/广度/报告逻辑。计算语句及相互顺序保留；prepared_iterator只提供同一成员的coverage/window。
4. 公开 `_universe_evaluation`/`universe_report` 保留签名与调用意义：先原前置→对所有query执行_at_cutoff→总行数检查，随后给共享内核一个**逐成员惰性**prepare迭代器。成员1准备/指标先于成员2准备，保持pure输入的原失败次序；不把pure路径也改成“先准备全体”。纯函数仍接受完整列表/tuple，不能新增接受任意外部generator的公开约定。
5. HTTP的私有prepared入口：在相同成员前置后先按原序重放全部selection_error，再检查selected total，随后提供一个逐成员迭代器，在各成员yield前重放其preparation_error。因而成员1公式异常仍早于成员2normalize异常。

共享内核只访问header中的snapshot_id及既有identities，全部metadata留给filter后处理；旧universe不因prepared而多输出字段。接口envelope仍由相同inputs/parameters/result构建。

### 3.2 filter

- 原 `filter_report(queries,D,N,rule)` 继续执行：normalize_rule→D→容器/数量→按输入顺序prior-cutoff校验→snapshot排序→原universe evaluator。这个顺序不变。
- 从现有283–303行提取 `_assemble_filter(headers,universe,evidence,canonical,D,N)`：全部_source→共享contracts→条件目录→全部_member→inputs及各ID→counts/envelope。此处调用现有_source/_member，不复制精确比较、三值逻辑、原因汇总或来源合同投影。
- 私有HTTP prepared入口使用相同filter前置和同一个组装helper，中间调用prepared版universe。它只接本次owner内部产生的prepared记录，不公开到路由参数、Library或Store。
- 来源header包含manifest/metadata/batch_checks，因此_source和source_rejection仍读取原内容。规则来源合同、原始价格文本、source/window/analysis IDs与旧结果逐字节一致。

共享helper调用是内部重构；现有测试若依赖被拆分的函数名，须把spy迁移到实际共享边界，同时保留原完整响应/安全错误断言。每成功请求仍为M次count/read/raw/bars、一次共享集合计算；不允许绕过旧spy后宣称覆盖。

## 4. 错误映射接缝与延期边界

### 4.1 可信输入下真实可达性

完整_research_query已验证row为普通dict、tokens为dict、checks的name为字符串且outcome合法，OHLC为数据库Decimal或None，selection由Store构造。当前prepare没有任何Store、文件、decoder或acquisition调用。

- daily_bars显式ValueError只涉及unsupported_period、research_row_limit、ordinal_window_not_supported、invalid_cutoff。
- 后三项在集合HTTP中由已完成的参数/预算/完整读取保证；period仍可能不支持，应在全部读取结束后的原屏障拒绝。
- `_bar` 中decimal_value的NumericError被捕获并转成invalid_price坏槽；其它坏值、重复日期、冲突、隔离均为既有reason。
- daily_coverage无显式业务异常。没有合法持久输入例子能使AcquireError、DecodeError、StoreError或OSError从这个pure调用图正常逃出。

仍须保住已有程序故障边界及多错次序。未知ValueError在两路的映射不同；人工注入NumericError/OSError也有现成owner码。下节直接复用这些映射，不因此构建异常类型注册表。

### 4.2 只存最终安全code/status

`register_research_routes`额外接收现成 `_safe_store_call` 函数，由workbench的现有注册点传入。它只是同步执行和安全映射的函数，**不能调用owner.call/submit嵌套排队**；所有工作仍在同一个既有owner调用内。

分别将研究API现有两种计算try/except提成固定局部helper并复用：

- universe guard：ValueError在_SAFE_ERRORS中→原code/400；其它ValueError→invalid_research_input/400。
- filter guard：ValueError在_SAFE_ERRORS或FILTER_ERRORS中→原code/400；其它ValueError原样再抛，交现成owner mapper。

两helper不重复owner的_STORE_CODES/HTTP状态公式，也不负责Store/文件异常。最终调用的边界位置也保持：universe guard只包报告计算，原inputs/parameters/envelope身份组装仍在该ValueError捕获之外；filter guard仍包整个filter报告（包括其组装/身份）。不能把整个新入口随手包进同一个guard。新的prepare捕获方式为：

1. 在短生命周期单源函数内，用相应route guard包住**纯prepare操作**，再交传入的_safe_store_call同步执行。
2. 只捕获该函数映射完成的既有请求错误类型（error参数当前为_RequestError），立即取其已有`code,status`两个普通值；退出except后不保存错误对象、args、cause/context、traceback、locals或捕获闭包。
3. 返回正常准备数据或安全错误对。错误对按逻辑阶段保留，**此时不抛给外层**，下一来源仍按原本读取顺序加载。
4. 在原阶段抛新的既有请求错误 `error(code,status)`。它不是ValueError，外层route guard不会二次改变code；owner对_RequestError原样传递。

读取/count始终在上面捕获范围外，出错就立即整体失败。不得把后源read错误存起来让前源prepare错误抢先。两个准备捕获区分别为_at_cutoff与normalize/coverage/window；header构造仅复制固定字段引用，其可信输入类型由现有读取负责。

故障注入必须核对：

| 注入到prepare的异常 | universe响应 | filter响应 |
|---|---|---|
| ValueError未知文本 | invalid_research_input / 400 | internal_error / 500 |
| ValueError已知safe code | 原code / 400 | 原code / 400 |
| NumericError('invalid_decimal') | invalid_research_input / 400 | invalid_decimal / 400 |
| StoreError('raw_object_corrupt') | raw_object_corrupt / 409 | raw_object_corrupt / 409 |
| OSError | storage_io_error / 500 | storage_io_error / 500 |
| duckdb.Error | database_error / 500 | database_error / 500 |
| RuntimeError/TypeError/AssertionError | internal_error / 500 | internal_error / 500 |

这张表说明故障映射兼容，不声明上述I/O类异常由合法行情自然触发。未知文本不会进入结果或延期记录。

BaseException（包括KeyboardInterrupt/SystemExit/取消）不被两个guard或现成_safe_store_call捕获。MemoryError属于Exception，可能已由现成安全包装器映射500；本方案不另加“识别内存耗尽”的异常框架，也不承诺资源耗尽时仍能继续读取、按业务多错次序完成。只要求任何已记录错误不转成成功/unknown，并如实记录灾难资源错误的未验边界。

### 4.3 固定裁决次序

参数/规则 → 全部count成功 → 判断预算 → 依序完整read（prepare结果暂存）→ 所有period → filter原前置（若适用）→ universe参数/全体身份/跨成员检查 → 依序全部selection_error → selected total → 每成员preparation_error与该成员指标 → 全组排名/广度 → filter全部source/contract/member/ID → 序列化。

“全部”阶段遇到其原有第一错误即退出，不意味着搜索更多错误。两个重要反例必须新增：前两源市场不符+第三源身份缺失，第三源身份错误优先；成员1公式错误+成员2normalize错误，成员1优先。

## 5. 实施次序与正确性门槛

独立批准后才可做以下工作：

1. 以第四片已冻结源码/发布commit作旧基线，另存仓库外只读参考；不stash覆盖并行工作。先写异常/全部响应/生命周期测试，确认候选入口缺失时合理失败。正式实现不刷新旧golden。
2. 先提取共享pure helper，在HTTP仍用旧加载时验证旧完整纯函数输出、逐成员多错顺序和现有筛选全部测试；这一步只改变结构，不宣称内存改进。
3. 接入两集合HTTP私有prepared路径及安全映射接缝，read/count外置。小规模全响应与旧基线逐字节比较，所有输入ID、fraction精确值、V binary64与原来源摘要保持。
4. 完整执行033 §8反例，额外以weakref包装rows验证“下一源read入口前上一源完整rows不可达”，包括selection错误、normalize错误、所有已知/未知映射，以及异常后Store重用。不得用强制GC掩盖返回对象保活。
5. 原件首次/重复/空前缀同长篡改、截短、删除必须失败；恢复后响应完全相同。batch checks验证顺序、全未定位计数、窗口外坏槽、token日期>D、duplicate跨位置与exact近阈值等完整来源边界全部对照。
6. 保留旧公开query/export和单股/双股回归。核对不在新API输出prepared/projection，不改变SAFE_ERRORS、owner码表、normalizer/numeric/Store公开方法AST。
7. 冻结最终代码/tests后跑全部Python回归；记录通过/失败/跳过、源码前后hash。现有49跳过继续为未验，不能把历史2200通过移作新版本证明。
8. 获准后依下节跑正式资源对照。独立实现审查通过且资源保留条件达到后才可保留该优化；否则停止/回退本片，不放宽来源或预算。

不要求本次重跑UI构建来证明后端内存；若API形状/前端合同发生变化，应判本片兼容失败并复审，不能顺带修UI接受新响应。

## 6. 预注册资源对照

本节尚未执行；启动正式大配置前再次向父任务确认运行窗口，避免与全仓测试、采集或其它重负载并行。未经批准不以smoke名义跑200k。

### 6.1 固定矩阵与基线

- 只做旧实现O和候选B，均测universe(U)与filter(F)，不加入A/A+B。
- 使用既有种子320261011的冻结合成夹具与规则：10×5,000、10×20,000、50×4,000；每组N20/252；保留缺D、重复、未定位成员及实际行数。旧文件不覆盖，新增manifest记录所有hash和实际源码commit。
- O必须运行冻结第四片代码，B运行待验最终代码，使用同一锁定依赖与同一只读输入；每个运行进程记录实际模块路径/hash，避免Python导入路径偷换基线。
- 源读取、每请求raw校验、完整规范化、计算和序列化均纳入ASGI完整请求。Store预先打开；系统缓存温热。无真实socket、冷盘或Windows资格外推。

### 6.2 延迟

每个配置启动两个长期子进程，分别固定导入O与B的源码，各自打开独立目录中的同一冻结合成Store副本；禁止两个Store打开同一root，也不在同一解释器热换同名模块。副本由已关闭且没有running attempt的冻结Store制作；测前数据库、manifest、raw等持久内容/hash逐项相同，仅root位置与.operation.lock排除。父进程按下列序列串行发命令，同一时刻只允许一个child执行研究请求；ASGI计时在各child内部从HTTP请求开始到响应完成，IPC等待和返回结果校验在计时外。child请求局部引用在下一命令前退出作用域，不保存完整query/oracle。每配置结束关闭两个Store及子进程，再作独立RSS观察。

测前后分别核对两副本原件长度/hash和公开完整query指纹一致；任何恢复工作、来源变更或运行中attempt均使该次基线无效，先修复夹具准备再另记运行，不以不相同来源作对照。副本仍保留Store唯一写入者和锁文件生命周期，不删除POSIX锁文件来绕锁。

每个配置四路O-U/B-U/O-F/B-F各预热一次，随后各5次，共每配置24次请求。正式5轮按以下序列交错，所有原始样本保留：

1. O-U、B-U、O-F、B-F
2. B-F、O-F、B-U、O-U
3. B-U、O-U、B-F、O-F
4. O-F、B-F、O-U、B-U
5. O-U、B-U、B-F、O-F

同轮同endpoint配对O/B；同轮B-U/B-F配对检查032增量门槛。报告每路中位及全范围、不删异常值；任何全配置复测另列为预先说明原因的一次完整复测，原失败仍保留。

### 6.3 RSS与对象生命周期

每个配置对四路各跑3个独立新进程，每进程只执行一次请求，不启用tracemalloc；PYTHONHASHSEED依次固定为`0,1,320261011`。共6配置×4路×3进程=72次独立生命周期观察。每seed的次序：

- seed0：O-U、B-U、B-F、O-F
- seed1：B-F、O-F、O-U、B-U
- seed320261011：B-U、O-U、O-F、B-F

RSS每次均使用独立exec启动的新进程和已关闭的匹配Store副本，不能采用上述长期warm worker的历史HWM，也不能fork继承已加载大夹具的父进程峰值。fixture创建、旧完整query/oracle和源不变性检查在正式测量进程之外进行；正式子进程不能持有baseline全queries或完整预期响应夹具。

每进程按原资格方式读取最终 `/proc/self/status` VmHWM，报告原始B和MiB及启动/结束当前RSS。一次请求的生命周期包含解释器/Store/读取/公式/序列化；不减去推测的基线占用。环境不提供此Linux指标时本项阻塞，不能换一个不可比指标冒充通过。

阶段RSS及tracemalloc另跑诊断进程，与正式延迟/RSS数据分开，默认先用小配置；需要追加200k诊断时另获准。阶段点至少覆盖import/start、Store open、预算后、每源读取后、单源准备helper返回后、全组计算后、JSON/请求后、Store close，记录VmRSS/VmHWM及可用时RssAnon。单源helper返回时的RSS不是请求峰值；阶段点无法看到所有函数内部瞬时峰值，不能用它替代正式VmHWM。tracemalloc须在请求加载之前启动，记录current/peak及追踪器自身成本。不得把152KB解释层局部测量代替全路径数据。

结构验收独立于RSS：进入下一来源read时之前来源的完整rows/tokens/checks已不可达；准备结束只留≤M(N+1) bars与header/coverage；延期错误仅code/status，不留异常/闭包/traceback。小型引用探针不得加进正式耗时。

### 6.4 保留与停止条件

全部正确性与最终全仓门槛先通过，再判：

- 两种名义200k形状、两个N、两个endpoint：B在3个配对hashseed的新进程VmHWM均低于O，并逐项公布减少的字节/比例及范围。小配置同样完整报告；若出现可复现增加，需解释和复审，不能隐去。
- 每个配置/endpoint的B完整ASGI中位≤O；每一O/B配对要求B≤O×1.15+20ms，用于限制单次明显退化。不能用降低内存遮住重复时延退化。
- 原032门槛对B继续独立生效：每seed的B-F减B-U VmHWM≤16MiB；5对及中位时间F≤U×1.15+20ms；新增解释层≤20ms；增量JSON≤256KiB、整体≤512KiB。原O的既有失败记录不因B通过而抹除。
- 全响应bytes/hash/全部身份与源原件/完整query指纹一致；结构门槛成立。每请求M次count/read/raw/bars和一次共享计算不能减少为抽样。

只降低Python可达对象而RSS未可复验降低，记录为结构收益、资源未达，不称本片资源通过。差异小到3组结果方向不一致也不宣布降低。任何语义/错误/原件/身份回归立即停止；禁止挑seed、重复到通过、加大16MiB、截尾源数据或加缓存救数值。

这套5次延迟样本没有稳定p95资格；原30次尾延迟项目仍单列未验。本片不保证交互SLA、并发排队、真实浏览器、Windows或预测/收益能力。

## 7. 编码前待审决定

请独立反方确认：

1. B直接落地及四个产品文件的窄边界是否可接受，特别是workbench仅传安全包装器的接缝。
2. §3共享职责是否保住pure和HTTP的不同准备时序，避免重复公式；filter所有来源组装仍在全体指标之后。
3. §4预映射code/status是否完整保留现有真实响应及故障注入响应，又不保留原query引用。
4. 反例/对象生命周期断言是否充分；resource耗尽的未验边界是否准确。
5. 固定旧/B、6配置、5轮延迟、3seed×4路RSS的保留条件能否授予编码后验收资格。

批准之前本文件仅是计划。此次文档修订及小探针不代表候选B已实现或性能通过。

## 8. 作者对R1–R3的逐项回应（已复核关闭）

- **R1接受并修订。** 删除033初稿的exception-family重建候选；§4.1区分正常可达业务失败与故障注入，§4.2明确route guard→现有_safe_store_call→只存code/status。workbench仅增加一处依赖传递；无新码表/registry，无纯模块HTTP依赖，read/count在捕获外。MemoryError遵循现有映射且不承诺灾难资源下的多错推进；BaseException不捕获。
- **R2接受并补齐。** §2列完整header（包含batch_id），§3给出pure逐成员惰性准备与HTTP小prepared列表共享同一指标/汇总、同一filter组装的边界，§4.3冻结全部selection与逐成员normalize→metrics屏障。§5先锁反例与弱引用生命周期，明确迁移spy不得减少合同断言。A未纳入本片；033已补其fetch与JSON复合故障顺序反例。
- **R3接受并预注册。** §6采用old/B两臂、六配置、每路预热+5次交错时延、三固定hashseed共72个exec新进程RSS，明确执行次序、两个版本长期child各用独立匹配Store副本的时延拓扑、独立exec单次RSS、基线独立物化和方向性保留条件。保留032全部原门槛及失败。正式生命周期VmHWM不插tracemalloc；更细阶段RSS与Python分配另作诊断，避免额外插桩改变正式比较。追加大配置诊断仍先确认运行窗口。

本回应只修订研究/计划，没有修改产品或测试，也没有执行候选实现或新200k矩阵。独立反方已依据修订全文关闭R1–R3并批准候选B；实际开工与正式性能窗口由父任务另行安排。


## 9. 执行结果与后验分阶段决定（08:03 UTC）

原§6的冻结顺序、全部样本和阈值均按计划执行，正文不回写。最终2301 passed/49 skipped，Node128、TypeScript/build及60真实配置/260 ASGI通过；正式24预热+120计时+72新进程RSS完整结束。36旧/B绝对峰值全部下降、60旧/B时延对及12中位通过；原032筛选RSS增量18对中4对失败，原整体保留条件仍为 **failed**。完整值见[本片资格](../qualification/research-memory.md)。

[独立最终审查](../reviews/2026-10-11-research-memory-review.md)重算原始记录后建议新增分阶段保留。主方于 **2026-10-11 08:03 UTC**接受：保留已验证的共享内存/时延收益并准备发布B，同时将筛选增量RSS明确列为 **failed/open**。理由是绝对峰值在所有36对中下降且功能/来源/身份不变；回退会恢复较高驻留，旧版增量门槛也未通过。

这一发布取舍是测后新增的工程决定，不能伪称满足本计划原先的全部保留条件，也不删改§6.4或提高16MiB。仍不保证尾延迟、Windows、浏览器、并发、预测或更高预算。来源与错误合同、四产品文件及测试继续冻结；没有追加重复矩阵或大阶段剖析。后续开放项另行研究与审查，不能自动重跑到通过。
