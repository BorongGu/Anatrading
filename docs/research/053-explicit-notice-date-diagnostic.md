# 053 有限公告日期核对（051独立附件）

2026-10-13，编码前冻结，基线main f5fb121。已读AGENTS、049/050/051、完整来源查询/扫描及051 DTO/前端校验代码。独立反方复核实际代码后有条件准入；固定以下边界，不把编码准入当作实现验收。

## 目的与简单基线

051原来核对所选日期数组相等；相同数组仍可能共同没有某个公告明确开市日。人工读公告逐日期比对是基线。附件列出具体日期、成员和官方出处，帮助决定回查哪个原版本。未实测人效，不认证供应商漏日、实际开市、必须有成交或投资增量。

仅051加默认折叠区，原DTO/API、121日期组/120来源区间/两60窗、全部成员、analysis_id、原失败和PIT/量额资格不改。不做完整日历、周内/调休推导、其它入口、行情重抓、Store读取/写入、填补、通用平台。静态版本JSON随前端发布，无新后端接口或参考网络请求。公开仓只含派生事实，不含原件HTML、私人审查记录或抓取日志。

## 官方阅读及独立审查记录

归档研究于2026-10-13下载官方通知原始响应正文，独立审查核对原HTML日期、文号、发布声明、范围及抄录。本实现者读取研究与审查结论及其精确hash，未声称重做原件全文审查。

