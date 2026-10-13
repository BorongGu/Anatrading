# 065 有界单日期收盘离散入口：编码前冻结设计 v2

2026-10-13。只读基线 main a79a8768fd56c8174d7ae678e3f9ec001c51a72b，工作区干净。无产品修改、测试运行、测量、安装、联网、行情/Store读取。本候选尚须独立反方审核；设计 GO 不代表实现或实源资格。

## 决定

GO：提供按需的单个来源日期窗口；NO-BUILD：完整离线报告直接上 HTTP、先计算完整报告再截取、前端重写数学、分页/摘要框架。当前最小用户价值是查看某日及此前19个可读来源日期组的精确描述并核对全部成员。日期输入使任一已有日期可达，不需要预装所有日期列表或20,000条结果。

比较：
- 现状离线纯核可审计，但用户在现有应用没有入口，不能满足用户可访问目标。
- 全报告+硬拒绝最少接线，却使已观测的20,000有效/全失格数据均无法使用；输出13,252,068/39,557,697字节，不能作为可接受默认。
- 有界页/范围可提供历史浏览，但需要位置范围身份、前19项halo、翻页状态与多窗计算。对查看指定日期并无必要；暂不选。
- 摘要+详情需定义全历史摘要，至少双层身份/请求及重复完整前缀读取，并引入尚无用途的新摘要语义；暂不选。
- 选中日期单窗仅1次精确计算，最多20成员与20失格成员；全前缀来源资格仍沿用。接受每次O(N log N)日期分组排序和O(N)来源核验，不宣传O(20)端到端；不增加缓存、队列、SQL窗口投影或通用框架。

## 接口与纯核复用

新增 GET /api/research/close-dispersion/{snapshot_id}，仅可选 cutoff 与 date 参数；沿用现有参数解析拒绝未知/重复参数。snapshot为既有64位小写hex，两个日期必须严格ISO真实日期；date>cutoff在读取前拒绝。date缺省表示“当前查询前缀最后一个可读来源日期组（包括失格、重复及从原token恢复日期的无label组）”，输出显式记录此选择策略及实际日期。显式date必须完全命中已有日期组，缺失返回有来源身份的 unavailable/date_not_present，不自动向前替换。零日期组返回 unavailable/no_date_groups。cutoff缺省保持None，与现有全前缀查询相同。

沿用 owner.call / safe_store_call / _research_budget / _research_query，20,000源行预检先于加载；unlocated行计入预算。每次仍验证原件，包括空查询；保持read-only Store兼容和既有唯一owner，不打开第二Store、不修改权限或数据。_research_query 的私有投影不得原样返回。

在 close_dispersion.py 中最小抽取共享“一个位置的窗口结果”及报告公共头部，旧dispersion_report逐位置调用同一投影，新selected_dispersion_report只调用一次。daily_bars/daily_coverage/_request和exact_window继续是唯一来源/算术实现。旧报告JSON必须逐字段完全不变；新入口不得调用完整dispersion_report，也不得构造全series后截取。若共用头部抽取造成广泛改动，允许极小字段组装复用，但不能复制窗口状态优先级、数值公式或边界舍入。

新返回：固定view_method_id=selected-source-close-dispersion20-v1；原method/adapter/numeric IDs、完整核心identity、parameters/coverage/qualification/units/limitations均保留；selection={date_requested:null或日期,resolved_date:null或日期,policy:latest_source_date或exact_source_date}；selected为旧报告对应series行（缺失时null），members为至多20条{position,date,ordinal,close,source_reason}。空/未命中有明确顶层status/reason，数学结果不借用其他日期。有效命中时selected的status/reason原样保留。允许invalid_members与members内原因小量重复，维持旧行全等，最坏仅20项。

分析身份在HTTP边界用现有store._identity封装，绑定view_method_id、核心method/adapter/numeric IDs、实际完整前缀query_id/snapshot_id及请求date选择（含None语义）；不新增通用哈希。保留原core identity的batch/raw/source_contract/qualification。相同快照/截止/选择重复请求身份稳定；不同截止即使末日期相同也不能混同。原query_id保持可信Store完整前缀身份，不伪装为任意图形ordinal子范围查询身份。

## 语义保持

严格正价daily_bars完整OHLC资格；数学零接受和来源零拒绝分别验收。坏OHLC、来源代码/复权冲突、隔离、重复日期、可解析日期但无label、完全无日期的来源披露都不改变。当前及前19日期组，首19不足优先history_insufficient，完整窗任何失格为invalid_window，全部失格位置/原因保留；不跳过、不填充、不压缩。无日期行使coverage未知，不虚构具体坏窗；日历完全缺日仍不可验证。

均值/方差与原源价保留精确文本；三个数值区间lower/upper/exact/display/display_reason完整保留。只显示服务端已证明可舍入的display；null/ambiguous时给“显示舍入未定”和可展开精确端点，不取中点、不JS Number重算。负下界保持；0.0000不解释成数学零。文案为20个来源日期组、总体方差、均值±2σ，明确数值界非概率区间，无买卖/预测/95%覆盖/交易收益结论。

