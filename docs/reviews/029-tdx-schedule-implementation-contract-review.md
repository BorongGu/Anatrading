# 029：U4 定时入口实现合同反方

2026-10-08。实际只读审[合同v0.1](../contracts/TDX_DAILY_SCHEDULE_IMPLEMENTATION.md)，SHA-256 `f547c5b76dd1f2eaac993496dceaef700fc867e485b6e7d7e59bd2956b68a22f`，现有 `tdx_acquisition.py`、CLI、客户端锁实现、027方案复审及真实分钟未知报告。本轮只新增本评审文件；未改产品代码、注册任务、请求行情或打开数据库。

## 结论

**同锁贯穿和单控制文件归槽两项简化通过，无新增方案级P1。具体合同需补下述两项P2后再解冻编码。** 这些修订不需要新框架或第二套账本。注册、真实刷新和强停资格仍冻结，当前分钟未知保持。

## 已闭合的不变量

- `due` 持同客户端锁贯穿 reserve、内部采集和归槽，取消释放再重入以及公开派发参数，减少活owner授权分支。OS锁在崩溃后会释放，所以持久reserved、必需标记和普通acquire全局门禁仍不可省略。合同已保留这些条件。
- `preparing` journal及linked均先于任何POST持久化；通用journal不接受空identity，只有严格匹配scheduled关联走保守中止。reserved无journal、双收据单边写成、关联不符均保持未知。
- 旧publication恢复与新槽派发分开；恢复本次不占新槽，终态current不得通过普通acquire重新取数。归槽逐字段比对，原journal终态先落盘，单个dispatch原子替换同时归原槽与关闭active，覆盖原方案两控制文件单边写入的窗口。
- `refresh_unknown`同会话阻断。真实分钟观察在current中保持refresh_unknown；due选择更保守的零RPC策略，与普通手工既有会话变化规则分开，未清除真实未知。
- 150秒业务预算与Task Scheduler180秒强停边界分开；每阶段取剩余预算，不把系统退出、HTTP成功或时间经过当作外部任务终结证明。工作台继续是唯一写者。

## 编码前补足P2

1. **每次新POST的民用时间边界。** 合同目前在选槽时核start/end，POST前明确写了单调预算。末日接近end_at派发后，后续import可能已越界；单调剩余仍充足。需明确所有新POST前重新读取注入UTC，核该槽due_at、计划start/end、相对持久观测的回拨及主机时区；失败保持当前持久阶段，不发POST。恢复GET允许期限后进行，不授予refresh/import。新增用例应在refresh之后推进UTC至end_at之外，确认import零次且原current/active保持可读未知。
2. **控制对象的语义校验。** 合同列出active state，但slots status/result及空关联约束尚未穷举。需固定pending、closed_no_target与已派发状态全集；pending/closed不得携带派发关联或结果；active恰好绑定一个已派发槽；无active时不得遗留非终态派发槽；终态result的run/dispatch/plan/slot/root/port/client/symbol/date必须一致。slot状态与result.status映射明确，不接受未知status、缺字段或extra字段；owner FILETIME为精确整数或十进制字符串，禁止经浮点损失身份。负例覆盖格式有效但关联矛盾的dispatch，普通入口与due均零POST。

## 事实核查与资格限制

实际核私有 `sse-closed.html` 和 `sse-weekdays.html` SHA分别为合同的 `7ea10c…`、`f5d957…`。前者正文含2026年10月8日起照常开市、10月10日周末休市；后者明确每周一至周五且法定假日与本所公告休市。8—14日的有限SH名单可由两份正文推导。未重新请求网页，保存时间不能伪称精确网络接收时刻；不扩充到SZ/BJ、停牌或供应商完成保证。

Task Scheduler的Hidden设置只代表任务可见性，不能单独证明交互会话下Python控制台窗口隐藏。本轮仅生成XML应准确标为未注册、未运行、窗口行为未验；真正后台启动策略在后续注册合同和实测闭合。7日与单证券属于首次资格，长期自动续期、生命周期和分钟来源仍须继续推进。

合同修订关闭两项P2后，可允许列明范围的代码与XML生成；之后还需独立代码评审和实际系统触发资格。当前不能宣称已实现日常全自动更新。

## v0.2 复审

实际重读修订合同，SHA-256 `845f061b8c48cbccfb2b77a8b3fff03a242d381bc7483b610ac8e7d35cf179cb`。**两项合同P2关闭，允许按所列范围开始产品代码、测试及XML生成。** 注册、真实行情POST和系统强停资格仍未解冻。

- 民用期限：新POST前明确重新读取UTC，独立核主机时区及偏移、回拨与原槽due/start/end并持久前值，越界不能开始import。结合单调总预算，满足期限与预算两种独立边界；代码和故障用例须实际覆盖refresh后跨end_at。
- 控制语义：固定四字段slot、八状态、open/closed约束、空关联条件、active恰好绑定一个非终态槽、终态result逐字段一致及UUID唯一性。格式有效的矛盾对象需invalid_schedule_control并零POST；原生FILETIME实现时保持精确类型，不能使用浮点中转。
- 模板声明已区分Hidden任务可见性与原生控制台窗口行为，生成文件不能充当实际无人干扰运行证明。

本复审只证明合同明确和方向可实现，不能替代锁持有、原子替换、恢复关联与预算门禁的独立代码检查。真实minute current保留和零RPC行为继续作为下一轮可核资格边界。
