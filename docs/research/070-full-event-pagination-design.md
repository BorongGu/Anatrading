# 全事件账本有界分页：冻结编码前设计 r1

日期：2026-10-14 UTC。源码基线：6c472ff4c3c6d162d32f4ed8bbd08a50dcba6e79。
状态：设计待独立反方审查；未授予实现准入，未修改产品。

## 1. 唯一目标与证据边界

使已经接受的单股研究响应 events.rows 中每条事件都能在最多100条事件的当前页访问；h=5且既有详情资格通过时，每条均可尝试打开现有六槽详情。早期负变化、invalid、immature、purged、overlap_excluded 和其他分段事件不得因分页被过滤。

当前 SingleResearch.tsx 使用 rows.slice(-100)，captureEventPath 另有 length-100 最小位置约束。056 明确披露这个限制；它是工作流可达性缺口，不是新发现的统计数值错误。上方现有统计已经使用完整报告。静态101条玩具行反例仅证明第一条可能不可达，不证明真实用户损失或金融价值。

本设计仅取代056的“最近100条入口/不做完整账本分页”排除项，以及由该排除项直接导出的 captureEventPath 最小数组位置限制与对应测试预期。056的标签、来源、六槽、只读拥有、h=5、分段、统计归属、验证层级及全部未验资格边界保持。没有新金融算法或交易收益主张。

## 2. 最小分页规则（冻结）

- 固定 PAGE_SIZE=100，不设可配置页长、筛选、排序、搜索、导出、虚拟滚动或持久化。
- 接受响应中的原数组顺序保持；同页仍按原有早→晚顺序展示。页码从最近一页算起，初始 page=0，等同当前最后100条视图。
- N=events.rows.length；P=ceil(N/100)。N>0时合法 page∈[0,P-1]。
- end=max(0,N-100*page)，start=max(0,end-100)，展示 rows.slice(start,end)。每行 globalPosition=start+offset。
- globalPosition 是完整 events.rows 的零基数组位置；event.index 是 series 的零基位置，两者不得混用。传 captureEventPath 的仍为 globalPosition，六槽仍取 series[event.index+k]，k=0..5。
- 例：N=101，page0=[1,101)，page1=[0,1)；N=201，依次[101,201)、[1,101)、[0,1)。最早不足100条只在最早页，不重新分配最近页。
- N>0呈现状态：“第 {page+1}/{P} 页（从最近一页起） · 事件 {start+1}–{end} / {N}”。固定附注：“每页最多100个事件；上方统计使用完整研究范围。”
- 四个原生 type=button 控件，置于事件表上方：最近一页→0、较新一页→page-1、较早一页→page+1、最早一页→P-1。越界/当前目标按钮 disabled。使用文字标签，无下拉或输入解析新分支。N≤100时可保留四个禁用按钮与准确页码。
- N=0且有series时显示“当前研究范围没有突破事件。”，不渲染分页控件、不构造第1/0页、不构造详情按钮。空series仍保留现有空范围提示与原布局，不强行增加账本。
- 页面只产生最多100条事件主行、最多一个展开详情；详情固定6槽的既有表不计入事件主行数。全部P页区间两两不交，并集恰为[0,N)。不按selected/status/价格变化/当前train-test分段筛行。

## 3. 局部所有权与过期回调（冻结）

分页适用于h=1/5/10/20，也适用于旧validator已接受但六槽局部门失败的报告。因此不得依赖 acceptEventPath 成功或 reversalSource 成功才能分页。

在 SingleResearch 内增加一个局部账本视图记录及同步ref，与state成对更新；不建立通用框架。记录包含：每次完整接受新建的token、report对象引用、该次请求Generation、完整图表上下文副本（ownerQueryId、snapshotId、batchId、cutoff、ordinalStart、ordinalEnd），以及page。记录对象自身同时作为本次页面身份；真正翻页时生成新记录对象，保留token/report/generation/context，仅改page。不在每次render重建身份。

成功接受（旧assertResearchReply通过，并已通过既有请求Generation/完整上下文守卫）时，无论h是否5、analysis_id是否相同、JSON值是否相同、是否同一对象重复接受，都建立新token/page0。六槽接受失败只禁止六槽，仍保留原报告和分页。分页不新增报告级字段校验，不重复接收报告、不调用onReport。

统一当前性检查需同时满足：closure中视图记录 === 活动ref记录；record.report === 当前report；record.generation仍被现有gate认可；完整record.context等于当前上下文。render亦用当前上下文门禁，不能先显示旧页再等effect清理。沿用现有上下文变化的永久失效、abort和Generation机制，包含同query_id的版本/批次/截止/序号A→B→A；旧token不能复活。

