# 冻结预期答案与有界验收矩阵

编者注：下文保留编码前设计时态；同编号 design-review 的 §7 最终 r2 GO 已获接受，已进入最小实现。下列验收条目在原设计时尚未执行，实际执行状态以 056 主记录为准。

2026-10-13，r2。以下全部为**未执行的验收设计**。没有通过数、运行截图、性能结论或真实市场数据。fixtures.json是合成字段投影；extends/override/slot_override仅说明合成卡继承关系，不是可运行加载格式。override.event字段局部覆盖；公共evaluation_as_of的覆盖必须同步到事件；slot_override覆盖close数组的同一位置。未提供的完整DTO字段必须由独立审查逐项补齐，不能声称这些卡已经可直接喂给现有validator。

## A. 内容正确性（固定卡；不扩大为随机搜索）

- A01 P1A/P1B：六行顺序精确同卡；分别指出d1/o1=90或110。既有终点同值不代表路径相同；不加新百分比或涨跌自动结论。B0可人工答对；B1只省找起点；C直接绑定窗口。
- A02 P2A/P2B：分别定位90→110、110→90；无极值汇总替代表格。
- A03 P3：固定6位置，t0..t3存在；t4/t5三字段均未知；h=5保留。P3_BAD仍immature，第三槽在原位置为坏槽，成熟判定优先级不倒置。
- A04 P4_DUP：2026-01-07是一个坏日期组，不展开成两条原Row，不跳过以凑5个有效后续点；序号/close为空。P4_ZERO/P4_NEGATIVE按规范字符串原样保留0/负数，不阻断结构合法的invalid证据。P4_OHLC的正close不恢复valid；P4_END_NULL/ZERO/NEGATIVE分别在t5原位显示null/0/负数，event.end_close与槽逐字一致，成熟invalid仍可查看。坏槽后已存在的有效槽必须warming_up、reason=null。
- A05 P5_OVERLAP/P5_PURGE/P5_OVERLAP_PURGE/P5_INVALID_PURGE：四种原状态分别保持；重叠排除優先；purge也可覆盖成熟invalid。上方事件count不包含这些记录；不声称基线排除。P5_IMMATURE_OVERLAP保持label=immature、evaluation=overlap_excluded；目标index21及此前selected index20均须在完整合成账本中一致体现。
- A06 P5_OTHER_PART：test面板不说train事件已入上方；切到train只更新说明。无test_start时尽管React初始partition为test，实际说明必须descriptive。
- A07 P6：拒绝从close确定柱内次序、MAE/MFE、止损、财富、成交或预测。B0提供更多OHLC但仍不自动给成交资格。
- A08 P8_PAGED与P8_ABSENT：两者均零源callback、零新增请求；显示真研究位置，不用不在当前页推断不在query。不强转Row，不调用loadQuery，D不变。
- A09 PRICE_PRECISION及所有price_text_cases：第18位全部保存；无Number/parseFloat/closeNumber路径；接受界限最大40字符，超界拒绝。null与未知未来槽不同。
- A10 KALMAN_ONLY_FAILURE：series的invalid/numerical_failure照实注明，原valid/evaluation/当前事件归属不变；故障后t3..t5明确warming_up。此卡为估计故障注入，不声称已证明正常价格自然触发该失败。
- A11 NULL_CUTOFF与EXPLICIT_GAP_CUTOFF：请求cutoff与D分列；一个D=最后槽，另一个D=请求截止；graphQ≠researchQ接受。禁止用最后槽覆盖显式截止。
- A12 M01–M12各自注入一次、恢复一次：在对应门拒绝，原表/原报告保留，新关联不显示未经核验六槽。M03由原validator拒绝，遵守原错误流程，不能降级绕过门一。

## B. 身份、变异和交互（每条固定一次流程＋重复点击边界）

- B01 同analysis_id新JSON仅改t2close：新代次先清选择；点击后只能看到新值。不按ID缓存/合并。
- B02 尝试改变本功能独占投影的身份/参数/原事件字段、槽数组和slot.close：所有自身容器已冻结，值保持不变，且没有raw event/series/parameters等可变别名。严格/非严格模式不强求都抛异常。raw report强制原地写是明确不支持操作，不要求产品抵御，也不宣称该违规行为后原表与捕获仍一致。
- B03 同一对象再次接受：仍建新token，旧选择失效。不同对象内容完全相同也失效；无论是否同analysis_id。
- B04 按钮A→A收起→A→B，只出现一条详情；没有原selected变更、URL/history变更或请求。错误A→合法B清局部错误。
- B05 Close、Escape、外层details收起分别清E；重开外层不恢复；焦点回存在的触发按钮。若事件因上下文失效被移除，不把焦点发到旧DOM。
- B06 展开后逐一编辑lookback/horizon/test_start，含空值、非法值、编辑后未提交：同次UI事件隐藏旧详情；h切非5无入口；切回5不自动恢复旧报告。
- B07 连续更新A/B，安排A成功晚到、A失败晚到、A abort、B成功：只有B可接受；所有晚到结果不恢复选择或覆盖新错误。以旧DOM排队点击A也无效。
- B08 V/cutoff/ordinal范围变化、重新查询相同参数、same-query_id重挂载，逐项清选择。异常query对象同ID但V/cutoff改变，渲染门立即阻断，不等待effect。
- B09 workspace切换→返回、导入触发invalidate、chartError、页面刷新、Back/Forward触发卸载、StrictMode重复挂载：旧E均不泄漏；无卸载/上下文变化的Back/Forward不制造新选中。
- B10 会话失效/网络失败/用户取消：无旧详情；不新增后台恢复fetch。沿原错误反馈。授权正常更新后必须新代次。
- B11 图表选择其他Row、原表翻页/图缩放：仍同研究上下文时详情保留，UI不表示两边聚焦同步。
- B12 上方train/test切换保留6槽与原四状态；仅当前事件统计关系说明变化；统计值、原partition与baseline都不变。
- B13 最近100边界：100条显示全有入口；101条仅最后100条入口，首条仍在原rows/原统计。零事件/空series不提供虚构入口。不扩全账本分页。

