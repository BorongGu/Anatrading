# 073 估计图与报告归属修复

2026-10-14；编码前条件见[冻结研究计划](../research/073-estimate-report-ownership.md)。本次修复SingleResearch及其发布到RecordDetails的报告当前性。以下保留各阶段证据，最后的消费者补漏为最新验收范围。

## 实现与已执行检查

原结果区只检查report/latest；同query_id换snapshot时，旧SVG在首个React提交仍存在，随后清理effect才清除。新增仓库回归在未改产品的基线上得到0通过/1失败，明确断言失败于commit 0。修复复用既有accepted view的报告引用、Generation及上下文，渲染时同时门禁完整结果区、SVG/图例/统计、来源、空范围提示和反转附件。原清理effect继续撤销接受，返回旧参数或来源不恢复旧报告。

局部view上下文增加周期、manifest资格及known_negative_sample失败布尔值；沿用原query/snapshot/batch/cutoff/序号范围比较。只对上下文改变防御，没有新增资格规则、报告缓存、全量来源hash或计算。EstimatePlot、SourceChart、数学、共享validator、请求路径/参数和后端未改。

- 新增实际SingleResearch＋HistoricalPathResearch React/jsdom回归34/34通过，0失败/跳过；Profiler检查首个及后续提交。覆盖来源各字段A→B→A、显式再接受、query-ID自动加载、number/date/select参数、迟到成功/失败、所有来源往返后的旧成功、旧页/行/关闭回调、非5跨度、空报告、局部六槽失格、null/估计故障及同ID同对象再接受后的重画。
- 既有实际App＋SourceChart图形API适配器回归2/2通过。日线/分钟路由、选中/重置、迟到请求、来源取消/重选均覆盖；不能据此声称原生浏览器或无适配器图形验收。与上组共同运行36/36通过。
- 完整Node955/955通过，0失败/跳过；TypeScript及生产build通过。保留既有>500kB chunk告警，无性能合格声明。
- 合法接受后完整research-columns DOM在等价Query、往返后再接受及分页/详情操作保持；DTO深值及采样属性描述符不变，分页/详情请求与发布增量为0。同对象估计变化用例仅在旧接受撤销后故意修改合成fixture，重新接受仍重新绘图。
- 首轮扩展DOM集33通过/1失败：测试错误地假定既有RECENT0含首行，读取属性描述符时失败。保留外部日志，改为在空报告场景直接复用这份完整既有合成DTO，未修改产品迎合用例。

复现命令（web目录）：

```
ANATRADING_JSDOM_PATH=/absolute/path/to/jsdom/lib/api.js node --test tests/estimate-report-ownership-dom.mjs tests/component-query-keys-dom.mjs
node --test tests/*.test.mjs
npm run build
```

jsdom使用已安装外部依赖，不改package/lockfile；无新网络取数。原生浏览器历史EPERM不重试。后端未改，Python未跑；真实数据、Store、HTTP、Windows、视觉/键盘设备、性能、人效和预测/交易效果均未验。本地日志、运行产物和历史输入不提交。独立精确候选复审见下节，发布状态另列。

## 独立精确候选复审

独立复审对候选 `1ec0838e863775bb4bd6eaf01324710e414fcbb6` 给出 **GO**，检查全部五个改动文件、干净工作树及diff。产品SHA256 `e53779d454c92a34523c9bd6b241964e4d22f5b0c516d598d0fcfe57583f4c46`与独立实跑副本一致。

冻结首提交测试在原基线保留38断言中的13个失败；候选38/38通过。独立实际App同样取得10/10提交观察通过：正常toolbar先撤销旧来源，分钟周期卸载日线研究；该组在基线也通过，单列于异常同ID直接prop防御。App只在外部编译副本中将SourceChart替为null，原生图形接线未验；初次测试日期selector失配及修正版本均保留。

另有31份正确性观察在基线/候选逐字节一致，包括完整统计/图形、null/reset分段与请求/发布；共同SHA256 `8ca5faf816c960b73308812b2aff09181cb6f6023e62286e9113b87a5701456e`。没有计时或性能重跑。独立报告SHA256 `89b19aeb192ffd33848d11247c6355826ac6332e14ffd09e416240a9595788ee`，证据清单SHA256 `b8c4907ebb4cf9fd2ec21d0a1f935093cf860326c22074346c517ec127794b9d`；完整本地产物不公开。此收尾仅记复审，不改已测试产品/测试；发布状态另列。

## 保留负结果

此前仓库外估计图复用实验保持 **NO-BUILD**，首提交错误在基线和候选都存在；合成导航中位数减少55.91%不能改变该结果。本修复有独立冻结条件，不实施memoization，不修订/重跑旧性能实验，不把本次DOM正确性升级为优化资格。

