# 073 估计图与报告归属：冻结修复条件

2026-10-14，基线 `3ab16f114eec5597c7ff8d02690db84f5a651027`。这是独立的正确性修复；此前仓库外估计图复用实验保持 **NO-BUILD**。该实验合成导航中位数改善55.91%，但同query_id换snapshot的第一次React提交仍有旧SVG，第二次才消失；数值阈值通过不能代替正确性。不得修订旧候选、重跑性能或降低旧门槛。

## 编码前计划与验收（冻结 r1）

1. 先加入实际SingleResearch＋HistoricalPathResearch的合成React/jsdom回归，以Profiler观察每次提交；在未修改产品上复现同ID换snapshot首提交旧SVG，保留失败证据于仓库外。
2. 复用既有accepted view的报告引用、Generation和来源上下文，在渲染时门禁完整结果区、估计SVG、图例、统计、来源说明及空范围提示。现有清理effect继续永久撤销接受，A→B→A不恢复。
3. 同一局部上下文补充来源周期、manifest资格和批次known_negative_sample失败标记的标量匹配。只侦测改变，不新增研究资格规则；初次合法接受与原有局部六槽/反转失败保留原报告语义。正常App周期变化仍沿用现有挂载路由。
4. 覆盖query/snapshot/batch/cutoff/序号范围、周期/资格/已知负样本变化第一提交，A→B→A、参数number/date/select修改、迟到成功/失败与旧回调；明确支持通过重新提交接受新报告。保留合法报告完整DOM、请求/发布次数及只读性，覆盖非5跨度、空series及局部附件失格。
5. 不修改EstimatePlot/SourceChart、数学、API/请求参数、后端或共享validator。不引入memoization、通用缓存、每render全来源hash或新身份系统。使用现有依赖；原生浏览器EPERM不重试，不宣称视觉验收。
6. 执行定向DOM、全Node、TypeScript/build、diff检查；后端未变不重跑Python。独立复审冻结候选后方可发布。真实来源、Store、HTTP、Windows、真实浏览器、性能与预测资格均未新增。

## 原因

原结果块只检查report/latest；事件分页已检查接受代与上下文。来源prop变化先提交，再运行清理effect，故结果区比事件账本多保留一次提交。修复应使同一次提交的报告展示拥有相同当前性边界。

## 远端审查补漏（编码前，2026-10-14）

PR68对已测试首版指出：后端source_rejection同时读取metadata.quarantined===true和批次known_negative_sample失败。首版只捕获后者，遗漏独立隔离标记。接受此发现，原冻结无旧报告条件不变；先增加隔离标记第一提交/A→B→A及迟到成功回归，保留首版失败，再增加一个布尔上下文匹配/依赖。无新资格政策、性能重跑或范围扩张。

## 已发布报告的消费者补漏（编码前，2026-10-14）

PR68第二轮审查指出RecordDetails仍可在同ID上下文变更首提交展示旧相邻价格；SingleResearch的null发布发生在后续effect。完整消费者审计只有App的sourceResearch状态，经两处RecordDetails进入AdjacentSourceDetails/adjacentSource。补充同一冻结首提交条件：先在实际两处消费者＋SingleResearch及App等价发布回调的父组件中复现；再提取现有局部来源上下文捕获/匹配，发布绑定保留标量快照，消费者渲染同步比较。复用共享条件以免内部/外部规则漂移，不改回调签名、次数、DTO、数学或请求；原清理与A→B→A永久撤销保持。正常App工具栏流程与异常同ID直接props分别验收。

独立实际App首提交补充发现：异常同ID日线→分钟→日线时，日线子组件曾卸载，原cleanup只撤销内部代次而未清父绑定；返回日线仍可首提交复活父相邻值。原“回调次数完全保持”假设不能满足冻结永久撤销条件。先将仓库父测试改为与App相同的日线条件挂载，保留该红灯；最小补充为已接受报告的owner卸载时发布一次null。请求、接受结果发布及回调签名保持，新增清理发布明确单列；旧query-ID清理仍由既有binder拒绝。