## C. 资源与字段异常（仅本地合成，不用行情文件）

- C01 0、1、5、6、20,000个series槽与0、100、101、20,000条事件的结构边界分别按可构造合法性选择代表；不得为了达到20,000事件强迫不可能的检测器输出。大卡可直接测试纯局部结构边界，须标“异常/不可达输入”，不能当真实核验收。
- C02 series/events长度20,001、非法日期/闰日、负索引/越界、非安全ordinal、错误类型、缺失端点字段、unknown资格状态、重复partition键的解析风险（以解析后预期处理为准）以及未知额外安全字段：旧validator的拒绝保留；门二的必要字段明确拒绝；未知额外字段不任意升级为全DTO exact-key校验。
- C03 深度16/17、每数组20,000/20,001、每对象128/129键、字符串4096/4097沿用原validator边界；新功能不改旧校验、不引入新的节点/字符总预算，不宣称现有响应解析资源局限已解决。
- C04 接受入口仅处理jsonRequest解析结果及可信测试构造的JSON数据；不承诺防御任意getter、Proxy、循环或恶意JS对象。局部捕获逐字段复制显示标量，自有全部容器，冻结只覆盖这个小投影。
- C05 接受时一次有界账本关系扫描（N≤20,000），点击最多6槽校验/复制/冻结；无新全树访问。记录正常完整合成响应的实际大小/耗时/峰值内存后才谈性能，本设计无毫秒/SLA承诺。若需要worker/分块异步/缓存框架，停止并回设计。
- C06 无网络函数/import、无Store依赖、无价格运算/ratio/哈希。校验器整数计数只用于比较原counts，不产生新统计报告或修改原值。

## D. 原API/统计不变的golden约束

后续获准后，使用仓库已有的纯合成golden及补齐的新合法合成响应；固定当前基线commit作为前后对照。不得读真实Store来制造golden。

- D01 固定同输入下后端 single endpoint 的全部JSON字段语义与原序一致：series、events.rows、selected、partition、label_status、label_reason、evaluation_status、start_close/end_close、price_change、counts、各分段statistics、baseline、query_id/analysis_id、cutoff/D、limitations完全不变。没有后端文件修改也必须列出这项回归，未跑不称通过。
- D02 同一已接受响应在展开/换选/收起/切分段的所有支持操作中，完整report深度值及原statistics/baseline DOM数值与实现前相等；原report及嵌套对象可写属性描述符不改变，仅小投影冻结。
- D03 原API请求路径、次数、参数在同样基线操作下不变；六槽按钮及换段增量请求数为零，不触发历史路径/原图新加载。不把组件本来自动加载的请求归咎或隐去。
- D04 onReport既有只读消费者回归：App.receiveSourceResearch→bindSourceResearch→RecordDetails→AdjacentSourceDetails→adjacentSource；相邻输出、来源匹配拒绝、迟到归属拦截不变。ResearchProvenance/EstimatePlot仍只读。不得增加report原地写；若未来确有这种需求先改合同。
- D05 现有h=1/10/20、singleResult/pair/universe validator、原事件表价格变化、空范围、各种研究错误回归不退化。新局部失败不能让shared validator原来拒绝的响应变为接受。
- D06 完整事件账本与baseline计数不受最近100、当前选择、正负close、排除状态、当前上方分段影响。原负结果、真实0/15边界和金融限定继续保留，不因UI验收翻转。

## E. 审查结论表（供独立审查填写，当前全部待审）

1. 设计是否可在零新增数据、零新数值引擎条件下完成：待审。
2. 只读报告拥有合同、接受令牌与独占投影无别名/完整冻结：已按R1修订，待复核；不引入整树冻结或新全局预算。
3. 局部count一致性检查是否足以支持原响应归属措辞且不越界成统计重算：待审。
4. 所有原invalid/immature合法保留值是否仍可看，Kalman失败是否分离：待审。
5. 是否有B1更小且完整实现路径：待审；若有则优先B1/停止C。
6. 是否授予任何产品编码或执行验收准入：本文件不授予，须由母任务另行决定。

## F. 最终执行索引（2026-10-13）

本文件A–E保留编码前冻结条件及当时时态；最终f216f72已获限定本地合成PASS及独立代码复审GO。实际执行、初始7/扩展12项失败、修复、34份完整DTO、原报告不变证据及逐组未验边界见[056验收](../qualification/056-single-event-six-slot.md)。完整App/真实浏览器/HTTP/Store等未跑项未因静态接线或组件卸载测试而改成通过。
