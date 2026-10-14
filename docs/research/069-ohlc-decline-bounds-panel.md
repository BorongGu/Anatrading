# 069 候选：OHLC 跌幅范围的单窗 API 与日线面板

2026-10-14 UTC。设计 v1，待独立反方审查；不授予编码准入。
基线 main `b89b2fae479354ad6d8121af3ab4670957ac1232`。仅在仓库外编写本文件，未修改产品或发布。核读 AGENTS.md、068 research/qualification 与完整核心、065 research/qualification、research_api.py、SelectedCloseDispersion.tsx、selected-dispersion.ts、App.tsx 与字体样式。没有旧数据库、真实捕获或行情读取。本片无需另行论文主张，完全暴露已审查068数学，不新增统计模型。

## 1. 决定与价值

选择一个独立、按需、明确起止日期的日线面板，调用一次单窗 HTTP 入口。让用户能够对自己选定的来源日期窗看到：只看收盘遗漏了多少必然源价跌幅，以及 OHLC 内部次序仍留下多少歧义。两端日期必须确实存在，窗口最多253个来源日期组。它服务回顾性数据解释；不输出风险评分、预测或买卖信号。

比较三种小方案：
- 仅原始 JSON/分数：实现最少，但日常难读，来源拒绝也不易理解。不选。
- 独立折叠面板，两个日期，范围/收盘参照/资格/精确详情：无需图表新交互，含真实用户完整路径。选择。
- 在价格图上画两条极值路径或阴影：容易让假想顺序被误认作市场路径，需要第二坐标与日期关联设计，本片排除。无图形拖选、全历史扫描、批量报告、排名、导出、缓存或新框架。

有两个不同完成门槛：合成 API/React 功能可完成；真实浏览器视觉与操作验收必须有实际浏览器证据。jsdom通过不升级为后一项。真实行情兼容、PIT、复权、完整日历、最终收盘、Windows、金融价值继续未验，实采 NO-GO 和既有科学 STOP 不变。

## 2. 用户流程与中文展示冻结

位于现有“个股研究”日线区域，和 SelectedCloseDispersion/SingleResearch 平行，直接接收父 Query；SingleResearch失败不阻断。标题“OHLC 跌幅范围”，展开按钮“选择来源窗口”。仅 retrospective + 1d 可提交；其他模式明确“仅支持回顾性日线来源”。初次展开不发请求，起止日期均为空，避免把可见/裁剪数据擅自当默认研究窗。填写“起始来源日期”“结束来源日期”，点击“计算这个窗口”。start=end允许；无需两个收盘价。

父图形截止若非空，end不能晚于它；父图形截止为空可选任意有效日期，实际缺端点由服务端报告。显式提示：“本次分析截止：结束来源日期。使用该截止内完整来源前缀核验；图形记录序号范围不裁剪研究窗口。”不沿用065的“查询截止不变”。end只是分析截止，不修改父图形选择，也不声称该日历史可得。

结果先显示已请求/已定位的起止日期、日期组数、源身份简写及完整身份入口。成功主区：
- “兼容路径的最大源价跌幅：下界 …；上界 …”，无概率/置信区间用语。
- “收盘观察参照 …”。解释：“只观察各日收盘可能漏掉日内及跨柱的跌幅；本窗从首根开盘开始。”
- “次序歧义宽度 …”。identified=true：“上下界相等；这个跌幅数值已由供给 OHLC 确定，实际路径仍未确定。”false：“盘内先后未提供，保留上下界。”
- 范围下方始终展示：“仅约束已提供柱的兼容路径。若有漏柱，不能作为完整真实区间的上界。交易日历、复权与公司行动、历史可得时点及收盘闭合尚未验证。源价跌幅不等于财富损失或可成交收益；无预测结论。”

展示采用精确分数为权威，提供易读百分比。仅一个有界 BigInt 展示函数，无 Number/parseFloat 价格转换：n=0显示“0%”；0<n 且 n*1,000,000<d 显示“小于0.0001%”；其余按 n*1,000,000/d 半入舍入到4位百分数，明确前缀“约”，显示值不参与排序、相等、资格或证明。每项就地显示/展开 n/d；接近1的值可舍入成“约100.0000%”，精确分数仍<1，不能说实际100%跌幅。width同样处理。冻结相邻大格点与循环分数测试，绝不把极小正值显示为数学零。

两个闭合的“假想极值证明”详情，分别说明 O→L→H→C / O→H→L→C；只列峰/谷对应来源日期、槽位、精确价格与原序号。必须在每份详情标题与端点前标“假想”，不造时分秒、不画成真实路径、不把来源日期当极值实际时刻。零值 witness=null，显示“无正跌幅见证”；close-only见证称“收盘观察峰谷”，不套假想盘内槽位。全体≤253成员表默认收起，展开后呈现全部；OHLC为规范源值，标明“规范精确值；原始 token 未嵌入”。重复日期无唯一序号，通过完整query身份与日期回查，不伪造一行。

