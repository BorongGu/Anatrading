# 051 全成对双窗实施审查与有限验收

2026-10-13。编码前冻结提交46448fd；实现5fbd42c，原因码与测试生命周期修复8668c5b。以下为发布前验收记录，不含部署。最终代码保持049精确核、来源helpers及旧DTO不变。

## 独立反方及修复

独立只读审查核对新后端、API、DTO、UI、控制器接线及测试，未自行运行测试。首次发现一个P2阻断：全部日期未知时，空候选日期分支遗漏未知行的local_source_conflict/unclassified_source_failure，但DTO要求其诊断存在，导致合法失败报告被拒绝。

先新增回归并实际失败（缺这两项原因）；再合并未知行scoped reasons。新增all_unknown跨Python→DTO样本通过。二次静态审查确认原阻断已修复，未发现新阻断，准许最终回归与本地提交。另依建议补全部50成员均非常量的2450可算相关、四成员0/60/120共同端点断言。

051初版“T摘要与全部端点相同”已明确纠正为“T的相关摘要与各成员共同起止端点相同”；两世界C完整121价格序列不同。验收公式和反例未调整。一手阅读归属及公开链接已补全。

## 首实现5fbd42c的实际通过

- 受影响Python 194 passed，0 failed/skip：test_group_pair_research、test_group_pair_api、test_peer_neighbor_research、test_peer_neighbor_api、test_peer_relative_research、test_drawdown_episode_research、test_drawdown_episode_api、test_research_api。
- 完整Node 684 passed，0 failed/skip；其中051的新DTO/请求/SSR/回调56项。全部Node以test-concurrency=1运行，合成Store仅指定的新临时根；未读取旧研究Store。
- TypeScript + Vite production build通过；git diff --check通过。保留npm http-proxy环境警告与bundle超过500kB警告，没有调大阈值掩盖。

覆盖：先异常输入；四成员两世界手算/有理数oracle；六成员结构；50成员2450cell及全非常量2450相关；恒价、恒定非零、近常量、符号翻转；各对逐目标049的相关对象（含非边界/常量）完全对照；缺/额外/重复/未知/截止日期与全源身份反证；新合成Store完整/投影/API一致、原件损坏/丢失后恢复、预算先于读取、双方指定日期原记录回查；置换与新来源身份的未来合法追加保持固定截止数值；受控整数/显示/2MiB失败；DTO keys/ID/完整组合/日期/常量交叉乘积/计数/估计边界/SHA篡改；一次GET、迟到fetch/hash失效、两表默认折叠、完整50对分页和双方回调身份。

预算：canonical UTF-8 JSON包括analysis_id，后端与DTO同为2MiB。边界等于实际字节数成功、少一字节失败，API受控过限整次拒绝。50成员测试仅正确性与序列化，不是性能benchmark；输入上限不保证全部合法输入均能装下。

## 原始失败与未验范围

保留首次异常测试因模块尚不存在的收集失败，以及上述独立审查P2真实回归失败；最终所列检查无遗留失败。初版测试未出现其他失败。原始日志保留在实施环境的专用临时证据目录，不提交个人或运行产物。后续复核另发现下述原因码和测试生命周期问题，首轮无阻断结论不覆盖它们。

未跑fullpytest；未启动监听服务/端口/浏览器、未接真实行情、旧Store、账户/依赖/部署。SSR使用Vite middleware-only转换，无listen；API为ASGI内存transport。SSR/回调与控制器测试不等于浏览器实际挂载/布局/焦点验收。Windows原生、真实样本兼容、实际浏览器、性能/峰值内存、真人效率、预测/交易效果均未验。未重新启动任何已停止的性能基准。


## 后续原因码与测试生命周期修复

负责人复核发现新增错误字典未限定自身属性：constructor/__proto__/toString等继承键可被当成说明，导致诊断返回函数或请求提示泄漏native code文本。上轮静态审查漏检。新增独立错误测试先实际取得2项失败，再将两处查找改为Object.hasOwn，并将peer_neighbor_泛前缀匹配收窄到三个明确的核错误；陌生、安全或不安全错误保持既有安全回退。实际banner表达式测试覆盖原型键、陌生前缀、非Error、不安全内容、已知预算和原件/服务恢复提示。独立只读复核认可修复，无新代码阻断。