## PR68 隔离状态补漏

远端审查指出首版没有匹配独立的metadata.quarantined。核读后端source_rejection，完整全局拒绝条件只有两支：metadata.quarantined is True，或批次known_negative_sample失败。首版独立GO漏检前者，不能据此宣称覆盖了隔离状态。本修订单独捕获quarantined布尔值，纳入既有来源匹配和effect依赖；另一负标记保持真时，其变化仍撤销旧接受。不增加资格政策；逐行证券代码/复权冲突仍由原来源与snapshot身份边界处理。

先加回归：首版完整红灯34通过/2失败，分别为隔离标记变化第一提交旧SVG及A→B→A后的旧成功恢复报告。首次红灯输出停在24项，保留原日志；将DOM节点对null断言等价改为布尔比较后，完整36项得到上述两失败。没有据日志推断中止原因，也没有修改门槛。加入单一隔离标量后，新归属DOM36＋既有App2共38/38通过，完整Node955/955与TypeScript/build再次通过，0跳过；原大chunk告警保持。

独立补充冻结5项隔离断言，修订前2通过/3失败，修订后5/5通过；原38项归属回归再次全部通过，独立编译通过。独审再次核对完整source_rejection两支均独立进入上下文；最终源码SHA256 `5c3b94e93af14e767e850033264ca039124cc3033136aaf238e68ee3b6e8afb7`。

原性能NO-BUILD、未跑Python及原生浏览器/实源/Windows/预测边界保持。该补漏不引入其他界面功能或优化；最终精确提交复审及远端自动审查按PR68记录。

## PR68 已发布报告消费者补漏

第二轮远端审查指出，父App的sourceResearch只在子组件effect收到null后才清除；两个RecordDetails位置可在首提交继续显示旧相邻价格。完整引用审计确认只有App→两处RecordDetails→AdjacentSourceDetails→adjacentSource这一外部消费链。首版内部图形GO及隔离标记补漏均未覆盖此边界，失败结论保留。

编码前补充原首提交条件后，实际SingleResearch＋两个RecordDetails和App等价发布回调的仓库父测试得到39通过/6失败，覆盖batch、两端序号、资格、known-negative及quarantined的首提交遗漏。将既有来源上下文捕获/匹配移至adjacent-source，SingleResearch与发布绑定复用；绑定只保存标量快照，消费者每次渲染同步校验。原快照/截止、记录成员及逐行链接检查保持，没有重算相邻值。

独立实际App补查发现异常日线→分钟→日线的卸载返回边界；仓库测试改用与App一致的日线条件挂载后得到44通过/1失败，保留第一提交旧相邻值复活证据。最小修复为存在已接受activeView的owner清理时额外发布一次null；先撤销内部引用/Generation，再清外部绑定。无已接受报告的初始StrictMode清理不增加发布，旧query-ID清理仍由binder拒绝。原“所有发布次数保持”仅适用于先前未覆盖卸载的操作，不能据此免除永久撤销；新增这一次清理发布明确列为修复的一部分。

最终仓库归属/消费者DOM46＋既有真实App2共48/48通过，完整Node957/957、TypeScript/build及diff检查通过，0跳过。新增纯绑定检查标量快照不引用可变metadata、等价上下文继续关联、两个独立负标记单独撤销；原accepted-report数学、精确值与DOM保持。另验证卸载已接受owner恰多一次null、未完成旧请求在重挂载新接受后不能再发布。产品仅SingleResearch与adjacent-source两文件；App、RecordDetails、SourceChart、EstimatePlot、后端/请求与DTO均未改。单个静态分页测试仅改为共享比较函数名。

正常App工具栏会主动撤销来源和选中记录；合成同ID直接变更用于防御该异常输入，两者分列，不声称普通用户必经此错误路径。日志及本地执行产物仍不提交；性能NO-BUILD与所有真实浏览器/实源/Windows/预测限制不变。最终独立精确提交和远端新head复审按PR68记录。

独立最终来源检查：实际App25/25与周期卸载2/2通过；StrictMode重复对应25/25与2/2通过。另有不可变prop消费者28/28、隔离5/5及原归属回归通过，31份稳定输出逐字节一致（共同SHA256仍为 `8ca5faf816c960b73308812b2aff09181cb6f6023e62286e9113b87a5701456e`）。各组重叠，不相加为独立样本。实际App测试仅适配SourceChart图形API，无原生图形/视觉资格；独立编译及作者最终日志已核对。最终两产品文件SHA256分别为SingleResearch `5eb59d9dc75dfd3d93d0ef3b52d21ef20afa8c2d6765c12ee643c1ab00ca3779`、adjacent-source `63e107db5e0faad12783992d7a6a2336d5b9dc936ff48328b5a24d343dd9fd5b`。
