# 多股条件筛选界面整合独立评审

日期：2026-10-11。首轮核读与合成探针：05:29–05:31 UTC。

评审对象：[界面计划](../plans/2026-10-11-research-ui-integration.md)、[032](../research/032-explainable-stock-filters.md) 与最终 web 实现。**当前决定（06:21 UTC）：最小界面接线的代码、合成模型、静态组件与构建审查通过，详见 §8；真实浏览器与交互体验仍未验，后端 RSS 资源资格仍未通过。** 05:48 的设计批准见 §7，首轮暂缓与反例保留如下。不要求重写界面，不增加规则框架或新依赖。

## 1. 已核实的范围与可接受决定

已读根 `AGENTS.md`，032 全文及设计/实现评审，`stock_filters.py`、`research_api.py`、`universe_research.py`，Store 的规范 JSON/身份方法和 workbench 安全错误边界。前端核读 `CrossResearch.tsx`、`App.tsx`、`research-model.ts`、`research-types.ts`、`ResearchResults.tsx`、`api.ts`、样式、包清单及现有研究界面/模型测试；另读既有浏览器验收报告。

计划的大部分必要合同已经写清，以下应原样保留：

- 一个条件请求同时返回原集合结果与筛选证据；关闭条件走原 universe。没有第二份选择器、逐条件查询、自动重试或展开时重新研究。
- 组内 AND、组间标准 OR。`T OR U` 入选且保留 partial，`F AND U` 可排除且保留未知；`F OR U` 待核。源日期 gate 为 unknown 时全部启用原子 U。未启用 V 的失败只留在基线，不增加 M/DD 筛选的 partial。
- 阈值用文本控制与十进制字符串移位。M/DD 百分比的 16 位输入变为最多 18 位比例，负零/尾零规范化；不先 `Number`/`parseFloat` 再除以 100。前端不重算 Fraction、V、真值或名次。
- 用提交时冻结的组内容映射响应的 canonical 顺序；不能把响应第 0 组固定解释为编辑器第 1 组。跨组相同原子可以复用证据，全部成立、失败和未知引用都可查。
- 成员、D/N、规则及启用状态一变，立即失效并清报告。同步提交锁在异步哈希之前建立；旧成功、错误和 finally 均受代际约束，取消不会声称服务端 CPU 已停止。
- 多股草稿只提升到 App 局部状态，报告不随导航保留。搜索不改变成员，目录丢失版本也不静默删成员；Back/Forward 与 bfcache 单列真实验收。
- 复用现有字体和配色；自然中文、文字状态、就近原因、原生表单/展开结构及窄屏纵向阅读都合适。当前没有浏览器证据，不能把字体、留白、焦点或窄屏效果写成已经通过。

## 2. R1：实际窗口与旧集合的请求末端必须分开

**必要阻断：界面显示与新响应校验。** 计划 §2.2 要沿 `result.universe.members` 排序并显示实际起止；§5.2 同时引入 `member.window`，但尚未明确两者端点冲突时使用哪一处。当前 `UniverseResults` 直接显示旧成员的 `start_date/end_date`。

实际反例：来源只有 2026-01-01/02，请求 D=2026-01-03、N=2。05:31 UTC 探针得到新 `window.actual_groups=0`、`first=last=null`、`start_date=null`，但 `end_date=2026-01-03`；旧 universe 同样保留该 end_date。032 实现评审已将此列为 I1，作者正在修新投影。

**最小修订：**

1. 在计划明确：条件结果仅从旧 universe 取排序、原名次、原数值/原因和广度；新列表及证据的“实际起止”均取对应筛选成员的 `window.start_date/end_date`。不得用旧 universe.end_date 或请求 D 补空。
2. 缺 D 时，新 window 的实际 start/end、first/last 都为 null，actual_groups 为 0；请求截止单独显示 D，并显示“缺少截止日期记录，未形成此次窗口”。短历史但存在 D 时保留实际已有窗口，不能也清成空窗口。
3. 把这一差别加入 UI06/UI09 的响应与展示 fixture；保留旧 universe 兼容 golden。等待 I1 修复与复验后，再冻结新 window 的身份字段。UI 不自行修正一个不一致的 API 响应。

**通过条件：** 同一成功响应里，旧 universe.end_date 仍为 D，新 window.end_date 为 null；界面没有把 D 放进“实际末日”，仍保留请求截止与待核原因。校验器既接受这个合法差别，也拒绝新 window 空窗口却伪造实际端点的响应。

## 3. R2：rule_id 的精确哈希对象需要一次同步冻结