unavailable呈现主原因、完整原因列表、来源资格和全部失格成员，所有数值卡及见证均不存在；不显示0、不保留旧数值、不跳坏日继续。原因必须有人话：来源隔离/代码冲突/复权冲突、来源日期覆盖未知、起止来源日期不存在、窗口有失格日期组；详情保留原因码、全源首冲突计数、未评估后续判据声明。计数统计单位不同，不求和成异常总数。

网络、超限、非法JSON/DTO等操作错误使用alert并清空结果；“读取失败，请检查日期或来源后重试”。非法报告不显示部分身份/数值/成员，日志不得带真实数据。取消仅废弃UI采纳，已开始只读owner工作可能继续。加载有状态文案，提交期间禁重复提交，取消/关闭可用，失败后可重试。

沿用panel、section-heading、metric-grid、table-scroll、details、按钮与色彩。不新增图表依赖、字体下载、动画、全局视觉改版。局部中文正文字体栈明确 PingFang SC/Microsoft YaHei/Noto Sans CJK SC/Noto Sans SC/WenQuanYi Micro Hei/system-ui/sans-serif；标题沿既有宋体风格但具Linux Noto Serif CJK SC回退。不要把整段中文交给代码等宽字体。长分数/身份可断行，成员表仅自身横向滚动；屏宽390及1280px、200%缩放无整页横溢。键盘焦点、label、aria-expanded、status/alert无需颜色猜测。

## 3. HTTP、可信读取与内容绑定

新增 GET `/api/research/ohlc-decline-bounds/{snapshot_id}?start=YYYY-MM-DD&end=YYYY-MM-DD`。start/end都必填且各一次；无默认日期。拒绝未知/重复参数，包括cutoff、ordinal_start/end；校验64小写十六进制snapshot、严格合法ISO日期、start<=end，均在Store调用之前完成。父截止限制由UI上下文执行；HTTP合同仅承诺所请求end全前缀，不把caller自报父查询当认证。

在现有owner内，复用 `_load(store,[sid],end,error)` 的行预算/完整可信读取与原件核验，再且仅再调用 `decline_bounds_report(query,start,end)` 一次。可信研究Query必须retrospective、cutoff=end、ordinal限制null；不把图形q.rows传给核心、不用图形行数做来源预算、不给空结果绕过原件核验。全部已供给前缀行含unlocated≤20,000；原件校验与NULL-label已有披露不变。不可将请求start先裁掉，再检查来源冲突/覆盖。窗前普通坏价不阻断局部合法窗，窗外全局冲突/未知日期仍关闭；测试沿068。

原068结果字段全部保留，新增 view_method_id=`selected-source-ohlc-decline-bounds-v1`、analysis_id。沿用store._identity，但这次输入是完整报告（含view_method_id，唯一排除analysis_id），而非仅snapshot/query/日期。绑定精确members、资格、coverage、结果/见证、所有方法ID与选择；同query_id却资格/成员内容改变必须变ID。这是本地结果内容标识，不是签名、授权或PIT认证；不建缓存、不在客户端把ID本身当正确性证明。相同完整内容重复请求ID稳定。核心report无需修改其数学或现有身份合同。

固定安全错误白名单涵盖 invalid_decline_query、ordinal_window_not_supported、ohlc_window_limit、ohlc_metadata_limit、ohlc_result_limit及现有日期/期间/行数错误。超253组拒绝整调用，不能裁至253。日期缺失是正常200 unavailable并保留missing_endpoints；坏结构、元数据/载荷超限是受控非2xx错误；保留现有框架错误状态与安全映射，不泄漏exception。底层内部算术错误不能被当作computed/unavailable成功报告。

沿用现有no-store、Host/Origin、单owner、只读Store与安全错误边界。无新增socket权限、公开部署、后台读取或真实采集。

## 4. 端到端有界输出与客户端接受条件

核心已有限身份投影16KiB和报告256KiB；HTTP新增字段也计入262,144字节上限。复用065同样的局部有界JSON编码思路，固定本入口限额与错误码，不为此抽通用框架。在owner内先有界遍历报告树/字符串，再绑定ID并一次紧凑UTF-8编码，累计超限立即停止；同一最终bytes交Response，不重新JSONResponse编码。不能裁短qualification/reasons/members。现有核心内部完整序列化仍存在，本片不虚称全链流式；资源观测包含它及hash/最终编码。HTTP最终超限分支必须动态边界测试，修复068只有静态确认的缺口。

