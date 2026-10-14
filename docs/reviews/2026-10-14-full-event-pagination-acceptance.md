# 070 全事件分页独立验收

2026-10-14 UTC。结论：**限定本地合成状态/功能验收 PASS，无新增分页产品阻断。**

## 冻结与方法

- 基线6c472ff4c3c6d162d32f4ed8bbd08a50dcba6e79；候选99b54274bb83c18b3329ef43ebfa044ffb35683a。
- SingleResearch.tsx SHA256：20210d7230438228635feeace29b7e3921ad21d65f6824e9bd24a64f3dce6b03。
- single-event-path.ts SHA256：64a4cf1a268d0908bfbbd336e0b36a870bef62e0d1a87ab84672fd369660ad18。
- 编码前设计53e189fd473d1fe1119a722d3fad251c9e5c0447288bba7a29ebcb306806522d，矩阵16d89e5a1a1db1abc96d9778538a2884a6a6451411db4e4b9cc853b8e8187fe7。独立oracle在读取实现前冻结：e3072bc7be8b7e031eaa299fc999168ef639cc9a9c7dc65b2613c123765222bb。
- 全部测试、生成物、归档和报告均在仓库外；未修改仓库。Node24.19.0、既有React19.3和外部jsdom、产品Python3.14虚拟环境；无新增安装。实际SingleResearch及其HistoricalPathResearch子组件均保留。网络全部mock，无HTTP/Store执行。
- 正常数据由未修改signal_report纯内核生成，包含14份完整响应，均先经现有assertResearchReply；fixture SHA999fa34df30a2ee9e6b181eaa741e88eac793fcee4b730e1c1b199a1ebd34d62。额外故障注入明确分组；没有把畸形数据当正常可达案例。
- 独立基线归档重建后实际复现101事件首条不在DOM、无导航、capture首条拒绝。保存expected-red，不用产品修改后的基线假冒。

## 实际通过

### 42项React/jsdom状态断言

1. N=0/1/100/101/199/200/201；空series和非空series无事件分开；各页DOM事件日期严格对应独立公式[max(0,N−100(p+1)),N−100p)。每个原位置恰一次、原顺序不变、原生四按钮边界/文字/type准确。所有小例各页首尾点击六槽准确；ID使用绝对事件位置，来源槽使用event.index。
2. 完整内核早期负变化、invalid、overlap_excluded、purged、尾部immature和分段均保留。负变化在最近100之外，最早页可开，110→105及中间逐槽原值一致。翻页前后整个统计区文本、分位数、基线和当前趋势与DTO完整JSON相同。
3. page0→1→0旧null-selection行、旧行、导航、Close、Escape、toggle逐一不能改变新选择/页面/焦点。React提交前重复同一旧导航最多执行一次；同页和越界回调不清详情。同页A→B旧Close/Escape/行回调、新响应旧Close/Escape/toggle均失效。当前关闭/Escape返回当前行焦点；关闭外层账本清详情、保留页码，重新打开不恢复详情。
4. train/test保持页面、选择和六槽投影。所有参数编辑（包括空的未提交数字输入）、更新开始、当前失败、正常query-ID替换、卸载清旧状态；h1/10/20均可分页且无六槽，切回5后重新接受。
5. 同analysis_id新内容、同内容新对象、同一对象重复接受分别重置page0；201→1/0不留越界。snapshot/batch/cutoff/ordinal_start/ordinal_end逐个同ID A→B→A，在Profiler第一提交即隐藏旧账本，返回A不复活，不自动增加请求。上述同ID直接render属于故障/状态注入，未冒称均为普通App用户操作。
6. 请求乱序、旧成功/失败/abort、未完成请求上下文往返、卸载旧回调均不能建立/替换新账本。覆盖056原12项过期场景类别（四上下文往返、前代次三回调、同代次三回调、旧成功/失败），并扩展batch及页面身份。
7. 六槽接受故障与reversal-source-only故障独立测试：原账本仍完整分页；后者六槽仍可用。单行捕获故障显示原局部错误，翻页清错、其他页正常。故意接受后原地变异只用于注入捕获失败，不赋予违规变异合同资格。
8. 所有201位置直接capture；负数/上界/超界/小数/NaN/Infinity拒绝。原报告完整值和递归可扩展性/属性描述符不变；独占投影正常工作。