**必要阻断：前端 expected rule_id 的实现依据。** 计划 §5.2 与候选代码一致，使用 `_identity({canonical_rule, policy_versions})`；032 §6.2 第 2 条仍写另一组顶层键：`rule_schema_version, canonical_rule, logic_policy, comparison_policy, source_gate_policy`。两个对象的结构不同，window 版本的绑定也不同。不能让前端和后端分别照两份已批准文字实现。

探针使用唯一规则 `momentum / gte / "0"`：

- 候选实际 rule_id：`3da65f5831498101d75e47d038536df66c6fafaeb7a671f896b397b8460f1a7f`
- 按上述 032 字面对象和相同政策值构造：`f58975607b3349da4a0bd2d34b247f63fbc5f21ef5b776191db89303cb0b9e69`

**最小修订：** 请 032 作者明确采用哪个对象并同步正文；建议沿用实际 `{canonical_rule, policy_versions}`，不为文字漂移重写实现。界面计划链接该冻结决定。固定一个含两组、跨组共享原子和非规范输入尾零的合成 golden，同时记录规范 JSON 的确切字节、policy_versions 与 rule_id。Store 当前规则是递归键排序、紧凑分隔、UTF-8、无 NaN；数组保留已经规范化后的顺序。不得把 JS 默认插入顺序或 locale 排序当作同一合同。

**通过条件：** Python 与前端对冻结 golden 的规范字节和 rule_id 完全相同；输入组/原子反序、尾零、负零规范化不改变身份；阈值和政策版本变化会失配；组标签仍正确映射回提交时的编辑顺序。只核验规则内容身份，不引入客户端来源/算法认证。

## 4. 两处实施说明，可随本轮答复澄清

这两点不另扩成设计阻断，也不要求新的后端错误格式：

1. §6 的“参数/阈值/重复规则就近聚焦”应区分来源：前端本地校验可定位具体输入；后端仅返回 `{error: code}`，无法唯一归属的阈值/重复组错误应聚焦规则区的错误摘要，保留全部输入。不要凭错误码猜是哪一行，也不为焦点新增字段路径协议。
2. 新端点的 512 KiB 限额应覆盖成功和错误正文。现有 `checkedFetch` 在非 2xx 分支直接 `response.json()`；新封装若先调用它，错误正文会绕过新限制。用本片窄封装在解析前计累计字节，超限停止读取并给安全错误即可；旧端点不改。

## 5. 可执行的最小验收门槛

沿用计划 UI01–UI11，无需另造通用测试平台。作者修订后先写以下合成用例，再实现：

| 门槛 | 必须断言 |
|---|---|
| 请求与基线 | 未启用条件只请求 universe；启用只请求 universe-filter 一次，基线/筛选共享同一响应；展开与状态过滤零额外研究请求，分母与原名次不变。 |
| 精确输入与组映射 | `5.0000000000000001% → "0.050000000000000001"`；最大跌幅输入 `10% → "-0.1"` 并回显 `回撤 ≥ −10%`；过精度拒绝，V 不带百分号。两组反序、共享原子及全部 proof/false/unknown 引用仍对应正确的编辑组。 |
| 真值与失败 | 服务端同显为 5.00% 的 F/T 保持原徽标；selected+partial、excluded+partial、F OR U、gate U、仅未启用 V 失败、合法零值、全部未知和全部排除各有 fixture。不能从缺值推断 false。 |
| 来源与窗口 | R1 缺 D 反例、短历史实有窗口、不同起点、重复日期 ordinal=null、八例加 omitted_count；来源 absent/null/unverified、BaoStock 文档单位未核适用性保留。 |
| 响应边界 | 错方法/政策/rule_id/D/N/成员、孤立 source/window/atom/group 引用、非法枚举、非有限值、损坏数值文本和计数均拒绝整份报告；512 KiB 边界/+1 覆盖成功与错误正文。只查结构/引用/守恒，不重算真值。 |
| 请求生命周期 | 受控 deferred fetch 和哈希覆盖慢 A/快 B、A→B→A、编辑成员/D/N/规则、取消后旧成功/失败/finally、双击/Enter、卸载；陈旧事件不得发布结果或释放较新请求的提交锁。验证实际复用的请求控制逻辑，不只单测 Generation 自增。 |
| 恢复与导航 | 错误保留草稿可显式重试；404/409 清报告，零自动删成员/回退/循环重试；切个股返回、目录失效版本、刷新/bfcache 的模型路径有测试，实际浏览器操作另列。 |
| 静态界面与回归 | SSR 可核对中文、fieldset/legend、label/error 关联、summary、文字 partial 和一套可聚焦控件。执行 Node 全测试、TS/build、受影响 Python 集合；协调后的最终源码另跑全仓回归，旧 golden 不刷新掩盖改变。 |

