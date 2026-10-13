# 060 收盘反转记录：限定验收

2026-10-13。基线 `e0d8d29007269235a1eac7ef3b113951c54b6df7`，当前为本地工作树验收，发布状态另以提交/PR为准。[编码前设计](../research/060-close-reversal-records.md)已通过独立接入审查；最终实现经独立代码复审和合成验收GO。

## 实际能力与边界

现有 SingleResearch 内折叠展示保存的日线规范close字段反转记录。阈值1..9999整数基点，默认600无最优含义；每次同时计算up/down两初始化，完整分页与JSON导出，不择优。精确BigInt阈值比较、相等极值取最早位置、等阈值触发、每观察最多一个事件。日期明细区分极值锚点和首次确认；全部事件携带初始化身份，末段单列未确认。

复用既有截止前完整来源响应，不改变后端/API、Store、数据读取和依赖。图上ordinal范围不裁剪计算。来源坏点/重复/无法定位/未知覆盖/不一致计数使整条结果不可计算；events/count/terminal均null，保留完整原因及坏来源证据。只有来源coverage全有效时，Kalman numerical_failure不阻断独立精确close计算。

20,000点限制保持，两模式宽松事件上限39,998；交替20,000点实际39,997（19,999+19,998）。完整报告UTF-8 JSON最多2MiB，超限受控失败，绝不截事件。两模式列表每页50条，能遍历全部可接受事件。此预算不代表总进程内存上限。

原始close token没有随父报告提供，显式为null/unavailable；规范close_exact不冒充原字节。batch来自请求前Query且与snapshot绑定，父研究响应没有batch字段，未独立认证。来源闭合、交易日历、复权、公司行动、历史当时可得性仍未知；不补closed=true，不声称TradingView OHLC等值、盘内路径、噪声识别或交易收益。

## 实际验收

- 仓库15项新测试通过：固定16模式精确预期及各前缀，词法/微小价格边界，整条失败，模型与源资格分离，取消，20,000点事件数，以及独审缺陷回归。fixtures/oracles均为合成定义例，closed=true只属于定义例，不认证生产来源。
- 最终全前端894通过、0失败/跳过；TypeScript/Vite构建通过，保留既有大于500kB的chunk警告；git diff --check通过。
- 受影响Python79通过：signal_research、research_series、research_api、research_adversarial。完整Python套件本次未重跑。
- 独立纯核298/298通过：原16组oracle、80前缀、160倍率前缀、12个额外逐模式边界及输入/预算检查。独立参考用Fraction按分段最早极值重算，不复制产品结果。
- 独立适配器45/45通过：来源/请求/批次/阈值身份，完整报告hash，空/单点，整条失格，numeric_failure区别，原型键防护，新鲜度，247事件完整报告及超2MiB整份拒绝；UTF-8边界实测。
- 实际React＋jsdom 27/27场景通过：247事件跨50条分页遍历且完整导出、Blob URL回收，默认值及六类词法错误、日期说明、取消/折叠/卸载、来源及参数A→B→A、晚到digest、同引用父修改、旧模式/页/事件/导出handler，以及真实SingleResearch组件的lookback/horizon/batch失效、HTTP请求替换/卸载AbortSignal与晚响应。fetch为mock，不是实际HTTP服务器验收。
- 每个DOM场景在新串行Node进程执行，V8堆160MiB。P2修复最终复验最大观测RSS154,845,184字节（147.7MiB）；首轮为150,257,664字节（143.3MiB），均低于256MiB审查界限；没有重试原近上限OOM，不认证长会话内存或瞬时硬上限。

最终三份实现源码SHA256：

- `web/src/close-reversal.ts`: `1c71e9d24b57313e314dbb7d9efc9eae792d0602938d4ff945e53a596f6dcdfc`
- `web/src/CloseReversalRecords.tsx`: `e339361af55691772060189e1f42aba65bb3fe959b621c8bf7b9efe5c0766068`
- `web/src/SingleResearch.tsx`: `ef3f4c2ef8b7d15f03a5f853bb6fc805d17219a2978f45c709ebd3082969e1b1`

独立最终DOM在P2修复后重建并重跑27场景，独立纯核298与适配器45同样重跑；最终全前端与build在以上源码版本运行。外部独立执行器/日志未随仓库发布，公开源码、合成fixtures及持久测试可审阅；这些hash不代替完整外部复现包。

## 历史失败与修正

首次红测试因实现模块尚不存在失败，未冒充断言已执行。初始模型验收合成旧Query缺batch字段，给新测试补明确合成batch后通过，未放宽生产身份检查。两次全前端最初从仓库根启动使Vite找不到/src，保留失败后从web正确cwd重跑。系统python无pytest，切换已有repo虚拟环境后通过，未安装依赖。

独审复现两个产品阻断：source_rows比series多却仍通过完整资格；reason/qualification为__proto__时绕过原因记录，constructor等继承键则破坏计数类型。分别改为整条计数失格和Map/own-property计数，并加入实际回归。中文映射同样避免原型名。旧模式/页日期handler、同引用父变更、来源替换瞬时展示及React提交前旧导出资格分别由当前模式/页/source token、有界源签名和同步publication generation守卫处理；render复用已接受上下文，不重扫完整父报告。

独立DOM初版执行器误分派保存的模式切换动作，错误地把未切换的导出判为过期；保留该执行器失败并修正分派，数值预期、门槛和产品未据此放宽。初版核心默认参数断言移至UI，因为冻结core API要求显式bps。独立数值预期没有改动。

## 未跑与继续限制

真实浏览器/截图/布局（已知Chromium socket EPERM保持，未重试）、Windows原生、真实软件文件或市场来源兼容、实际HTTP/Store端到端、真人效率、预测/交易增量均未验收。058数量秩科学STOP及其他已有限制不变。此GO只支持有界来源close描述功能，不是整产品/真实来源/金融效果验收。

## 远端审查P2补充（2026-10-13）

首轮本地独审与独立验收GO对应旧close-reversal.ts哈希7c0db1f6及893项前端测试。PR #54自动审查在提交31243bb上发现source_rows小于series.length时被提前当资源错误抛出，较大不一致值则保留unavailable报告，违反计数不一致统一保留证据的约定。接受该P2，未合并旧head。新增回归实际先失败再通过；仅去掉source_rows>=series.length资源判断，保留20,000上界，所有不一致值都进入source_row_count_mismatch。纯扫描算法、UI及SingleResearch没有改变。

修复后的持久测试15通过、全前端894通过、build通过；独立补丁审查另验六个直接边界：0/25/27/20,000来源条数对26行序列均整条失格并保留26行证据，-1及20,001拒绝。上述新源码哈希替换旧hash。受影响Python79项来自同批未改后端的既有运行，未为本TS一行修复重跑完整Python。独立execution-final-04重新执行纯核298/298、适配器45/45（新增较小来源条数）、重建bundle后全部27/27 DOM，实际新hash核验通过；原首轮GO及较低RSS属于前一版本，不冒充本次执行。
