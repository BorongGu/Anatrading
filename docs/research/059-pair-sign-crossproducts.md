# 059 涨跌分项共变核查

2026-10-13，实施前合同；058 真实来源数量秩最终 STOP 保持不变。

## 研究依据和范围

本功能采用简单变化与中心化交叉乘积恒等式，定义及八组合成数组已在修订2规格与独立 Fraction 审查中冻结（规格 SHA256 d0b9874a4095a3eaad6bd977b2036b825b7af4a4e913edfd0f320648d9de2d0b；数组 a8632148c80c35e26c40385f6ca80267098106337ad43ce41a2071904d2ca490；oracle c1286c2abbb12f4cdd6bbce499e3d6a59100c72aa0fa10cc002814bc44a15a9c）。该代数恒等式不声称新论文贡献或新预测算法；未新增市场样本、Store 读取、模型调参或数据下载。

问题：相同或相近相关下，已选两列在前后两窗各自的同涨、同跌、异向原变化乘积是多少？基线为现行 051 标量相关和来源表。F01 给出相同相关/计数而同跌和不同的反例；F08 证明相同价格不能识别真实重估和公司行动。

x=(C_t-C_{t-1})/C_{t-1}，y 同理。A_pp、A_nn、A_pn、A_np 分别累加正正、负负、正负、负正变化的绝对乘积。M=(Σx)(Σy)/60；S=A_pp+A_nn−A_pn−A_np−M。A 是未中心化分项；S 是中心化交叉乘积总和，未除59，不另报样本协方差。零变化进入九格计数，所有60区间保留。

## 最小接入合同（独立边界审查已允许实施）

- 新增单一 TypeScript 模块 pair-sign-crossproducts.ts；无后端接口、Worker、缓存或全局上下文框架。现有 051 输出格式、数值和请求不变。
- calculatePairSignWindows(input, options) 为可独立测试的纯算法入口。input={cutoff,common_dates,left,right}；side={ids:{snapshot,batch,query},endpoints}；endpoint={index,date,ordinal,close_exact,close_token}。七份有效和一份非法冻结数组均直接适用。返回 previous/current 两窗的 rows/counts/terms/display，无假造的 parent_correlation_state。
- buildPairSignAttachment(report, expected, pair, options) 为产品入口；expected={ids,cutoff} 必须来自真实提交请求，pair={left_snapshot_id,right_snapshot_id}。先在 await 前捕获完整 report、expected、pair 副本；复用 assertGroupPairs 和 verifyGroupPairIdentity 校验全部2–50成员，不择幸存者；复用 054 groupPathCanonical 的有限 JSON/UTF-16键序/无 Unicode 正规化规则哈希完整父报告。只对选中两列运算，不重算全矩阵。
- 返回 {parent,attachment}，持有不可变父副本。attachment 顶层严格为 method_id,rule_version,parent_analysis_id,parent_content_hash,pair,cutoff,status,reason,source_refs,windows,limitations。方法/规则名遵循修订2。source_refs={left,right} 各为原 GroupPairMember 副本，端点增加原位置 index，其余字段及 unknown/null 原样保留。端点仅保存一次；行 right_index 引用对应两个端点。不截断原 token、不重排、不压缩。
- 完整来源面板可算时 attachment.status=complete、reason=null；窗口各60行与九格计数；terms={denominator,pp,nn,pn,np,centering,centered_cross} 为统一分母整数串；display 为六项5位有效数字半偶科学记数。每窗 parent_correlation_state 原样复制原对单元（包括相关失败及 constant_members）；常量使相关未定义，但分项仍有定义，不能提升相关资格。
- source_panel_complete=false：status=unavailable、reason=source_panel_unavailable、windows={previous:null,current:null}；source_refs 保留原成员原因与原端点/null；limitations 保留 parent_reasons、parent_grid_reasons 和 parent_limitations。完整父报告由返回 parent 保留。父 status=unavailable 若仅因常量，并不关闭有定义的分项。
- pair 两 ID 必须为不同真实父成员；允许左右互换，仅查找父已有无序对。原父单元不改顺序。附加 limitations 明确 retrospective_source_prices、no_causal_attribution、no_tail_dependence、no_forecast、no_portfolio_return、unknown_corporate_actions/PIT、human_efficiency_not_evaluated。
- 错误码有限：invalid_context（形状/身份/日期）、invalid_price、numeric_limit、resource_limit、cancelled。错误不产出半份附件。

## 所有权、预算与界面

复用现行 054 的捕获/冻结方式，仅在本模块私有函数内使用；不建立通用对象框架。父响应独立受现行2MiB限制。完整附件 UTF-8 JSON ≤512KiB；去除明确计算数值文本后的 metadata（保留全部结构、键、身份、原价格/token、日期）≤128KiB。两个限制分别实际编码测量；不声称父＋附件总内存≤2MiB。

每窗 Lx=lcm(60个前价整数)、Ly 同理，LCM先约分后乘。D=60LxLy，Q=60Σ|vx vy|，Mnum=(Σvx)(Σvy)，Snum=Qpp+Qnn−Qpn−Qnp−Mnum。a<10^38 推得最终整数最多4564位、bit_length≤15162；实施硬限16000bit，显示/等价比较32000bit。Python参考比较使用有界10000位十进制转换配置，不能误拒合法4564位整数。

options={signal?,yieldControl?}。循环每8区间让出并检查取消。await前冻结捕获；返回前再次检查取消及原调用上下文内容，外部变更不得发布旧附件。UI 在现有选中对区域新增折叠小块和按窗逐区间表；打开时计算，关闭卸载中止。以报告对象/请求对象/两ID关联本次结果，换父（包括相同 analysis_id）、换对、关闭、离页、重复点击均使旧结果与导出失效。只允许当前已完成附件导出，不缓存旧 Blob URL。父选择状态也绑定当前报告对象。

