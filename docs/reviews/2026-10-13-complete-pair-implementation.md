# 051 全成对双窗实施审查与有限验收

2026-10-13。本地实现，未推送/合并/部署。编码前冻结提交46448fd；本记录与实现同提交。最终代码保持049精确核、来源helpers及旧DTO不变。

## 独立反方及修复

独立只读审查核对新后端、API、DTO、UI、控制器接线及测试，未自行运行测试。首次发现一个P2阻断：全部日期未知时，空候选日期分支遗漏未知行的local_source_conflict/unclassified_source_failure，但DTO要求其诊断存在，导致合法失败报告被拒绝。

先新增回归并实际失败（缺这两项原因）；再合并未知行scoped reasons。新增all_unknown跨Python→DTO样本通过。二次静态审查确认原阻断已修复，未发现新阻断，准许最终回归与本地提交。另依建议补全部50成员均非常量的2450可算相关、四成员0/60/120共同端点断言。

051初版“T摘要与全部端点相同”已明确纠正为“T的相关摘要与各成员共同起止端点相同”；两世界C完整121价格序列不同。验收公式和反例未调整。一手阅读归属及公开链接已补全。

## 实际通过（最终代码）

- 受影响Python 194 passed，0 failed/skip：test_group_pair_research、test_group_pair_api、test_peer_neighbor_research、test_peer_neighbor_api、test_peer_relative_research、test_drawdown_episode_research、test_drawdown_episode_api、test_research_api。
- 完整Node 684 passed，0 failed/skip；其中051的新DTO/请求/SSR/回调56项。全部Node以test-concurrency=1运行，合成Store仅指定的新临时根；未读取旧研究Store。
- TypeScript + Vite production build通过；git diff --check通过。保留npm http-proxy环境警告与bundle超过500kB警告，没有调大阈值掩盖。

覆盖：先异常输入；四成员两世界手算/有理数oracle；六成员结构；50成员2450cell及全非常量2450相关；恒价、恒定非零、近常量、符号翻转；各对逐目标049的相关对象（含非边界/常量）完全对照；缺/额外/重复/未知/截止日期与全源身份反证；新合成Store完整/投影/API一致、原件损坏/丢失后恢复、预算先于读取、双方指定日期原记录回查；置换与新来源身份的未来合法追加保持固定截止数值；受控整数/显示/2MiB失败；DTO keys/ID/完整组合/日期/常量交叉乘积/计数/估计边界/SHA篡改；一次GET、迟到fetch/hash失效、两表默认折叠、完整50对分页和双方回调身份。

预算：canonical UTF-8 JSON包括analysis_id，后端与DTO同为2MiB。边界等于实际字节数成功、少一字节失败，API受控过限整次拒绝。50成员测试仅正确性与序列化，不是性能benchmark；输入上限不保证全部合法输入均能装下。

## 原始失败与未验范围

保留首次异常测试因模块尚不存在的收集失败，以及上述独立审查P2真实回归失败；最终所列检查无遗留失败。初版测试未出现其他失败。原始日志保留在实施环境的专用临时证据目录，不提交个人或运行产物。

未跑fullpytest；未启动监听服务/端口/浏览器、未接真实行情、旧Store、账户/依赖/部署。SSR使用Vite middleware-only转换，无listen；API为ASGI内存transport。SSR/回调与控制器测试不等于浏览器实际挂载/布局/焦点验收。Windows原生、真实样本兼容、实际浏览器、性能/峰值内存、真人效率、预测/交易效果均未验。未重新启动任何已停止的性能基准。