## UI与并发身份

在现有单股日线区域增加独立折叠面板/组件，父Query直接传入；不依赖SingleResearch模型请求成功，不自动附加到旧默认响应。展开/提交才请求；日期为空时清楚标为最近来源日期，可输入其他日期并明确“查询截止不变”。显示均值、σ及上下界，精确详情和至多20来源成员；无新增图表、批量导出、排名或全历史摘要。

捕获ownerQueryId、snapshot_id（任何sourceId必须只作该字段的已验证别名）、batch_id、cutoff、ordinal_start/end、generation和请求date。返回核对snapshot/batch/cutoff、前缀selection无ordinal限制、固定IDs、请求选择、结构/计数/成员连续位置/日期与selected窗口、失格清单和结果空值一致性。不把图形ownerQueryId强制等于研究全前缀query_id：图形ordinal裁剪可以不同，明确说明计算完整前缀。

来源/批次/截止/ordinal/date改变立即清空与invalidate并abort；相同ownerQueryId却上下文改变亦如此。Close/Cancel/unmount废弃代次，不允许晚到响应重新打开或替换；重复点击仅一个活跃代次；旧sourceId的回调失效。取消只保证UI不采纳，现有owner中的已开始只读工作可能完成，不声称服务端计算已终止。若加导出，只导出当前已核单窗口DTO，不在本最小切片实施。

## 先冻结的资源预算与测量门槛

业务硬上限：20,000源行，20成员，20失格成员，每次至多一次exact_window。成功HTTP完整响应（身份、资格、包络均计入）UTF-8紧凑JSON<=65,536字节。超过则整份拒绝dispersion_result_limit，禁止裁短资格/identity/成员。使用实际发送的同一序列化字节，或显式证明编码与JSONResponse完全一致；所有分支含空/未命中均执行。异常身份/qualification超大同样拒绝；不得把字节限只放在数学子对象。编码计数要有界停止，避免先生成无上限大字符串。前端对应64KiB有界读取及结构校验，超限整份失败，不仅依赖Content-Length。

实施前一次冻结的合成资源观测：分别独立进程，256MiB地址空间、20秒CPU、30秒墙钟，UTF-8响应64KiB；零行、19行、20行、20,000有效近最大格点、20,000全零失格、20,000交错失格和日期重复/无定位，均需满足预算。统计归一化/计算/序列化耗时和整体峰值RSS，并用计数instrumentation核验只计算一个窗。超时/OOM/超字节即失败，不提高预算重试。先测纯来源字典，再对授权临时合成Store/进程内ASGI单独验收；禁止真实socket重试。预算是验收上限，非承诺稳定尾延迟/服务级限制。若20,000资格归一化本身失败，停止接线，另审优化，不悄悄减少允许行数。

## 冻结验收

1. 与旧dispersion_report在小/中合成全前缀逐日期行全等；共享抽取前后旧报告完全一致。前缀追加/修改未来不改变共同日期局部结果；不同前缀identity按原合同变化。
2. 不可能日期、紧凑日期、时刻、date>cutoff、未知参数、非日线、错误snapshot、20,001行在正确层拒绝；preflight失败不得调用_research_query。空源/全部无日期/缺目标日期有明确状态，无NaN或虚构最近日期。
3. 零数学/零来源分开；最大格点及相邻格点、极小离散、负下界、舍入ambiguous、负零；源类型/尺度/范围非法仍由原核心拒绝。
4. 坏位置25使25..44失格、45恢复；密集失格全部原因保留；重复日期ordinal=null；无定位及覆盖未知；bad volume/amount不额外失格；隔离source_rejected保持。
5. 身份：sourceId/snapshot、batch、raw/contract、cutoff与date变化；两个不同query相同数学；owner ordinal裁剪；请求/返回错配、同ID突变；请求A晚于B完成、Cancel/Close后晚到、重复开关/提交、卸载、重新打开、错误后恢复。旧结果不能出现或导出。
6. 64KiB边界附近成功/超1字节失败；Unicode资格按UTF-8计算；超大qualification/selection拒绝不裁剪；客户端虚报/缺Content-Length、分块超限、非JSON/非有限/非法结构全部关闭。
7. 临时纯合成Store：只读打开、原件缺失/篡改、空查询仍核验、行预算含unlocated，库/原件前后不变；只用新夹具，不接触历史Store或捕获。ASGI非真实HTTP资格明确。
8. 受影响Python、API、原纯核回归；前端DTO/实际React交互、类型/构建及规定全套。初稿时web依赖未安装；父任务随后报告恢复完成，基线910项Node、3项DOM及build通过。此为父任务报告，不是本设计执行证据；新功能仍须独立执行本条验收。真实浏览器、Windows、实源、PIT、完整日历和金融效果继续未验。