批准编码后应运行并记录准确结果：

```text
(cd web && node --test tests/*.test.mjs)
(cd web && npm run build)
.venv/bin/python -m pytest -q tests/test_stock_filters.py tests/test_stock_filters_adversarial.py tests/test_stock_filters_api.py tests/test_universe_research.py tests/test_research_api.py tests/test_research_projection.py
```

上述命令是本片后续门槛，**本次文档评审没有执行这些 suite，也没有新增 UI 测试可供通过**。Node/SSR 的通过只证明所测模型与静态结构；React 实际点击绑定、焦点顺序、可访问树、浏览器历史及 bfcache、320/375px、200% 缩放、字体/对比度/触屏和截图继续记未验。

已核读[浏览器阻断记录](../qualification/research-browser.md)。同环境 Chromium 在创建页面前因 socket 权限被拒，受支持重试也被拒；本 review 未再尝试启动或绕过。接口/DOM/TS/build 可以独立推进，真实浏览器未验不会被这些结果替代。

## 6. 首轮证据、状态与下一步

- 已完成：上述源码/合同核对；只读 Python 合成探针复现 R1，并确认 R2 的两个哈希不同。没有读取私人行情、联网研究或重跑既有真实报告。
- 产品或测试改动：无；仅新增本 review，未提交/推送。
- 尚待：计划作者逐项答复与修订；032 作者冻结 R1/R2 的实际接口，并由实现 reviewer 关闭 I1；随后本 reviewer 复核后记录是否允许最小界面编码。
- 本轮没有授予 UI 已完成、浏览器已通过、Windows 已验、用户任务省时或预测/交易效果资格。030 同行入口保持后续独立设计，不纳入本片审批。

本轮核读快照：计划 SHA-256 `38f37fbe918cd05c53f65e22e6eea3efab902e2bd5dbc376cee576f5a6c24e3f`；032 `bb0a8d6979fc831b3708935f10483a0fdfe2730a1c20290a7c2e9818b7e23f5d`；候选 `stock_filters.py` `1d02f884e1a21f8dbf63b36c7421ffcb4c96e0b3523e1b0d09db3bf0863af653`。并行修订后的复核另记，不把这些快照当作最终发布版本。

## 7. 作者回应与复核决定

2026-10-11 05:46–05:48 UTC，已阅读作者在计划 §11 的逐项答复、§12 的跨语言 golden，以及 05:45 冻结的 `stock_filters.py`。最终复核对象：

- 界面计划 SHA-256：`ae467fd911a323e5ad94428061f35bb100988a76cc760e82e79486ee58aa77f1`
- 032 SHA-256：`9bffa4b72e3aed6a69d7080da7ee0eeed967ae2744368157e59583b62d3e9827`
- `stock_filters.py` SHA-256：`345b54b8683ffaf487b277931f46a550dcbe2d559fba313a423d5542d94dc571`

| 项目 | 修订与独立复核 | 决定 |
|---|---|---|
| R1 | 计划 §2.2/§5.2 明确新列表与证据仅用 filter.window 的实际端点。实际候选代码已经从真实 window 取首末日期；本 reviewer 重新运行缺 D 与存在 D 的短历史探针，确认前者四个端点字段为 null、actual_groups=0，后者保留两组实有日期，旧 universe.end_date 均保持兼容值。 | 关闭。UI fixture 仍须落实。 |
| R2 | 032 §6.2 与计划统一 `{canonical_rule,policy_versions}`。本 reviewer 从计划提取确切单行 JSON，独立运行 Python 实际 normalize/序列化及 Node 字符串十进制规范化、ASCII 递归排序、Web Crypto；双方均为 477 字节和 `ed05c4aef00f6130eda8d84f5046cecb2734e9059469be4fd481bb0b4c64272d`。反转组/原子仍同 ID；阈值/政策变化不同；原编辑组映射为 canonical `[1,0]`。 | 关闭。产品实现须再用同一 golden。 |
| 错误定位 | 计划 §6 已区分本地具体输入与服务端仅有码的规则摘要，不加字段路径协议。 | 采纳。 |
| 正文限额 | 计划 §5.1 已明确成功/错误正文均先限量读取，超限取消流，不经过旧 checkedFetch 无界错误解析。 | 采纳。 |