本轮完整Node首跑682通过、1测试文件失败：先注册的DTO测试结束时after关闭Vite runner，而同文件顶层await仍在加载SSR，5项SSR测试尚未注册。修为SSR模块全部加载完成后再注册测试和清理hook；所有原断言保留。修脚本曾因工作目录前缀错误失败，意外启动的未修重跑已取消，其日志保留，不计通过。

最终相关Node 59项通过，完整Node **687通过、0失败/跳过/取消**；TypeScript/Vite再次通过，原npm环境及大chunk警告保持。Python没有修改，沿用同一Python代码的194项通过记录，本轮未重复Python。git diff --check通过。README和research-status补入当前功能入口，直接链接本实施记录；没有新增资格副本。本轮回归未覆盖实际DOM/浏览器；后续独立模拟DOM验收见下节，实际浏览器、真实行情、Windows、性能和金融效果仍未验。


## 独立 React/JSDOM 有界交互验收

独立验证者在最终产品提交8668c5b上实际挂载React组件，13组通过、0失败，React/JSDOM/window错误与警告记录均为空；这项执行与上文独立静态代码审查分开。冻结协议及合成样本，复用既有隔离依赖，没有安装、服务监听或仓库修改。前后5756个仓库及既有隔离依赖文件SHA-256一致、无增删，HEAD及干净工作树不变。私有验证脚本、原始日志及运行产物不提交。

覆盖11成员55对完整与不可算报告的两窗默认折叠、50→5→50分页、边界按钮、全55对保留、双方实际日期回调和关闭选中端点；真实UniverseResearch的group_pairs接线中，一次提交仅一个GET意图，取消/切换模式/改截止/卸载各自晚到成功与拒绝共8条路径不污染新结果；不同合法analysis_id后折叠、页码及选择重置。重置使用实际父级，加载时控制器也清空结果，不能独立证明key的因果作用。

本验收使用真实React与JSDOM模拟DOM、合成fetch，不是实际浏览器或HTTP验收；未跑50成员25页DOM遍历、pagehide/pageshow、视觉布局、键盘/焦点、真实Store、Windows、性能或金融效果。隔离测试未纳入仓库持续回归。

## PR41精确9909d98复审：Unicode原文失败报告

[Codex P2评论](https://github.com/BorongGu/Anatrading/pull/41#discussion_r4255415051)指出完整响应预算误用ASCII专用canonicalJson，合法“停牌”原始价格token会令整份失败报告被拒绝。此前静态无阻断和有界DOM结论均没有覆盖这条路径，本轮不重放那些结论。

先增加实际Python解码合成capture生成的失败报告，包含中文价格原文、引号/反斜杠、换行/tab/NUL、U+2028/U+2029、128个astral字符，以及中文与constructor/__proto__/toString原始失败码。取得3项跨语言红失败。只改完整响应预算后，继续复现128个码点被JavaScript UTF-16 length误判；修复码点长度后，又复现诊断计数same调用仍以ASCII序列化中文键。三阶段原始失败均保留。

最终新model以JSON.stringify后UTF-8字节数执行原2MiB硬限，原文长度按码点与Python len一致，诊断计数按自身键逐项比较；保留ASCII计算身份canonicalJson/SHA和全部共享helpers/旧协议。独立只读复审重新核查所有same调用，剩余用途只有固定格式、身份ID、日期和计数，无允许的原始Unicode字段；此次复核未执行测试。

实际跨语言测试确认完整Python ensure_ascii=False序列化字节数与前端一致（含特殊字符），反转对象键顺序不改字节数；多字节输入即使UTF-16文本长度低于2MiB，真实UTF-8过限仍整份拒绝。新SSR验证GroupPairResults全部成员、两窗全部不可算对，以及选中来源的中文/astral原文和未知码安全回退；未将SSR称为实际浏览器或重跑的JSDOM验收。

最终受影响Python测试27通过（包含新增fixture验证及新功能API）；产品Python无修改，原194项记录仍适用于原代码，本轮未重跑全套194。完整Node **691通过、0失败/跳过/取消**；TypeScript/Vite及diff检查通过，原npm环境/大chunk警告保留。真实行情、实际浏览器、Windows、性能/人效和金融效果仍未验。该修复推送到PR41同分支，禁止用旧head的review状态代表新head；合并仍待精确新head复审。
