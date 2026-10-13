# 049／050：限定 React＋JSDOM 交互补验

2026-10-13 UTC，基准 `main e78c44996caff2ca1d6c6fa2b69b9220c114a1d6`。本记录补充[049变化差异验收](peer-change-lookup.md)和[050回撤摘要验收](drawdown-episodes.md)，保留原记录及编码前冻结稿的当时范围。

## 结果与实际覆盖

- 最终 `run-05` **11组通过**，仅覆盖 Peer 组件和 `UniverseResearch` 的 peer 模式。负责人复核发现它没有执行050分支，随后另行事前冻结并补验；不从共享 controller 外推050结论。
- 最终 `run-050-02` **10组通过**，覆盖真实 `drawdown_episodes` 分支。两轮均包含工具冒烟与 fixture 准入，不能相加称为21个独立产品功能；最终各组 React／JSDOM／window 错误列表为空，未发现产品缺陷。
- Peer：关闭时零来源访问、零变化行；外层打开仍零行，只展开前60窗得到60行。嵌套精确详情的模拟 toggle 不改变父层状态或行数；同 ID 替换合法数据及双方回调后采用新值、新回调，此项仅为隔离合成 props 用例，不表示真实已认证版本可以原地修改；关闭卸载、重开两窗关闭；通过真实父组件的现有 key 验证报告与候选身份变化时复位。
- 两个模式分别实测取消、改变方式、改变截止、卸载，各含迟到成功与迟到拒绝。真实组件事件中止旧 signal，受控 fetch 故意忽略中止并迟到完成；新请求仍成功，旧结果或错误不能恢复、覆盖新结果，卸载后仍为空，重新挂载可成功。
- 050实际链路为模式选择 → `/api/research/drawdown-episodes` 的准确 `snapshot_ids`／`cutoff`／`lookback` 参数 → `DrawdownEpisodeResults` 成员与分析身份呈现；同样核对 `no-store`／`same-origin`。使用真实组件、hooks、controller，没有手工调用失效逻辑。
- 新旧成功响应同请求有效且分析身份可区分，经过真实 DTO 与 SHA 身份验证。成功迟到组等待新旧两次真实 digest 完成，拒绝组等待新请求一次 digest，再经 `act` 排空，未以固定延迟代替终态证据。050配对按事前冻结方法用既有报告生成器及 history 不足反例生成；未手改 DTO 或身份哈希，仅为合成边界，不认证真实 Store 修订。

## 工具隔离与证据保护

仓库外使用独立 package、lock 与 cache，从官方 npm 固定安装 JSDOM 30.1.2及其锁定依赖，完整清单保留；禁安装脚本、省略可选依赖，未装 canvas。Node 24.19.0、React 19.3.0，Vite／rolldown 无服务内存打包；固定 HTML 使用 `outside-only`，不加载外部资源。标准编码、WebCrypto、MessageChannel、structuredClone 及受控 fetch 适配用于同一模拟 window；MessageChannel 端口均关闭，无 Worker 任务。

两轮保护账本各核对3,887个既存文件（含 node_modules，排除 .git 元数据）SHA-256无改、增、删；验收结束时工作树干净，HEAD与远端 main 均保持基准。无产品依赖、锁文件或代码修改，无浏览器、HTTP服务或 socket。本文及链接属于随后文档补充，不纳入上述“验收时文件不变”声明。

两份独立审查均阅读代码与保存结果，通过限定范围；审查者没有独立重跑。协议、补充及执行入口的完整哈希账本保留在仓库外；以下核心 SHA-256 从最终账本读取并与文件复核：

- peer 原协议：`4a670fcf0b534cb564607e081010747af5b9a9ddf326ebf1a6ff9075cbe63721`
- peer 工具补充：`c6d8082b442f2943baaa64123a06e7a426b919a7384240e76b5ba9e28a9f98f2`
- peer 观测补充：`555e8a9fa30e371c12aff78425172687f94b874e78832b55b091f3cc382218a3`
- peer 最终 harness：`ff00076d999002c7160b1f2c81726d2aa4b24fee64c03ff82f660efb90470827`
- 050协议：`45bff8edc3a562c74fd75f6cb058b6765fbf726dfc526e1c6dab54f810ae5a07`
- 050最终 harness：`6428e6442ffb65303c7c4a3a1b7172eb6bd3d31247c66cfc1d586d26464eb7cc`

## 失败与修正保留

首次 npm 工作目录错误仅生成空 lock／cache，移入本轮隔离目录后正确安装成功。早期执行先后遇到 Vite 返回数组的解包错误、缺 MessageChannel；这些运行不作有效产品验收。相同新旧 fixture 与固定延迟观测有假阳性风险，独审指出后保留原协议及临时结果，补充冻结可区分有效响应和完成条件，最终完整重跑 `run-05`。050首轮列表 `row_count` 误沿用121，改为本例9后完整重跑 `run-050-02`。均未修改产品，失败及临时记录未删除。

## 未验与结论边界

这是限定模拟 DOM 交互证据。产品 details 操作用 `open` 属性加显式冒泡 toggle；仅工具冒烟观察 JSDOM summary 点击，不认证真实浏览器原生时序。当前60窗保持关闭已验，展开未验；`pagehide`／`pageshow`、坏身份的完整 UI 错误流程未验，050也未覆盖全部交互。

真实浏览器时序、视觉／CSS／键盘／焦点、HTTP／Store集成、Windows、性能、真人效率及预测／交易效果均未验，不解除既有浏览器限制。脚本仍在仓库外，未纳入持续回归；本轮没有重跑完整 Node、Python 或生产构建。既有真实来源验收的限定不变。