前端所有响应含错误均按262,144字节流读取；不得依赖Content-Length，检查虚报/缺失/超大header与实际分块；UTF-8 fatal解码、非法JSON拒绝，取消释放reader。有限结构/深度防护先于递归clone/freeze；本入口JSON最大深度64、结构节点≤65,536，超限受控 invalid_query_response，不改变核心资格语义。若发现原本合法资格超过此接受合同，报告受控错误，不悄悄省略。服务端对应成功输出也执行这两项限制，避免发送自己客户端不能接受的成功体。

DTO按068完整字段写专用validator；不机械复制065，因为ordinal在068是0..2^63−1精确字符串、包含0，selection无snapshot_id字段，且source_qualification不是065三态qualification。验证：
1. 固定method/adapter/numeric/view IDs、scope、path_ids、所有必需limitation、source-conflict policy与未评估声明；analysis_id为64hex。
2. snapshot/batch/raw/contract与本次父来源匹配；query_id非空且≤256 UTF-8字节，不强求等于图形ownerQueryId。identity.selection恰retrospective/cutoff=end/ordinals=null；请求/解析start/end、bar_count及首开盘初始化一致。source_qualification与identity副本一致并与本次父manifest资格一致；来源声明/symbol_identity按既有映射核对，不自创代码含义。当前资格无法协调时整份拒绝并提示重新读取数据版本，绝不接受旧缓存。
3. members≤253，index从0连续，日期严格递增且在[start,end]内，已解析端点必须实际在members对应首/末处；missing_endpoints恰为缺失请求端点（start=end只列一次），resolved值只可原日期/null。bar_count=members.length。价格是规范DECIMAL(38,18)精确字符串/null；合格成员均严格正且OHLC几何合法。ordinal按字符串解析为BigInt，范围/重复/失格规则依068；duplicate_date必须null。不用Number表示ordinal或价格。
4. coverage计数有界且自洽；invalid_members与members首因逐项全等；reasons去重并保留主reason；source_rejected、全源冲突计数、未知覆盖、缺端点、invalid_window按068优先级闭合。computed只在无上述拒绝条件时；unavailable所有五个结果字段必须null，不能夹带见证。全局冲突顺序沿服务端首见顺序，不强制排序成另一主因。
5. rational为规范非负整数字符串、正分母、gcd=1；边界/close最多38位，width最多76位，零必须0/1。使用有界BigInt交叉乘验证0<=close<=lower<=upper<1、width=upper−lower、identified精确等价。不以显示相等代替。
6. 非零bound见证hypothetical=true/path_id正确；slot、bar_index、path_position与规定槽序对应，peak位置<trough位置；date/ordinal/price_exact严格映射members；(peak−trough)/peak与该bound有理数相等。close见证仅收盘索引，先峰后谷、价格/来源一致。值0时见证必须null。DTO不声称重新证明全局极值或择早；那由已验核心与独立oracle保证。客户端验证不重建路径用于图表。
7. 完整接受后深复制并freeze。任何失败整份关闭，无局部卡片。来自可信API的报告含原样已核来源证据；客户端不能通过相同ID认证任意字典。

## 5. 生命周期与无旧结果

采用065的局部context/request-generation/AbortController模式，独立文件组件，不侵入SingleResearch。上下文包含ownerQueryId、snapshot、batch、raw/contract、period/mode、父cutoff/ordinal范围、来源代码/市场/复权声明/interpretation、隔离/known_negative_sample与manifest资格。普通显示名称不触发研究重置。start/end是另两个绑定键。

上下文/任一日期变化时立即invalidate并abort；渲染本身先核当前context+dates+generation，首个render即隐藏旧结果，不能等useEffect才清空。父上下文变化后面板关闭且日期清空，必须在首个commit生效（局部以contextKey作为组件key或等效同步render门卫）。关闭、取消、卸载废弃代次；A/B乱序、同ID上下文突变、重复提交都不能采纳旧回应。取消后保持当前日期可重新请求；重新打开不恢复旧对象。任何父source change后旧callback不能重开面板。无结果导出。

## 6. 编码前冻结验收

所有测试只用新合成fixture/临时Store。先异常测试红灯，再实现；任何改变以下成功定义需独审，不事后放宽门槛。

A 数学/展示：068固定十例原期望保持，重点单柱(100,120,80,100) lower=1/5 upper=1/3 close=0；跨柱identified例；常量0跌幅witness=null；极小正有理数不丢失；循环分数、近1、零宽、最大76位width精确往返。反例缺失中间柱的0上界仍有常驻警告。新接口结果剥离两个HTTP字段后与直接068报告全等。

