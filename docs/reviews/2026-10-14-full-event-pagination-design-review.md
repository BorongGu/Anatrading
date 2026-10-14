# 全事件分页：独立编码前审查

2026-10-14 UTC。结论：**GO，限定设计准入；没有编码前阻断。**

## 冻结输入与执行边界

- 仓库基线：6c472ff4c3c6d162d32f4ed8bbd08a50dcba6e79；实际 HEAD 相符，审查前后工作树干净。
- design.md SHA256：53e189fd473d1fe1119a722d3fad251c9e5c0447288bba7a29ebcb306806522d。
- acceptance.md SHA256：16d89e5a1a1db1abc96d9778538a2884a6a6451411db4e4b9cc853b8e8187fe7。
- 已核读 AGENTS、SingleResearch、single-event-path、两组现有测试及 fixture 恢复器，056研究/设计/设计审查/验收矩阵/qualification与最终复审；定向核查 Generation、完整上下文比较、shared validator和event_report。
- 本轮仅本地源码/文档阅读、哈希/状态检查及仓库外本报告写入。未改产品或仓库，未运行测试、产品、数据库、原生浏览器或网络获取。未重试历史EPERM限制。没有将历史PASS当本轮结果。

## 1. 区间与可达性：通过设计审查

设 P=ceil(N/100)，合法页p的区间为[max(0,N−100(p+1)), N−100p)。对N>0的合法页，右端恒正。相邻两页在N−100(p+1)相接；第一页右端N，最后一页左端0，各区间内部长度1..100，因此互不重叠且恰好覆盖[0,N)。N=0单独处理，不生成非法页码。

page0精确保留原rows.slice(-100)的内容和原顺序；最早不足100条留在最早页，不改变最新页。N=101、199、200、201与19,980的冻结预期正确。globalPosition=start+offset正确指向完整事件数组；series起点仍是event.index。原限制仅位于SingleResearch.tsx:144–145和single-event-path.ts:108；后者改最小位置为0而保留安全整数及N−1上界，即足以解除模型入口限制。

event_report.py:98–105在index<lookback时不产生事件，:123–135保存所有突破事件，包括未selected者。因此20,000来源槽、lookback20最多19,980事件这一合法大例成立，200页最早区间[0,80)正确。20,000事件算术用例与合法DTO分开，避免重新引入056已排除的不可达大例。

## 2. 所有权与过期攻击：局部页面身份必要，现有机制应复用

现有accepted仅h=5时建立，且acceptEventPath可能局部失败（SingleResearch.tsx:60–66），不能用它作为分页存在条件；reversalSource亦有独立接受失败（:67–70）。设计建立普通账本视图，和两个局部功能解耦，符合原报告保留合同。

现有Generation已经提供请求永久失效（model.ts:4–8；SingleResearch.tsx:48–56、74–83）。完整reversalContextMatches已覆盖ownerQueryId、snapshotId、batchId、cutoff及两个ordinal边界（close-reversal.ts:72）。直接复用这两个机制；无需新全局owner、hash、框架或再做完整响应校验。

现有选择引用守卫（SingleResearch.tsx:40–43、87–92）只区分具体选择。翻页清空后selection又为null，旧页面捕获null的行回调可再次满足该条件；page数字A→B→A也会相等。因此每次真正翻页新建页面记录，并同步更新ref，具有实际必要性。冻结B02/B04覆盖两种危险：返回同数字页，以及同旧导航回调在React提交前重复执行。不得简化为仅按page数字检查或仅useEffect清理。

普通账本每次接受的新token在“页面记录本身每次接受/翻页均新建＋当前ref身份＋generation”组合下没有额外区分能力。这是非阻断的常量级冗余：保留它不会形成资源问题，但实现不得围绕它新增第二套代次生命周期、查表或同步effect。若作者选择删去该冗余字段，应在文档同步说明由新页面记录承担同等接受身份，保留B08验收；无须为优化一个对象另建架构。既有六槽AcceptedEventPath.token语义保持。