### 7.1 最终去重响应的接线复核

新表示已逐项与源码核对，计划 §5.2 是本片的具体接线依据；不要继续使用首轮每成员原子携带完整定义的形状：

- `result.conditions` 只存唯一 `{id,field,op,threshold}`；成员原子精确为 `{id,truth,fact_ref,reason_refs}`。`aN/gN` 绑定当前 rule_id，`rN` 绑定当前成员；跨成员共享同名 r1 不构成共享原因。编辑组与 canonical 组按内容映射，不靠 g1/g2 当原编辑序号。
- 来源通过 `source_ref → sources → contract_ref → source_contracts` 连接。只对完全相同的固定六项合同投影去重，metadata 与身份仍各成员保留；present/null/applicability 不丢。服务端内容 ID 沿用，前端不另建来源认证器。
- 原因 example 为二元组 `[date,ordinal]`，报告列定义精确为 `["date","ordinal"]`。本 reviewer 额外用坏价合成响应确认实际二元组与局部引用形状；不能再按 example.date 或旧 atom.threshold 读取。
- 同次合成探针核对了 conditions 去重、共享合同、source/query/window 连线、成员内 reason_refs 与短历史/缺截止的端点。以上都是源码与纯函数表示探针，没有验证 React 接线、用户点击或真实行情。

### 7.2 批准范围与仍待验的部分

**允许现在开始：** 现有多股页面的最小增量、专用有界请求/响应模型、局部草稿提升、必要的结果/证据组件、增量样式和 `web/tests` 合成测试。先落实 §5 与计划 UI01–UI11 的异常/边界用例；保留 single/pair/导入/导出回归。本批准不要求等待浏览器环境恢复才写这些代码。

**本片不修改：** Python 数学、HTTP/Store、冻结政策或后端测试；后端联合全回归和实现 reviewer 的最终结论仍由对应工作负责。UI 可按冻结合同并行实现，发布可用入口前须确认实际 API 的独立实现阻断已关闭；不能用本设计批准替代那个结论。

实施后仍需独立审代码、跑最终前端测试/TS/build 和受影响回归。真实浏览器交互、字体与窄屏、200% 缩放、截图、Windows 和用户复核任务继续分列未验。浏览器安全拒绝保持原边界，不重试绕过；离线模型/SSR 通过不升级为端到端完成。

本次复核只更新本 review；未改产品、后端或测试文件，未提交。没有新增必要设计阻断。

## 8. 独立实现审查与最终决定

时间：2026-10-11 06:02–06:21 UTC。此阶段 reviewer 只新增 `web/tests/filter-adversarial.test.mjs` 并更新本 review，产品修改均交作者完成；未改 Python、后端测试或依赖。后端资源采样期间仅读代码、写测试和执行轻量语法检查，收到 06:17 UTC 采样结束通知后才运行验证。

### 8.1 本轮发现及关闭结果

| 项目 | 问题与作者修订 | 复核结果 |
|---|---|---|
| U1 报告内的事实与引用矛盾 | 初始校验可接受 date gate 与已返回 coverage_known 不一致、启用 V 缺值但原子仍 true/complete、另一字段的数值失败引用、logical/selection 枚举相互矛盾及 V 文本表示不等于实际估计。作者增加已返回字段之间的绑定、可用性、局部原因索引与合法枚举配对检查。 | 独立负例全部拒绝；合法 OR+partial 和未启用 V 失败继续接受。只在矛盾时拒绝整报告，没有重算指标、Fraction 比较、Kleene 组真值或生成替代结论。关闭。 |
| U2 基线与说明有遗漏 | 初始筛选视图没有并列原三项有效/缺失/无效/短历史计数，新增身份限制会落入“未识别状态”。作者在原有 details 内补回小表和窄中文标签，同时保留来源合同版本；局部控件字号/触控目标补齐计划约定。 | 最终源码与 SSR 断言覆盖原始服务端计数、中文限制和来源说明。CSS 只作用本片；真实像素与触屏效果未验。关闭代码层问题。 |
| U3 本地 D/N 错误定位 | 浏览器数值框可容纳 `2e1`，本地严格文本预检拒绝后原来只聚焦摘要。作者增加本地 UniverseInputError、具体输入 ID 与 aria 关联，服务端同码仍落摘要；取消后的焦点目标也保留。 | 实际请求准备函数与目标映射测试通过；不新增后端错误路径协议。真实 focus/键盘行为继续未验。关闭代码层问题。 |

