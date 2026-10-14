# 070 全事件账本分页：限定合成验收

2026-10-14 UTC。基线 main `6c472ff4c3c6d162d32f4ed8bbd08a50dcba6e79`；产品/测试候选 `99b54274bb83c18b3329ef43ebfa044ffb35683a`。结论：限定本地合成状态/功能验收PASS；最终独立代码复审GO。尚未发布。

## 范围与继承边界

[编码前设计](../research/070-full-event-pagination-design.md)、[冻结验收矩阵](../research/070-full-event-pagination-acceptance.md)与[独立设计GO](../reviews/2026-10-14-full-event-pagination-design-review.md)已纳入研究记录。只解除056最新100条入口限制，完整账本按原顺序分成最多100事件一页，初始最后100条；仍至多一个六槽展开。六槽资格、投影字段、原统计及上限不变，h1/10/20和六槽局部失格响应同样分页。

产品仅修改SingleResearch.tsx与single-event-path.ts。分页视图对象同时提供页身份，Generation与含batch的上下文负责请求/来源当前性；每次接受从page0开始，实际翻页同步清选择及撤销旧页身份。globalPosition只用于事件数组及详情ID，六槽索引仍是event.index+k。每页切片最多100，捕获最多6槽；原validator/接受扫描和整体图形渲染仍全量，未声称整组件O(100)。

## 实施者已执行

- 测试先于产品变更：初始56项中53通过/3失败的红灯保留，旧RECENT101首事件不可捕获与缺少分页/页身份合同导致失败；实现后60/60定向Node通过。
- 完整仓库Node954/954通过；无skip。包含34份原完整合成响应、六槽异常/精度/未知槽回归与新增位置上下界断言。
- 产品Python3.14受影响event/signal/research-series纯测试61/61通过；未运行全量Python产品集合。
- TypeScript与生产build通过；保留超过500kB的既有chunk告警，不作为性能合格证据。
- git diff --check通过；后端、API、shared-validator及原Python测试与基线无差异。
- 新构造14份完整纯合成响应在基线与候选分别调用未修改signal_report，完整JSON逐字节相同（SHA256 `999fa34df30a2ee9e6b181eaa741e88eac793fcee4b730e1c1b199a1ebd34d62`），包含0/1/100/101/199/200/201/19,980事件、空series、h1/10/20、负变化与invalid。这里是纯内核证据，没有HTTP/Store执行。

各测试集有重叠，不相加成独立样本数。初次本地commit因未设置身份失败，随后仅命令级复用既有提交作者；未修改全局设置，未发布。

## 独立验收实际结果

[独立验收报告](../reviews/2026-10-14-full-event-pagination-acceptance.md)针对上述精确产品候选，42/42 React/jsdom状态测试通过，0失败/0跳过。包含完整SingleResearch及HistoricalPathResearch、页面/请求/选择过期回调、同ID含batch上下文A→B→A第一commit门禁、无选择旧回调、合法/空/失格账本、h1/10/20、参数/请求/失败/卸载重置及全量只读描述符。基线缺失功能的expected-red亦独立保留。

- 合法大例20,000来源槽/19,980事件遍历全部200页，位置并集恰为0..19979，无重复或遗漏；最新100条、最早80条，主行最多100，全部位置均可捕获六槽。事件数组数字索引读取每次导航最多100；source数字索引读取每次捕获最多6。分页请求/发布增量均0；20,001槽仍被旧validator拒绝。20,000事件单独为算术用例。
- 同操作基线/候选的全部统计区DOM文本、研究/历史请求URL与参数、cache/credentials及onReport序列逐字节相同，包含两次单股研究和一次历史路径请求。负变化例test/train/test统计与请求/发布亦逐字节一致。新增四类导航与详情操作增量请求/发布均0。
- 42项中3项挂载实际App及相邻消费者，只把SourceChart替换为外部no-op canvas适配器，使用真实版本/记录表格入口；取得父接线与模拟DOM状态证据，没有完整无适配器App端到端或图表鼠标证据。
- 单次Node/jsdom大例约10,175ms，结束RSS710,971,392字节，包含fixture/DOM和既有全量图形运算。这不是峰值内存、整组件O(100)、稳定延迟、流畅性或SLA资格；没有以资源上限合格作主张。

独立报告SHA256 `1a8fd218c35f1685b6afa7410be91f98b4162a4de5772a112767487b514d3f2a`；证据清单SHA256 `2279972fe1d48f68533dd91cfa5b512681d85633315e277692de405beb763ac4`。两组DOM/request golden分别SHA256 `8945b8c57b6c4fb6286032decc5acc017da9475a5775d5aaf293d9351137a564`、`068133d6785547d478b32071781dcae94ab4c132d4a405d5ec97ef6dcbcc7537`。

初期独立测试的嵌套表定位、null/undefined、分段文案、path-match名称、App夹具引用拆分等工具错误均保留并修正测试，没有修改产品迎合测试。App原有SourceChart/SingleResearch同层query_id重复key警告基线亦存在，列为单独后续问题，不宣称已消除或取得更广泛协调安全。

## 未验与停止边界

原生浏览器历史EPERM未重试，jsdom不等于视觉、真实键盘、焦点边界或窄屏验收。Windows、真实来源/行情、完整App、HTTP/Store、稳定性能/SLA、真人效率与金融/预测/交易效果继续未验。无旧数据库、原始行情、采集、新API或依赖，也不公开本地日志/私有数据。最终独立复审核验文档候选`caaea907a87e9194143eabe46facc63f25e2665c`，确认产品/测试与`99b54274`零差异并给出GO；[复审报告](../reviews/2026-10-14-full-event-pagination-code-review.md)SHA256 `4c7eb9ac6cffb131f7921b76144f16f77332d3eb724234252564891a106308a4`。该文档候选再次实跑Node954/954、Python61/61与TypeScript/build通过。当前文档收尾不改产品/测试，按复审约定继承GO；发布状态仍另列。
