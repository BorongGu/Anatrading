# 062 双股历史相关与 β：限定验收

2026-10-13。基线 `aff49d83010d439af66bec66238606b013bce3a2`；编码前范围见[冻结合同](../research/062-pair-history-table.md)。本片只把旧双股已算出的逐共同日期相关/β完整展示：默认折叠、每页50条、最新到最早，逐行保留窗口、有效区间与独立失败/覆盖原因。既有算法、API、DTO、依赖和来源资格不变。

## 本地实际通过

- 纯分页回归：空、1/49/50/51/100/101/20,000行全部可达，无过滤或原数组变更，边界夹紧；20,000行只读取当前页50个元素。小身份覆盖有序角色、query、method、analysis和截止/窗口。
- 持久化实际ReactDOM＋jsdom：默认折叠、重复开关及上下页、完整101行、预热及null、corr null/β0、独立记录/覆盖警告、同ID新对象重置、同引用内容/身份更新、缩短后再增长不复活旧页、卸载再挂载、空表；另持久化两个父流程用例：移除所选版本/改为非日线后隐藏旧报告，禁用且拦截提交，待处理请求中止，恢复目录后旧失败不覆盖新成功，卸载后旧成功不复活。该环境使用既有外部jsdom，不新增产品依赖。
- 全部前端 `node --test tests/*.test.mjs`：910通过，0失败/跳过。上项实际DOM runner单列，不算入910。
- TypeScript、Vite和预压缩构建通过；原npm配置提示、JS主包大于500kB警告保留。只验证可构建，不作页面提速结论。
- 未改后端；受影响的 `test_pair_research.py`、`test_research_api.py`、`test_research_adversarial.py`：62通过，0失败/跳过。未在此片重跑完整Python或离线qualification。
- `git diff --check`通过。本地自测首轮未失败；独立实际ReactDOM最终44项范围内交互通过，覆盖父请求中断、A→B→A、旧成功/错误、目录移除/恢复、增添/排序不误清理；其失败及修复另见下节。发布状态另记，不能由本记录推出已合并。

## 可重跑命令

```bash
(cd web && node --test tests/*.test.mjs && npm run build)
.venv/bin/python -X utf8 -m pytest tests/test_pair_research.py tests/test_research_api.py tests/test_research_adversarial.py -q
# jsdom须已在测试环境安装；不在本片安装/修改锁文件。
(cd web && ANATRADING_JSDOM_PATH=/path/to/existing/jsdom/lib/api.js node --test tests/pair-history-dom.mjs)
```

## 未验与边界

真实浏览器/截图与Windows原生没有新增证据；既知Chromium在创建页面前socket权限失败不重复尝试。jsdom没有实际布局/绘制和完整浏览器交互语义，不冒充这些验收。未读取旧Store、真实行情或捕获，未新增实源兼容、真人效率、PIT/闭合/复权、预测或交易收益证据。058及既存科学STOP不变；本片补齐历史核查入口，长期TradingView高级分析目标保留。

## 独立失败与窄修复

独立首次runner因jsdom未提供MessageChannel而失败，补入既有Node MessageChannel后继续，保留原脚本与日志。随后第2/3轮保留了6项所选版本移除、周期改为非日线及待处理请求对应的失败页面/结果；旧父组件在目录迟到更新时未清掉结果。可达链为App目录刷新先开始、切入双股后旧刷新才完成。本片窄修复复用现有daily资格与snapshot ID：失格当次渲染隐藏报告，effect失效Generation并abort，提交和成功/错误完成再检查当前资格。移除后恢复也不会恢复旧报告。无全metadata哈希、后台重取数或新增资格。

独立最初还检查了直接注入不一致cutoff prop和不存在的取消控件；前者不符合真实父组件调用路径，后者未在冻结合同中要求，单列为验收边界。实际父cutoff/窗口/左右角色变更和卸载仍须中断旧请求。原失败不删除，也不通过改动期待掩盖目录资格缺陷。

最终独立第4轮44项范围内交互全部通过，源码副本执行后与当前web/src逐字节一致；3项不受支持prop/无取消控件观察保留而不计通过。最后全前端910、构建与持久化实际DOM三个用例在目录窄修后重跑通过；后端源码无变更，前述62项结果范围不扩大。独立执行器/完整结果保留在本次验收环境，公开仓库包含纯测试、合成夹具和可选DOM runner，不声称另存执行环境随仓库提供。

独立终审接受当前源码：既有滚窗序列完整展示、每页DOM最多50行，无新模型/API/来源资格；目录变化按现有daily资格失效。未发现剩余源码阻断，发布仍按精确提交与远端审查终态确认。