导航回调捕获具体视图记录，执行前检查上述门。合法目标与当前页不同才提交：先同步清selectPath(null)，同步更新活动视图ref，再更新state。不调用closePath，避免向即将卸载的旧事件按钮转移焦点。越界、同页或过期导航为无操作，不能关闭当前详情。页面往返A→B→A必须有三份不同的视图记录，最初A回调仍过期。

choosePath入口除既有 accepted token/report/generation/context/具体selection身份守卫外，再检查当前视图记录身份及 globalPosition属于当前[start,end)。Close/Escape/外层toggle同样受该页面身份守卫（保留原有selection身份守卫）。这使旧页按钮、旧页Close/Escape/toggle及旧页导航不能关闭、替换或聚焦新页详情，哪怕回到相同数字page，或旧回调捕获selection=null。不要仅检查page数值。

## 4. 重置与交互

- 任何现有invalidate、参数编辑（含非法/未提交）、更新开始、请求失败、完整上下文失效、卸载：立即撤销视图ref/state并清详情；下一次有效接受从最近页开始。迟到成功/失败不建立分页身份。
- 实际翻页：清本页详情/局部选择错误；返回原页不恢复展开。各页保留既有pathIssue等报告级诊断，不把翻页当重验或重试。
- 上方train/test切换：页数、当前页与六槽投影保持；仅现有统计面板与原有归属说明随分段切换，不能因此筛行。相同上下文图表选行亦不重置。
- 当前外层账本details关闭：沿用既有详情清理；当前page保留。重新打开不恢复详情、不重置page、不请求数据。
- 现有详情原按钮再次点击、Close/Escape和焦点返回规则保持。导航使用原生键盘语义；不自动滚动，不改URL/history，不恢复跨挂载状态。导航控件若因到边界变disabled，不添加跨区域焦点跳转；实际浏览器焦点/窄屏仍须单列未验。

## 5. 数值、请求、资源不变项

- 所有现有统计/分母/基线/计数与当前分段解析代码保持。分页切换增量请求数=0；六槽展开/换选/收起增量请求数=0；不触发HistoricalPathResearch、原图、Store或相邻来源查询。
- 相同原操作序列的请求URL、参数、次数和onReport发布次数与基线一致。当前组件已有的历史路径请求须计入基线，不假称总请求恒为1。新增分页序列只允许客户端state变化。
- report与全部嵌套对象只读；不得原地reverse/sort/splice、修改counts、冻结原报告、整树复制/hash或建立跨报告缓存。既有六槽独占冻结投影保持。
- captureEventPath仅将合法位置下界从max(0,N-100)改为0，上界N-1与safe integer检查保留。空数组、负数、越界、小数、NaN、Infinity仍拒绝。不改变接受校验或任何六槽内容/精确价格/未知值规则。
- 一次页面切片/主行渲染上界100；分页算术O(1)，切片O(100)，点击捕获仍最多6槽。没有新增按全账本的页面扫描。既有整体图表render、validator和接受账本扫描成本仍存在；不宣称整组件更新O(100)，不宣称内存/延迟SLA。
- 沿用shared validator 20,000数组上限与056来源资源门。合法大响应优先沿用20,000来源槽、19,980事件（lookback20）的纯合成内核构造。20,000事件纯分页算术测试只说明区间，不得冒充后端可达DTO。

## 6. 改动面与停止线

预计产品文件仅SingleResearch.tsx、single-event-path.ts；必要时增加一个仅用于本组件的纯区间函数文件（不得演化通用分页框架），测试及新研究/验收记录另列。无需改CSS即可复用现有按钮/布局；若实际布局需要扩面先说明，不假装视觉已经验收。

编码前须将本冻结设计、验收矩阵与独立审查结论纳入新研究记录，并明确056仅分页排除项被取代，保留历史记录而非改写旧PASS。现有RECENT101“首条拒绝”测试需改成“首条可捕获”，空事件拒绝不变。34份原合成响应及六槽负例继续回归。

若需要新API、原始数据加载/采集、后端计算改动、统计重算、新依赖、异步worker、通用缓存/分页架构，立即停止并报告原因，不在本设计内扩大。禁止旧数据库、真实行情、网络获取、发布和绕过EPERM浏览器限制。

## 7. 阅读与未执行声明

已读AGENTS（无仓库.agents/skills）、SingleResearch、single-event-path、现有两组event-path测试及fixture加载器、056研究/设计/审查/验收矩阵/qualification、research-model相关验证和请求构建、静态可达性评估。只做本地文本阅读和设计文件写入；未运行产品、测试、浏览器或数据库，未修改仓库。原生浏览器历史EPERM不重试；将来jsdom仅证明功能/状态，不代称视觉验收。Windows、真实来源、HTTP/Store、完整App、性能、用户效率和金融效果均不因本设计取得资格。