- [SZSE2024](https://www.szse.cn/disclosure/notice/t20231226_605108.html)，深证会〔2023〕409号，正文2023-12-26；原字节SHA256 `2c9906bac2116f3bc6190f0d0a74e0be40f1e4307f71e34cc12007d411e88b13`。
- [SZSE2025](https://www.szse.cn/disclosure/notice/t20241223_611283.html)，深证会〔2024〕413号，正文2024-12-23；原字节SHA256 `1c89289137907b6afd00c27059919dedcb8414f4402a38b995ff9eccd465874e`。
- [SZSE2026](https://www.szse.cn/disclosure/notice/general/t20251222_618087.html)，深证会〔2025〕481号，正文2025-12-22；原字节SHA256 `1656d8708d5faed33c7588538639d96128f39fdface02cfa6eb66d796c40f14e`。

独立审查接受有限事实文件精确SHA256 `d667d14bd1c6a761aef53a8a6ecf9c412e996211b45518eb58a967f815ccc541`；独立审查记录SHA256 `c3d0a3ce5087b6f9e2973deea084d8d6c29f50f9a37e323df60d82c184b640a7`。审核11份原件/17抓取记录；产品仅采用以上3通知的有限事实。原事实文件为保hash保留pending文字，另立审查按精确字节接受；产品不按未核布尔标记准入。

范围2024-10-11—2026-10-09，Asia/Shanghai，72个明示SZSE闭市日期及13个命名恢复开市日。SSE没有本包事实。起照常开市只生成命名首日，临时事件/更正全集、实际交易、个股状态、历史as-of未知。声明发布日不由URL替代。原件hash记录归档字节身份，不证明历史未改；运行时仅核验本地派生manifest形状和冻结hash，不重新读取/认证官方原件。变更原件须重新归档、审查并发布新包。

## 实际合同及保守适配器

现有路由使用完整`_research_query(...cutoff=None)`；`_source_header/_source_counts/_group_structure`要求完整回顾selection、计数、身份、格式和行结构。`_scan`扫描rows和unlocated，先归日期slot；`_member_window`取最后121组，再检查价格。完整anomalies.counts保留，examples截20条。只认现行051方法/规则版本及严格validator通过的响应。

- exchange只由source_qualified=true、evaluated、规范SH/SZ且无全来源global_source_conflict的symbol映射。拒绝来源fallback symbol/全局矛盾为N_unknown，全部成员保留。这仅核对来源声明，A股/日期基准仍assumed，未认证证券主数据。
- presence保留可靠日期，即使坏价格或重复端点ordinal=null；unlocated_endpoint/missing_endpoint不算可靠。完整counts含local_source_conflict/source_date_range/unclassified_source_failure，保守关闭成员日期证据。其它无法定位行不抹去明确可靠的已有日期。
- absence仅在非空date_array的[first,cutoff]且last=cutoff，完整counts无endpoint_integrity_unknown/unlocated_label/label和上述阻断，端点无unlocated/missing。否则span=null。first以前、空数组、拒绝源不能判absence。history_insufficient、坏价、重复、常量不单独阻断。
- counts用Object.hasOwn和正整数检查，不能因raw诊断包含原型键误判。若发现上游会先删行仍通过完整查询，停止absence准入并报告精确路径，不恢复坏源或新造完整性字段。

## 比较、身份与预算

先定W：全部原非空数组最早first（不按成败筛选）至原cutoff，再限manifest范围；全空取manifest起点。不取成员交集，不改原窗，各成员保持自身absence span。每所N_e和N_unknown和为N。候选明确“交易所声明已核为该所的N_e个成员”，另显未知身份人数，不称全原组缺席。

同向同日去重并保留证据；相反事实conflict，不按发布时间/抓取时间覆盖。v1不自动处理更正，须重审active事实集并新版本。每cell P+A+U=N_e。closed且P>0列计划差异；open且A=N_e>0列所内候选，N_e=1单数；部分缺席保留，U>0不全体。N_e=0不比较。无跨所共同缺日、通过章、质量分或完整率。零可比单元显示未评估。

附件ID绑定独立规则、原report分析/版本/参数、W、排序全部snapshot/batch/query/symbol、资格、日期、原reasons/完整counts/端点date+reasons、适配结果、manifest版本/hash。原analysis_id未覆盖所有日期可靠性，不能仅凭它缓存。价格数值不参与匹配；合法未来价格不改同日期投影，身份反证可撤销资格。原报告不修改。

原051<=2MiB、2–50成员、每成员<=121日期；manifest<=128KiB、notice<=16、事实<=128、scope<=800天、闭区间<=31天、open单日、URL<=2048、文号<=128；<=1600所日期cells、40000成员状态、附件<=2MiB。展开前检查，超限整附件拒绝。严格10字符有效ISO日，不作时区移动或宽松解析。完整差异保留，UI50行分页只限渲染。

## 17项反方答复与先测异常

1. 一所一条事实可用，其余未覆盖，缺周内规则不阻断。
2. 命名恢复只产一天，不推次日/周末。
3. 跨月/周末闭区间含端点，无调休覆盖。
4. 同向去重，相反conflict，不按“最新胜出”。
5. 日内/个股/港股通/另一所不得纳入本所全日事实；语义须人工独立审查。
6. 合成共同漏内部open给候选，原121/两窗/ID不变，不加第122点。
7. 自身first以前unknown，不交集；cutoff缺失保守无absence。
8. 可靠坏价/重复仍presence，原失败保留。
9. 第21条后未知日期用完整counts阻断absence，N保留。
10. 逐所分母；缺参考不拖另一所、不算通过。
11. N_e=0不全称真；N_e=1单数；N_unknown始终显示。
12. 空数组无absence，空证据无成功。
13. 仅当前证据回顾，不产生known_at/PIT。
14. W外事实不改W内行，换参考新ID；身份反证可撤销资格。
15. 置换排序稳定，P+A+U恒等，预算超限不截断。
16. 非法/超长/反向ISO拒绝，不移动日期。
17. 同analysis_id换参考/可靠性仍换ID；本地manifest变动hash失败。运行时不重验官方原件，明确披露。

默认折叠，无参考网络请求。异步SHA取消/版本保护，关闭、换报告、卸载后旧结果不发布。回查按钮“打开该版本截至此日”，缺席日可落在较早源终点，不冒称当日端点或自动聚焦源序号。

## 实际验收（编码前）

已完成设计、代码阅读和归档独立审查；未实现/测试。后续填写真实测试结果。计划新异常、051相关Python/Node、TS/Vite、SSR与异步失效测试。没有授权本次读取真实行情/Store。浏览器、Windows、真实样本、性能、人效、金融效果不能用SSR/合成结果替代。

## 2026-10-13 第一实现候选验收

先写异常测试后首次运行因待实现的notice-date-model模块不存在而RED；随后实现并补全边界/SSR测试。全Node首次回归发现本新增文案“快照”违反既有语言检查，改为“公告参考”后重跑最终版本。

- 新公告模型/界面测试42通过；含18份Python实际生成的合成051 DTO、手写72闭市/13恢复日oracle、失败/未知/坏价/重复、置换、未来反证、原对象不变、参考篡改、预算、分页及完整版本ID/截止回调。
- 最终全Node740通过、0失败、0跳过；TypeScript/Vite通过。原有npm http-proxy提示与主包超过500kB警告保留（本候选822.38kB）。
- 051纯算法Python针对性24通过；未跑完整Python/真实市场样本/现有Store。既有Node回归自己的临时合成库与本新增纯内存DTO严格区分。
- 派生公开manifest逐notice八个事实/来源字段与hash钉住的审核事实文件完全一致；本地manifest canonical SHA256 `f3ad5c46bde683f3d713259e2aa35166f7469296956d7cc82538734c60a90264`。
- 原051后端、API、私有源扫描助手及前端DTO/校验模块与基线无diff；仅GroupPairResults增加import和独立折叠组件两行。
- 独立代码审查与模拟DOM交互验收尚待最终记录。SSR不是浏览器验收；真实浏览器/截图、Windows、真实样本、性能、人效、预测/交易效果均未验。没有提交外部PR/推送/部署。