### 实际App接线，范围有明确边界

3项包含在42项内，挂载实际App、SingleResearch、HistoricalPathResearch、选中记录详情及相邻消费者，使用实际版本选择、更新图表/研究表单、账本/原始记录summary、源记录表格点击。

- 分页/六槽、同上下文源记录选择保留页面/选择；参数编辑立即清账本；相同内容新响应回page0；选空来源卸载研究。
- 相同query_id更换batch经更新图表实际路径卸载旧研究，迟到响应及旧页回调不能恢复；新响应从最近页开始。
- 历史路径子组件真实表单另发path-match请求；其错误独立。四种分页/展开/关闭没有额外请求。

**只有SourceChart在外部编译副本替换为no-op canvas适配器；没有替换App、研究组件或统计/记录消费者。** 因而仅取得“App父接线＋模拟DOM状态”的资格；真实图表点选、完整无适配器App端到端、canvas/实际浏览器均未验。源记录选择用实际表格可达入口，没有伪造chart鼠标动作。

### 合法大响应与有界读取

独立单次大样本运行：20,000来源槽、19,980事件、200页。遍历所有页DOM日期和位置并集，严格等于0..19979；最新页100条、最早页80条、主行最大100。19,980个位置全部直接六槽capture成功。每次分页用Proxy观测事件数组数字索引读取，最大100；每次capture来源数组数字索引读取最大6。分页增量请求0、onReport0；完整DTO深度值不变。20,001来源槽旧validator仍拒绝。另列20,000事件纯算术覆盖，未当作合法后端DTO。

该次Node/jsdom运行约10,175ms，结束时RSS710,971,392字节；这是一次合成测试进程观测，包含测试fixture与DOM及旧全量图形运算。**不是产品峰值内存、设备流畅性、总组件O(100)、稳定延迟或SLA证据。**

### 基线不变性

归档基线/候选执行相同SingleResearch及HistoricalPathResearch操作，完整统计区DOM文本、研究/历史请求URL及参数、cache/credentials、onReport序列逐字节一致：观察文件SHA8945b8c57b6c4fb6286032decc5acc017da9475a5775d5aaf293d9351137a564。包含两次单研究请求及一次历史路径请求，未假称总请求恒为1。

额外负变化分段例的test/train/test统计全部文本、请求及发布序列逐字节一致：SHA068133d6785547d478b32071781dcae94ab4c132d4a405d5ec97ef6dcbcc7537。新增分页/六槽操作增量请求和发布均0。

实现者另已报告954/954全Node、61/61受影响纯Python、TypeScript/build及14份完整内核JSON基线/候选逐字节一致。这些由实现者独立执行，本报告不将其写为本验收者亲自运行；原34份fixture模型/负例回归包含在其全Node集合。最终提交的静态复审由另一审查者负责。

## 保留的测试工具失败与既有警告

最初外部测试的tbody后代选择器把嵌套表头误计为第7槽；改成明确table.tBodies[0].children。无导航元素的null/undefined期待、分段文案“未计入”、历史请求path-match名称、App fixture.query与fixture.reply.query序列化后分离等测试假设已修正。保留preliminary日志；没有修改产品来消除测试错误。

App目前SourceChart和SingleResearch同层重复使用query_id作为key，会出现React重复key警告。基线相同接线已存在，本次产品未改App；本轮覆盖状态仍通过，但不能把警告消除或更广泛React协调安全算作通过。本项可独立后续修复，不扩大070两文件分页变更。

## 未验与停止边界

真实浏览器、实际键盘Enter/Space默认激活、导航disabled边界真实焦点、窄屏视觉、原图canvas、无适配器完整App、HTTP/Store、旧数据库/真实行情、Windows、真实来源兼容、性能资格、用户效率与预测/金融效果均未验。不重试或绕过历史原生浏览器EPERM；未新增API/后端算法/真实数据获取/公开发布。本地jsdom点击、Escape函数和focus行为仅为模拟状态证据。

42项测试0失败/0跳过；独立大例及两组基线golden通过。仅在上述限定范围给出PASS。