完整上下文render门禁与永久失效均要保留：门禁负责立即不显示旧页，已有invalidate/gate负责上下文返回时旧令牌不能复活。完整上下文需用含batch的版本，不能只用现有EventPathContext（single-event-path.ts:7–9、40–43不含batch）。设计已经明确这一点。

## 3. 重置、请求与局部失败：冻结要求充分

参数输入均同步invalidate（SingleResearch.tsx:100–103）；load在发请求前invalidate（:49–55）；query变化及卸载有现成清理（:74–83）。将新视图ref/state纳入这些入口即可。新接受必须在旧validator及现有请求上下文门之后生成page0，无需以analysis_id、report引用或内容相等判断“同一份”，与:58–60现有合同一致。

导航应直接selectPath(null)，不要调用带聚焦副作用的closePath；旧Close/Escape/toggle保留选择身份守卫并加页面身份门。当前外层details关闭保留page。越界/同页导航无副作用。设计B01–B10覆盖这些路径，没有发现依赖新API或异步机制的缺口。

分页不得依赖h5局部门；h1/10/20及接受失败报告仍可浏览。局部捕获失败仅显示本行原错误态。train/test仅影响现有part解析和归属文案（:94–96、129–135、149），不筛账本、不重置页；设计与矩阵一致。

HistoricalPathResearch在SingleResearch.tsx:159真实存在。C03要求保留完整挂载并与原请求基线比较，正确避免“组件总共仅一次请求”的错误。页操作不调用load/onReport即可实现零请求、零重复发布；对失败/迟到请求仍以既有gate为准。

## 4. 六槽、统计与资源：无语义扩面

single-event-path.ts:109–127按e.index提取固定6槽并逐字段复制/冻结小投影。无需修改价格、状态、标签、分段、计数、接受扫描或投影字段。仅放宽captureEventPath数组位置下界符合本任务。

统计从完整evaluation/part读取（SingleResearch.tsx:94–96、130–137），分页区间只作用于主行。不得把页内行重新构造成evaluation或重算分母。原报告只读、不排序/反转、不整树freeze/hash/复制，与056一致。

分页算术O(1)、当前主行切片/渲染最多100，均成立；不能推导整个组件O(100)：现有EstimatePlot输入仍map完整series（:121–124），既有校验亦扫描报告。设计明确保留这项限制。可达大例覆盖200页可用于正确性，不足以赋予实际设备流畅性或性能SLA。

## 5. 实施与验收关注点

没有必须返修的设计项。实施时以下内容应留在最终独立复审清单：

1. 新view建立/撤销的所有路径同步更新ref，导航回调封闭具体记录，不能把ref只放effect里更新。
2. render、行选择、Close/Escape/toggle和导航都使用含batch的完整页面当前性判断；旧回调不能移动焦点。
3. RECENT101旧首条拒绝断言改为可捕获；现有模型遍历从最近100起步也扩至0（single-event-path-model.test.mjs:20、31）。空数组拒绝和其他六槽回归保留。
4. 全量可达验证使用独立区间oracle，主行计数排除内嵌六槽表；正常响应先过未修改assertResearchReply，故障注入和孤立算术边界分组。
5. 上方统计DOM须覆盖全部分位数/正变化比例/基线，不只count；请求比较不能stub掉历史路径组件。
6. 将设计、矩阵及本审查决定先纳入新研究记录。056保留历史含义，仅明确分页排除项被新设计取代，原PASS不自动继承。

GO只认可该窄设计可进入已授权的实现阶段。产品正确性、jsdom交互、完整Node、TypeScript/build、纯Python及新golden都待本轮实际执行和独立复审。真实浏览器视觉/键盘/窄屏、完整App、HTTP/Store、Windows、真实来源、性能、人效和金融效果继续未验。
