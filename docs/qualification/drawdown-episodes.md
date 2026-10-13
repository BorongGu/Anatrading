# 多股已观察回撤摘要：本地验收

2026-10-13 UTC。实现依据[050研究定义](../research/050-observed-drawdown-episodes.md)、[冻结验收协议](../plans/2026-10-13-drawdown-episode-acceptance.md)和[独立审查修正记录](../reviews/2026-10-13-drawdown-summary-implementation.md)。这是一项来源价格描述便利功能，未测省时、用户判断改进或预测优势。

## 本次交付

- 独立只读 `GET /api/research/drawdown-episodes`，完整来源预算先计数后加载，来源早停保留失格行。
- 2–50成员、2–252来源区间、精确截止；只有全部成员自身有效且完整日期数组相同才发布摘要。
- 每股独立给出最深、已观察跨度最长、当前未恢复代表。每条携带自己的原价、窗口位置、源序号、精确跌幅、舍入显示与恢复边界。
- DECIMAL(38,18)正值精确整数和256位交叉积限制；未恢复的完整恢复跨度为null，观察跨度为下界，窗口前峰未知。
- 前端从完整原价端点重新推导全部段数、代表、真并列、分数、显示和跨度，并验证报告身份及资格；旧的取消和晚到响应防护继续复用。
- 复用既有多股成员、窗口、截止选择器，不新增筛选语法、序列图、预测、依赖或部署。

## 精确版本和一手来源

方法版本 `observed-drawdown-episodes-v1`；规则版本 `all-member-grid-last-peak-first-valley-exact-v1`；来源资格版本 `peer-relative-eligibility-v1`。源码中规则与所有输入版本一起进入分析标识。

050冻结稿记录了对 Mahmoud [The Temporal Dimension of Risk](https://arxiv.org/pdf/1501.01573) §3.2–3.3及Remark 3.13、TradingView [Average drawdown duration (close-to-close)](https://www.tradingview.com/support/solutions/43000772102-average-drawdown-duration-close-to-close/) 的定向阅读。这里采用另行明确的离散来源区间定义，未声称等同其连续时间、自然日或equity口径。冻结稿没有记录arXiv具体修订号，不补造版本号。

## 验证方式和结果

每次Python/Node运行使用新建TMPDIR。API只使用本轮新生成捕获字节、新EvidenceStore和进程内ASGI；没有端口监听。API原件损坏/缺失用例仅改变并恢复当次新临时原件。

纯数值参考按严格低于前缀峰的连续游程独立枚举，覆盖全部3–7点三值序列、闭式预期、极值和舍入冲突。前端测试另以逐候选峰枚举为参考，未将产品运行时重算充当独立oracle。

50×253极值成功报告完整UTF-8 JSON为1,487,517字节；同规模失败报告合并端点异常后为366,630字节。另以完整有效窗口及已核未来异常证据产生超过2 MiB的真实报告形状，顶层拒绝 `drawdown_result_limit`。不承诺所有合法最大输入都能成功输出，不缩成员或删失败行。

最终正式命令：

```sh
python -m pytest -q -s \
  tests/test_drawdown_episode_research.py tests/test_drawdown_episode_api.py \
  tests/test_universe_research.py tests/test_peer_neighbor_research.py \
  tests/test_peer_neighbor_api.py tests/test_group_endpoint_research.py \
  tests/test_research_api.py
cd web
node --test tests/*.test.mjs
npm run build
```

最终修订后的结果：所列Python 145 passed，0 failed、0 skipped；全量Node 628 passed，0 failed、0 skipped、0 cancelled；TypeScript/Vite构建通过。独立实现审查通过，无剩余已知阻断。以上Python范围只包含预审过的纯函数和全新合成Store用例，没有运行完整pytest。Node全量包含两个原有新合成桥接；只释放已完成桥接自己的新数据库，保留锁文件、原件和目录，失败时保留新证据。不清理历史Store。

旧数值/来源资格、Store/锁/导入/导出、原有结果组件及未计划修改的产品文件，按编码前SHA-256清单核对不变；有意接入仅限research_api、universe-request、UniverseResearch三个文件。最终产品验收时，三份设计文件也逐一核对未变。

## 失败、警告和未验范围

保存了最初缺模块、API入口404、DTO/SSR入口缺失的测试先行红灯；保存了独审发现的中文比较、异常总计、反证资格和重复日期早停回归的红灯。最大样例曾因测试生成器把日期跨度设为505天、超过既有捕获格式366天上限而失败；修正为253个逐日来源标签，不改变回撤定义或预算。

构建保留npm环境代理配置警告与Vite大chunk警告，未据此调整依赖或宣称性能优化。

未验：历史真实数据、Windows原生、真实浏览器交互与视觉布局、socket HTTP、性能/RSS、完整Python集合、真人效率、样本外预测或交易结果。未下载行情，未接触旧受限DB、凭据或账户权限，未公开部署。本地通过仅接受上述有界描述功能。

下一验收：负责方检查最终diff和独审记录后决定发布流程；真实来源/浏览器/Windows及任何性能或预测扩展仍需各自明确范围和证据。

验收后的文档同步：仅更新当前 `docs/research-status.md` 的050状态指针，并在本记录注明变更。050研究稿和编码前验收协议正文保持不变；设计提交 `19daf9440a5c77c4fe9abf5d8c974a430b08c764` 完整保留当时三份文件的编码前原文。此次不改产品代码或测试，不重跑产品验证，也不表示已发布或合并。

后续补充（2026-10-13）：[六个冻结案例的有限真实捕获兼容验收](drawdown-episodes-real-capture.md)已接受；本记录的合成验证范围与当时未验项目保持原义，新增覆盖及来源限制见补充记录。