## 预期成本与停止条件

主要成本仍是至多20,000源行的原件验证、投影、分组和覆盖扫描；数值计算从最多19,981窗变为至多1窗，输出从已测13.25/39.56MB变为硬上限64KiB；具体时间/RSS尚未测，不用操作数推断实测速度。目标日期不存在仍需完整资格与身份，不能绕过原件验证。metadata过大可能明确拒绝，属于有界失效。

建议下一步：独立反方审查冻结合同，修订后仅实现窄入口和共享纯核投影；后端合成验收与已恢复前端环境的新功能验收分别执行。设计阶段到此结束，不扩展研究。无历史市场数据库被打开、hash或复制。

## 独立反方修订及v2冻结（2026-10-13 21:52 UTC）

v1原文保留为design-v1.md，SHA256 dd6940d32ca55637bb957ea746978a3c3eeea92c16e5a48ee4feda1352083841；v2不是原v1哈希。独立反方认可窄接口架构，以下澄清具有优先级：

1. latest_source_date严格取daily_bars最后一个可读日期组，包括invalid、duplicate_date、unlocated_label及原token可恢复日期的组。不可寻找最后valid/有label组，不可绕过最新坏窗。显式date仍只能精确命中；date>cutoff和非法日期在任何Store调用之前拒绝。增测最新组为重复/恢复日期失格，以及目标处于日期空隙和晚于末日期两种未命中。
2. 数值逐前缀不变只在来源资格及所需历史内容不变时比较共同selected行、members及局部数值/原因；并不保证retrospective coverage、qualification或identity不变。_research_query在任意cutoff都保留全部NULL-label行；其中原token未来日期>cutoff的组不进入daily_bars，但仍计入source_rows/unlocated/batch披露。增测此类未来NULL-label原token，并核对当前请求coverage，禁止使用旧缓存资格。
3. quarantine/batch资格是当前查询的回顾性来源声明，后加隔离可使旧日期失格；不宣称隔离前后仍有相同历史资格或可计算数值。增测未来新增隔离/known_negative_source改变资格及既有窗reason，不以数值prefix原则错误压制变化。原query identity算法不因本功能修改；即使某些元数据变化未被旧query_id覆盖，UI仍以本次完整已核响应和新generation持有当前来源资格，不能仅凭query_id复用过期对象。
4. 默认latest与明确日期即使解析至同一天，选择策略仍显式可见，并由请求选择区分view identity。任何caller自报owner-query ID不能充当可信Store来源证明；owner query只是客户端生命周期绑定，研究前缀query_id由服务端返回。
5. UI渲染本身必须比较当前上下文/date与已接受对象绑定，props或date改变后的首个render即隐藏过期结果，不能等待useEffect清理才失效；generation和Abort控制异步采纳，并不单独证明渲染没有短暂旧值。
6. 整体有界序列化在owner工作内完成；沿用既有no-store和Host/Origin错误边界，不扩服务权限。
7. 补充执行断言：patch完整dispersion_report为立即失败，新入口仍须通过；exact_window调用数<=1；空/未命中为0。20,000失格时不得生成全series/全历史invalid_members。

v2尚待独立反方确认最终字节。冻结后才能产品编码；此文件无产品验收或性能测量声明。


## 最终设计确认与实施对应

上文保留编码前v2设计文本；独立反方于2026-10-13 21:53 UTC确认设计GO。仓库外冻结v2 SHA256为 `e605bb327208934110cfa9912b7da074279e72dbeee757317b1f5be2f6db2c73`；本公开文档追加执行记录后不再冒充该哈希。

实际接口为 `GET /api/research/close-dispersion/{snapshot_id}?cutoff=YYYY-MM-DD&date=YYYY-MM-DD`，两个参数均可省略；返回直接在所述单日期报告顶层增加analysis_id，无另层包装。使用共享 `_window_row` 与 `_header`，离线完整报告字段与值不变。整个成功HTTP正文由owner中的 `_dispersion_bytes` 一次有界编码，再作为原字节响应，不先构造完整历史报告、不重复序列化。

实际UI为App内单股日线的独立 `SelectedCloseDispersion`，与原SingleResearch并列。DTO验证、64KiB流读取、同步当前上下文遮蔽和generation废弃均局限于该入口；无新依赖、缓存或通用框架。截止、源序号、日期、模式及影响来源资格的代码/市场/复权声明/隔离/known_negative_sample/manifest资格改变会清空；普通显示名称改变无需重置。

原256MiB地址空间预算在完整API依赖导入阶段失败，未进入工作负载，不能列为资源通过。独立复核决定另立同256MiB全进程峰值物理RSS观测，虚拟地址空间另记，CPU20秒/墙钟30秒/响应64KiB不变；两个口径并列，原失败不取消。该决策及实际测量范围见[限定验收](../qualification/065-selected-close-dispersion.md)，不承诺256MiB地址空间运行或服务级尾延迟。