以上问题先由静态核读提出，再由作者修订；没有把未执行的旧版本反例写成“实际失败的测试”。最终通过结果针对下述冻结源码。

### 8.2 独立测试和实际跨端接线

reviewer 实际执行：

```text
node --test web/tests/filter-adversarial.test.mjs
15 passed, 0 failed, 0 skipped
```

独立用 BigInt 有理数等式验证百分比输入与比例字符串的精确关系，覆盖正负边界、16 位百分比小数、18 位 V、小数尾零及负零；没有用生产转换函数生成预期值。477 字节 Python golden 用独立 SHA-256 复核，并覆盖全部组/组内反序与原编辑组映射。其余用例覆盖 U1 的损坏响应、成员/来源/共享合同作用域、缺失和 null 不被补齐、异步准备失败、取消/卸载、旧响应与重复提交锁、实际请求准备副本及破损正文流。

另运行 **15 类实际 Python `filter_report` → TypeScript `assertFilterReply` 合成桥接，全部通过**，防止只有手写前端 fixture 自洽：

- 有效零值、变化价格、Fraction 在零阈值两侧、缺截止与存在截止的短历史。
- 可供查看的负价、缺 OHLC、重复日期、无法定位日期，以及仅有可读 source_date token 的坏标签。
- 隔离来源、局部身份冲突、共享合同中 applicability 的 null/unverified 差异。
- 已入选/已排除但含 V 数值失败的 partial，以及超过八个坏日期槽的原因二元组与 omitted_count。

桥接使用真实最终后端函数输出，TypeScript 以自身请求构建器生成 expected 再校验；规则 ID 均匹配冻结 golden。来源与价格全部合成，临时产物在仓库外；没有 HTTP、浏览器或私人行情。本次桥接是协议兼容证据，不是独立数值研究或真实来源验收。

作者最终日志经本 reviewer 读取核对：[界面资格记录](../qualification/research-filter-ui.md)所列全 Node **128 passed、0 failed、0 skipped**，`tsc -b` 和 Vite 52 modules 构建成功。独立 15 项已包含在 128 项中，不重复相加。完整命令应从 web 目录执行，§5 已修正；仓库根目录的旧命令会使 Vite SSR 模块解析失败。初次空视图测试的过宽正则也已收窄到成员名次/空 tbody，最终未改服务器结果或 golden 掩盖错误。

构建保留 JS 636.49 kB、gzip 193.96 kB 的单 chunk 超 500 kB 提示；没有提高告警线。没有执行浏览器加载性能试验，也不能由此判断真实加载耗时。后端 RSS 未通过是另一项明确保留的资源资格，详见[032 资格记录](../qualification/stock-filters.md)。

### 8.3 最终源码与边界

最终核读关键源码 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `web/src/filter-model.ts` | `c7b00895b4bc7b82294a84df4cb13509fbf3b5f89162d0aaf88794173af5479d` |
| `web/src/universe-request.ts` | `2b8c417e91034f11a810a3d9975b87c198ff1ce4ec00c062d2bcc12cea8000fc` |
| `web/src/UniverseResearch.tsx` | `ea7fbb23bfc83e1b589393ee094c2228c24275c1aafd4465940ff50368e55879` |
| `web/src/UniverseFilter.tsx` | `49ac729ae2b1645050b6254a3ad256bce80e9235ba670b86f27218ac31f2389c` |
| `web/tests/filter-adversarial.test.mjs` | `563ac303798a995d446192bab6160fef977ac6897e6f00c97eee69ffb881c6ed` |

已确认：只有 universe 分支增量接线；原结果组件移出后保持旧路径，pair 路径未扩展。App 仅持有多股草稿；提交时复制请求，修改数学输入即失效，展示筛选和展开不重新查询。短 ID 均在正确报告/成员作用域解析；结果从服务端取值，未新增阈值算法、通用规则平台、缓存、外部字体或第三方测试依赖。

**实现复审结论：本片代码与可运行的合成/静态层通过，没有剩余代码验收阻断。** 允许保留当前最小接线并进入最终集成记录。该结论不覆盖未运行的真实 React 点击绑定、键盘/取消焦点、Back/Forward/bfcache、Web Crypto 浏览器环境、可访问树、字体/对比度、320/375px、200% 缩放、触屏与截图。既有 Chromium 安全拒绝未被绕过。

Windows、真实用户复核任务省时、样本外预测/交易效果也继续单列未验；不把当前结果称为“界面端到端完成”或“全面性能通过”。本 review 和独立测试未提交/推送。