UniverseRequestResult.group_pairs 新增 expected 的提交时副本；loadUniverseRequest 在 await前捕获；GroupPairResults 接收该 expected。其他研究面板不变，不引入 App 全局字段。

## 验收与当前状态

先运行缺模块红测试，再实现；冻结候选源码后一次性对照八份独立 oracle，全120行比值/格子/小计/显示/日期/序号逐一核验，F07必须拒绝。另测交换、合法统一缩放、半偶进位、极小抵消、身份与原文 hash、null与0、元数据/总字节、取消与React DOM旧导出。051既有测试与Python桥接输出对照保持兼容；固定cutoff合法未来追加只影响父来源身份，不进入运算，完整来源资格反证仍须全组关闭。

当前：独立纯核规格/oracle通过；产品实现、整合、性能、React DOM和独立实现复审待完成。浏览器、真实来源兼容、预测/交易增量、人效与 TradingView 优势未验证。

## 实施记录（2026-10-13，未发布）

独立整合边界审查允许实施。实现保持上述单模块/选中对边界，无新服务、数据读入或依赖。源码审查补充：原文 close_token 可以为 null；ID 仅在各自 snapshot/batch/query 类别内唯一；附件 pair 明确投影为两个ID字段。来源回查和导出同时绑定计算代次与有界完整内容，关闭、换对再换回、同 analysis_id 换父和原对象原地修改均需失效。非法/超大上下文显示有限错误，不启动计算。

历史失败保留：首次缺模块红测试；首个候选错误地按 snapshot_id/batch_id/query_id 读取合成纯输入，七个合法例被拒绝，修正为冻结数组原有 snapshot/batch/query 后逐行比对通过，未改输入、数值、门槛或 oracle。完整前端首次从仓库根执行使 Vite 找不到 /src，改从 web 执行；一个旧测试只断言 useState 源码形状，随新增报告绑定状态更新。自写缩放测试最初误要求共同分母文本相同，改按预定合同交叉积比较有理值，原日志保留。独立边界测试原本要求拒绝 null 原文，与既有051合同冲突；保留原运行并改为有效兼容用例。

已运行：本地前端全套876/876通过，059专门测试27/27通过，051 Python27/27通过，TypeScript/Vite构建通过（既有大包警告仍在）。独立纯核23/23通过，包含八份原数组及15个冻结变形；资源受限执行0.901秒，峰值RSS83,196KiB，不能外推浏览器或全组性能。独立适配器39/39、边界39/39通过；原051合成桥接1,856,099字节逐字节相同。React DOM最终重跑、独立最终实现复审及完整Python套件仍待汇总；部分DOM首轮失败为跨Node/jsdom对象realm的测试构造问题，保留历史并修复测试，不算产品通过。

真实浏览器、Windows原生、真实来源兼容、市场效果、人效、预测/交易增量与竞品优势均未新增验证。058真实源数量秩STOP仍有效；新功能仅重组已有合格来源价格的描述性算术。

最终汇总：完整Python3487通过/49跳过；最终前端876通过/构建通过；独立适配器40、边界39、React＋JSDOM22通过，独立代码复审通过。以上取代前段待汇总状态，历史执行记录保留。详情见[验收记录](../qualification/059-pair-sign-crossproducts.md)。

## 后续：保存响应兼容性核查（2026-10-13）

上述实施前与初次汇总中的“真实来源兼容未验证”按当时状态保留。本次后续只检查已保存051响应与059附件的兼容性，未重新认证原始来源。冻结产品版本为 a64c80105e8141ec4ed7e5cdb5542249e5e0c7c3；产品和测试均未修改。

事前固定六份十成员父响应与一份请求/响应夹具，沿原顺序覆盖每份全部45对，共270槽；不按数值挑对、不搜索日期或改截止日。三个完整父面板预期135份完整附件，三个来源失败面板预期135份不可用附件。请求取自保存的提交上下文，并与对应父响应交叉核对；未从回复反推请求。独立有界精确有理数参考先生成并封存，随后调用产品入口，核对每窗60行变化/乘积、九格、小计、显示、原相关状态及完整来源投影；不重建或重新验收父Pearson估计。

执行记录为135完整、135预期不可用，共16,200行通过，独立保存产物终审通过，接受该固定保存响应兼容范围。独立终审从保存附件的来源副本重算全部区间行、1,620个精确小计和1,620个显示，与附件及封存参考一致；未重读七份原输入或重跑产品。前后七份输入哈希及85项冻结执行闭包均记录为不变，完整父来源与不可变性依赖已复审执行器及匹配的执行凭据。来源读取仅限这七份既有保存JSON；无新联网取数、原始行情文件读取、Store或旧数据库打开、模型拟合与重调参。前置执行器的边界/资源监督修正在首次保存输入读取前完成，未改变选择、公式或验收门槛。

本次只增加固定保存响应的描述性附件兼容证据；公司行动、历史当时可得性（PIT）、新样本外预测、经济收益与交易增量仍未验证，058数量秩科学STOP保持不变。059源码、合成夹具与测试可在公开仓库检查；本次私有历史响应及仓库外执行器未发布，摘要和哈希不能让公众独立重跑该历史实验。资源记录、最终审计与同环境浏览器阻断见[后续验收](../qualification/059-pair-sign-crossproducts.md#后续保存响应兼容性与浏览器尝试2026-10-13)。