B 请求/Store：缺/重复/未知参数、日期不合法/start>end、非日线、错snapshot、20,001行、0/1/253/254日期组；预检失败不得调用读取。真实临时合成EvidenceStore只读路由：原件缺失/篡改、空查询仍核验，恢复后库与原件hash不变；完整前缀与图形ordinal裁剪身份分离。缺任一/两个端点、相同端点缺失、日期缝隙均不邻近替换。

C 资格：全源窗外代码/复权冲突、隔离、unlocated及未来NULL-label披露、重复日期、无唯一ordinal、普通窗外坏价、所有窗内坏成员、坏volume/amount不额外失格。截止=end固定，后加全局反证可撤资格，不能误用未来数值不变性掩盖；报告不得宣称历史时点资格。

D 内容身份：相同完整报告同ID；不同start/end、raw/contract、资格、成员、原因、coverage或结果异ID，即使query_id未变。客户端拒绝每一种错配/遗漏、非规范有理数、非约分数、0分母、顺序/差值/identified矛盾、错误槽位/日期/ordinal、伪hypothetical=false与unavailable带结果。API安全错误和DTO非法报告均不渲染残留数字。

E 字节/结构：最终HTTP体恰上限成功、超1字节失败（通过可控资格/测试编码器夹具定位，不改数学期望）；UTF-8中文、多字节与转义内容按实际字节，资格不得裁剪。头虚报/缺失、chunk越界、非法UTF-8/JSON、depth65/nodes65537受控拒绝。实际同一bytes发出；原核心限额与新增字段导致HTTP超限分别覆盖。

F 实际ReactDOM：按需零自动请求；两个必填日期、start=end、父截止约束；独立面板不依赖趋势模型；loading/取消/关闭/重开/卸载/重复提交/错误恢复；A晚于B、同owner ID但每一来源资格/截止/ordinal改变；Profiler或commit探针证明首commit无旧数值/旧资格。改日期尚未提交即隐藏旧值。展示所有253成员、长分数、全253失格原因；警告不因identified=true/全零消失。

G Linux实际浏览器（独立准入门槛）：仅在同一授权本地服务运行环境，以已支持无头浏览器访问临时合成应用；不绕过既有浏览器或socket拒绝。须记录浏览器版本/viewport/字体实际解析结果，1280×900与390×844及200%缩放；截图成功range、identified/zero、unavailable、错误恢复，检查中文无方框/重叠、精确长值不溢出、表格局部滚动、焦点及keyboard展开/提交/关闭。浏览器执行快慢A/B与关闭晚到流程，截图/DOM共同确认无旧值。新布局无主线程>200ms长任务（受控253成员展开），加载耗时单列不含网络承诺。若浏览器/服务不可用，记录BLOCKED，继续API/DOM但不称UI视觉合格；jsdom永不替代截图。未经许可不下载浏览器。

H 回归：受影响Python/API/068全套；Node DTO与实际ReactDOM、TypeScript/build、现有允许产品全套；既有真实socket禁止重试项继续明确未跑，私有样本/Windows skip不能当通过。不相加重复测试数为新样本。

## 7. 冻结资源观察与停止条件

无需跑全历史数学。最多一次decline_bounds_report；computed exact_bounds=1，unavailable=0。rows≤20,000、members/invalid_members≤253、身份16KiB、最终HTTP256KiB；核心O(m)，全前缀排序O(n log n)/内存O(n)，不宣传全链O(253)。

实施后单次独立子进程矩阵：空源、单柱、253最大/最小格点、253全失格、20,000行末253有效、20,000行含全局冲突/无法定位。每例全进程峰值RSS≤256MiB（含API/native导入与构造fixture，不减基线），CPU≤20秒、墙钟≤30秒、最终256KiB；虚拟地址另记，不复用065失败的256MiB RLIMIT_AS承诺。CPU/墙钟硬限；RSS高水位及watchdog是观测/尽力终止，不说OS硬隔离。Store stub适配器资源与真实临时Store/进程内ASGI功能分开报告。统计读取/报告/绑定编码分段及全进程总量，但不把单次当稳定延迟。任一超限失败即停接线，先独审优化，不能提高预算重试或少测难例。

设计成功：独审确认日期/可信完整前缀、内容绑定、有界精确输出、资格/失败闭合、渲染失效与浏览器门槛足够清楚。最小下一步：独立反方核读本文和现行068/065，对完整最终文件给GO/改动；GO后先写API前置拒绝与DTO错误红灯，再实现窄路由/面板。浏览器门槛单列保留；不要因浏览器暂阻而冒充验收，也不因此重启真实采集或扩大产品范围。
