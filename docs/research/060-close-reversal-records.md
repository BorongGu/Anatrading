# 060 收盘反转记录：编码前接入设计

2026-10-13，基线 e0d8d29007269235a1eac7ef3b113951c54b6df7。此文件先于代码冻结，待独立接入审查。定义依据：仓库外 priority-review-v2-addendum.md、fixtures-v2.json 与 close-reversal-review-20261013/design-review.md、exact-oracles.json。前者实际阅读 TradingView 官方 Zigzag Calculation/Constructing/Projected pivots/Limitations/Inputs；本接入未新增文献阅读。标准描述查询，不声称 TradingView OHLC 等值、盘内路径、真实噪声、最优参数、预测或利润。

## 查询与精确规则

沿 SingleResearch 已有 retrospective 来源版本合同分析截止前完整日线 close 字段。保留 calendar_and_bar_closure_unverified、historical_availability_unverified、adjustment_basis_unverified；不新增模式，不伪造 closed=true，不提供已完成柱开关。058 STOP及其他限制不变。默认600基点，仅默认值；输入必须数字整数或规范十进制整数字符串1..9999，拒绝bool/float/空白/指数/小数/前导零。UI以文本输入保留词法检查。

同一次计算固定展示 up/down 两初始化，不选优。首点极值，up状态仅严格更高更新锚点，下降达到 ext*bps/10000 则确认down；down对称。相等极值保留最早位置；等阈值触发；每来源观察最多1事件。DECIMAL(38,18)正规范字符串转18位定标BigInt，交叉相乘判定，gcd约分的正magnitude及signed_relative_change分开。首事件标初始化警示，所有事件身份带initial_mode；后续不保证初始化无影响。未确认末段单列，不画投影。确认时点才可知，锚点/确认日期并列；延迟为index差，不能用ordinal差或推断交易日数。

## 首片来源适配与身份

纯TS核 + 薄适配器 + SingleResearch内折叠小块；不改后端、HTTP、Store、读取流程或依赖。使用已由assertResearchReply核验的完整single响应；不从图上ordinal范围裁切，不另取来源。现有响应只有规范close与日期/ordinal，没有原字节token。端点保留close_exact，close_token=null，token_status=unavailable_in_parent_report；UI明确“规范收盘原值；原始token未随研究报告提供”。不拼接图表的可能不完整rows。batch_id在请求前从当前已验证Query捕获，同snapshot绑定；响应没有batch_id，不能声称响应独立认证该字段；记录owner query、research query、snapshot、batch、parent analysis、cutoff。不会宣称重新验证完整OHLC或050加强资格。

在响应被接受时一次捕获并深冻结有界证据投影：来源身份、参数、limitations、coverage、qualification及每行date/ordinal/close/reason/status；不复制巨大完整父报告，不在每次render重新扫描。适配器校验输入kind/method/mode/expected参数、来源与Query/cutoff对应、唯一升序日期、唯一安全整数ordinal、coverage整数与条数等式、date_groups=series.length、source_rows<=20000、完整前缀初始化语义、必需limitations与日线资格。来源原件仍由原请求边界校验。

coverage中invalid/duplicate/unlocated/unreadable/batch_unlocated非零、coverage_known=false、source_rejected或任意来源reason使整个新结果 unavailable：两模式events/count/terminal全null，原因逐类计数，原coverage保留；不删坏点、不重置、不跨越。仅reason=numerical_failure是例外：若coverage确认全部source groups有效且规范正close/ordinal均有效，则允许独立精确扫描，不能把Kalman失败当源价失败。暖机/reset不影响准入。空序列无数据；单点可计算0事件。非法结构/预算/身份为受控错误，不发布半份结果。

## 结果与生命周期

方法close-reversal-records-v1、规则exact-close-bps-earliest-tie-both-initial-v1。完整结果含上述来源身份、threshold_bps、initial_modes=[up,down]、范围初始化与tie规则、来源语义、完整证据端点、两模式完整事件与末状态、局限。report_id为完整结果（不含自身id）规范JSON的SHA256；事件键绑定report_id、initial_mode、anchor/confirmation index，对应日期/ordinal由不可变完整证据序列解析。所有事件字段来自核的实际端点，不接受自洽但无来源的外部event。事件端点保留索引与日期/ordinal精确字符串、规范close及原token未知状态。完整结果UTF8 JSON最多2MiB（含report_id），两模式最多39998事件；超界受控失败，绝不截断。预算不声称总进程内存小于2MiB。

计算由显式按钮触发，参数变化立即清除结果和旧导出资格；每256点让出/检查AbortSignal。异步前捕获冻结证据，返回前检查当前来源ownership token、请求generation、参数、两固定初始化。同ID换内容、A→B→A、query/cutoff/ordinal范围变化、重算、关闭/卸载均永久使旧任务不可发布。render只重用已经接受的有界context；事件/导出处理器重新核对当前token/源context/参数。无跨任务缓存。

UI复用既有research-subsection、table-scroll和字体，放在既有SingleResearch区，无第二工作区。两模式并列总数，明确模式切换，完整事件每页50条，显示总数/页码/上一页下一页，能遍历全部事件。日期按钮展开该事件来源明细，仅展示，绝不改变查询截止或暗示锚点已知。末状态单列。只允许当前完整结果导出JSON，生成/回收临时Blob URL，关闭/替换后无旧导出。

## 事前验收

固定16组独立精确oracle，不改阈值或选择模式；全部80前缀及160倍率变换；边界/平台/缺口/单点/空值/小价格/最大数值/词法拒绝。额外覆盖bps=1/9999、坏价/重复/无法定位/全局来源反证/暖机与numeric失败、身份串换、未来追加与固定截止的区别。20000点交替序列应为39997事件（19999+19998），检查≤39998宽松上限并验证完整2MiB受控拒绝，不冒充可展示。jsdom实际DOM验收参数变化/取消/旧结果/关闭/卸载/A-B-A/事件日期明细/分页超100/当前完整导出。运行全web测试、build和受影响Python回归；不重试已知Chromium EPERM。真实市场样本、Windows原生、真实浏览器/截图、真人效率、预测有效性仍未验收。仅合成fixtures，外部执行日志放verification/close-reversal-20261013；未获父GO前不分支/commit/push。

独立接入审查：2026-10-13 review_reversal_integration 给出GO，已纠正20000点交替序列合计39997而非宽松上限39998；实现仍待独立验收。

实现细化（独审后）：所有源行date/ordinal/close/reason/status均进入一次捕获的有界来源签名，事件与异步边界检查新鲜度，render不重做签名。完整结果端点保留规范close；模型status/reason仍留在原研究报告，不属于反转结果的源价资格。不可计算结果另附全部rejected_observations保留坏行与其状态。reason计数用Map后转own-properties，避免原型名绕过。完整来源coverage要求source_rows=series.length；不一致整条不可计算。UI发布绑定来源token，事件动作绑定当前模式与页。

## 实施与最终限定验收（2026-10-13）

本地实现完成，独立实现复审及精确hash合成验收GO。最终前端893、受影响Python79、构建通过；独立纯核298、适配器44、实际React＋jsdom27通过。完整分页覆盖247事件；20,000点为39,997事件并验证完整2MiB超限拒绝。代码身份、历史首轮失败、两项独审产品缺陷及修正、真实来源/浏览器/Windows等未跑边界见[限定验收](../qualification/060-close-reversal-records.md)。当前未据此声称发布或预测有效；058及其他STOP保持。
