# 073 估计图与报告归属修复

2026-10-14；编码前条件见[冻结研究计划](../research/073-estimate-report-ownership.md)。本次仅修复SingleResearch报告的展示当前性。

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
