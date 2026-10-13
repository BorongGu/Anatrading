# 有界运输阶段诊断：编码前独立反方审查

2026-10-13 10:23 UTC。基线 HEAD `62448850dca41ced7d494aad205411c9242b4bb8`。

## 决定

**有条件 GO：只做 optional phase + 本次命令内存摘要的最小增量。真实请求仍为 0。** 本文列出的语义与矩阵须在编码前接受，并在实现后复审。此结论不授予腾讯／新浪、DNS、curl、代理、TLS、权限或凭据修改许可，也不代表实现或真实链路通过。

比只加 CLI/debug 钩子更简单且值得做的方案：worker 产生有限 phase，parent 严格接收，acquisition 在本次调用的局部列表收集运输失败；现 CLI 原样 JSON 输出这个摘要。CLI 本身接不到已被 acquisition 捕获的异常，若绕开它新增日志文件、回调、全局状态或 stderr 通道，复杂性及隐私面更大。不要增 sidecar、持久诊断、流式进度、重试框架、独立 socket 连接器或公共诊断平台。

列表上限 10 是安全天花板，并非当前会产生 10 条：现每次运输失败立即停，正常路径每命令最多一条运输失败。保留简单列表以便关联 attempt，**不能为了凑足记录改变 stop-on-first-failure 行为**。若实现需要显著超过三个现有产品模块的改动，应停下再审。

## 实际审查和验证范围

已读 AGENTS、研究报告、public_http_worker/public_transport/public_acquisition、CLI 调用处、public-acquisition/public-market 相关文档与受影响测试；查阅计划／评审的持久化和兼容约定。未打开 DB、Store、原始行情或凭据；未执行网络，也未改仓库。只使用仓库 Python 的 `-B` 做纯内存 `_decode_output`、`_read_response(BytesIO)` 注入。

实际本地观察：
- `error={code:transport_headers_invalid,status:403}` 被 parent 保留为同 code/status。
- 同记录增加现 parent 不认识的 phase（`http` 或 `bogus`）均变为 `transport_protocol_invalid`，不保留 status。
- 原 `{code:transport_network_error}` 可正常读取，异常属性仍仅 code。
- 401/403/429 状态行后接坏头，worker 都返回原 `transport_headers_invalid`，同时保留相应 status、零字节、空实体哈希与 complete=false。
- 初始 git status 干净。未跑 pytest；这些注入不是产品回归通过。

## 必须冻结的设计细节

### 1. phase 是已知执行位置，不是故障责任或网络许可

允许字符串精确集合：`dns/connect/tls/http/read/unknown`；无大小写别名、数字或自由文本。缺失 phase 的有效旧错误按 unknown 展示；不能从 code/status/耗时推造旧 phase。

- 仅在 `socket.create_connection` 的窄调用范围捕获 `socket.gaierror` 才标 dns。发生在其他阶段的同名注入异常不得倒推 DNS。
- create_connection 包含解析与连接；generic OSError、PermissionError、ENETUNREACH、超时均 unknown。`ConnectionRefusedError` 可在该窄范围标 connect；不将整个 OSError 或 errno 家族泛化。
- 进入 `wrap_socket` 后该调用内的失败为 tls；必须包含非 SSL 的 OSError 和 timeout。
- `sendall`、makefile 建立、读取状态及响应头为 http。
- 通过成功响应头校验后，进入实体／分块／trailer／实体结束验证为 read；chunk 行和 trailer 使用相同 reader.line/headers，也必须仍属 read。
- 完整实体的限制标志识别为 read。原 body hash/byte_count/complete 不变。
- 未验证请求、TLS context 初始化失败、未知异常、资源关闭／上下文退出失败可保守 unknown。当前 create_default_context 在 try 外，任意异常最终 worker_failed；不能为了加 phase 改成 tls_invalid。不要让一个已结束 read 的局部 phase 泄漏到随后 close 的异常，声称 read 失败。
- 父取消、截止、spawn、进程非零退出、IPC过量／损坏／读取失败、无法确认退出均 unknown。最终 JSON 尚未完成验证即没有可信阶段；不得采用半截 JSON 或最后观察到的阶段。
- shutdown_unconfirmed 的 finally 覆盖规则不改，不能保留被覆盖异常的阶段冒充最终原因。

实现可在窄边界注解已有异常，避免把错误处理重构成新分类器。worker 通过绝对路径 `-I -S` 独立执行，不能为六个值引入依赖应用包的 import。parent 已可从 worker import 常量；不需要额外共享框架。

### 2. 稳定 code、分类与来源限制有两道不同的边界

**有效 worker IPC：** status 401/403/429 优先于 code 的 transient/cancelled 分类，在 acquisition 保存原 code 和来源阻断记录；即便头损坏、framing/encoding 错误或已读状态后发生 timeout，也保留原 status 并 blocked。不是把 worker 的所有 code 改成 http_blocked。正常 200 限制正文仍 transport_restricted/blocked。

**无效 worker IPC：** unknown phase、非法类型、重复键、额外字段等使整个记录无效，parent 维持 protocol_invalid 且不采信 status。不能从被拒绝的 JSON 捞出 401/403/429 去制造来源限制，也不能为了保住 status 而忽略非法 phase。当前对任意未知键已如此处理；新设计只是增加一个严格认可的可选键。此类错误在 acquisition 仍 failed_terminal、不可 resume，不会自动换源或重发；不新增永久源限制含义。

不要把信任完整 IPC 与有效 IPC 内来源限制优先级混为一谈。测试要同时覆盖这两组。

原分类保持：timeout/network_error/truncated/http_transient 为 transient（若有可信受限 status 则 blocked）；TLS-invalid/协议/普通其他错误为 terminal；cancelled 为 cancelled；shutdown_unconfirmed 停止且不可恢复。phase 绝不决定是否可重试、停止、配额或源许可。特别注意 ssl.SSLError 在不同现有 catch 的 code 不一样：sendall 的 SSLError 目前外层变 tls_invalid，_read_response 中 SSLError 因为属于 OSError 变 network_error。即使新 phase 分别是 http/read，也必须保留原 code 和原分类。

### 3. 隐私和安全接收

- `_TransportFailure.record` 仅新增 phase 这个明确键，并对 phase 类型／枚举校验；不扩张为任意异常属性。
- `_safe_error` 只加这个键的严格枚举验证。沿用 `_pairs` 全层 duplicate-key 拒绝和现有非有限数／类型／大小校验。
- PublicTransportError 的可选 phase 也应有明确约束。直接构造或测试注入的异常不能把任意 phase 字符串穿透到摘要；优选非法本地值保守归一 unknown，IPC 非法值仍整条拒绝。不要让诊断验证异常打断本来应持久化的 blocked 状态。
- 字段缺失可不增加异常 __dict__ 属性，使用 getattr(error,'phase','unknown')；保留现测试对旧异常属性的精确断言。显式 valid unknown 也可接收。
- 摘要条目只从可信本地计划／attempt 取 run_id、attempt_number、block_id，加稳定 code 和净化 phase；不复制 worker 提供的关联身份。
- 不放 URL、host、IP、errno、异常文本／类型名、traceback、HTTP原因短语、请求参数、响应正文、代理／CA环境值。str(error) 始终稳定 code。
- 现摘要本来已有 request，不能宣称“整个摘要不含 URL”。本次承诺是新增诊断字段不扩大敏感内容。

### 4. 摘要及持久化兼容边界

建议固定名称 `transport_diagnostics`，仅存在 `_execute` 局部，传给 `_summary`；固定条目五键 run_id/attempt_number/block_id/code/phase，明确最多10、仅本次命令**失败**、非权威、未持久化。本轮无运输错误则 []。无需加入成功记录，也不把 capture/decode/store 错误冒充运输阶段。

- 从当前已预留的 attempt 收集；不得插入 `_new_attempt`、块 diagnostics、journal events、source-state、capture 或 plan。
- resume 后不能还原旧 phase；旧失败没有本次诊断条目。若 resume 本次又合法发送并失败，记录真实新 attempt number，不从1重新编号。无新请求的 resume 返回 []。
- 在现错误处理与持久化完成后做诊断收集；无额外 checkpoint、文件写入或触发用户回调的路径。列表只构造安全 primitive，不让诊断失败阻断来源限制落盘。
- `_safe_transport` 继续恰好 status/byte_count/body_sha256/complete 四键。所有 schema/version/decoder identity/VERSIONS 不变。恢复旧 journal 的正常状态变化仍可写 journal，“字节不变”应准确指相同固定输入执行与原实现的输出对照，以及无变化的读取不重写；不能承诺合法 resume 从不写 journal。
- 新 parent 接受旧 worker，无 phase -> unknown；**旧 parent 拒绝带 phase 的新 worker**。两个文件同版本交付，无跨版本热更新／混搭承诺；不因兼容需要悄悄忽略 unknown fields。
- 仓内发现的 consumer 是 CLI 原样 JSON 与按键读取的测试，新增顶层字段可兼容这些已知用法；未知外部精确字段消费者可能破坏，必须文档说明 additive 字段，不能笼统宣布全部消费者兼容。旧 summary 缺字段时消费者按 [] 处理。

### 5. 不碰资金式安全账本与提交顺序

不改 10 次全历史 reservation、15 秒 attempt/180 秒 command、发送间隔、请求封套、先 reserve 后 send、严格格式预检、capture 原子发布、Store临界区及恢复。每次失败仍消费已有 reservation。接收阶段不能免扣预算，也不能暗加一次确认 DNS 或探测。

捕获后取消、事务已开始、COMMIT ACK丢失、孤立capture恢复都沿用现最终结果。诊断记录缺失或进程崩溃丢失不构成捕获丢失、重试理由或任何 Store 状态。不要用 phase 产生恢复决策。

## 编码前固定的纯本地矩阵

所有新增 worker 单元测试在调用前替换 socket.create_connection；不得裸调用实际 worker 请求。父进程故障用现有 injected_worker 脚本，不创建连接。acquisition/Store安全回归只在另行获准的测试临时根运行合成数据；本次设计审查未读写这些根。

| 组 | 固定输入/注入 | 必须断言 |
|---|---|---|
| P1 | create_connection gaierror、ConnectionRefusedError、PermissionError、generic OSError、ENETUNREACH、timeout | phase dns/connect/unknown/unknown/unknown/unknown；原 code 原样 |
| P2 | wrap_socket cert error、SSLError、OSError、timeout | phase tls；code 分别维持既有映射 |
| P3 | create_default_context 异常；资源 __exit__/close 异常 | 不扩张旧 code 分类；保守 unknown，不冒称最后 read |
| P4 | sendall 与 makefile 的 OSError/SSLError/timeout；读状态/头 OSError/timeout/EOF | http，原 code；已观察 status/字节/hash/complete 不丢 |
| P5 | 定长正文、chunk长度/分隔、trailer、end验证、读体SSL/timeout/截断/超限 | read；原 code/已收实体计数与哈希；无原文泄露 |
| P6 | 200合法实体、200限制标志、500、302、404；100后200以及坏interim | 成功输出形状不变；限制 read/blocked；其余按既有 code/status，无重定向 |
| R1 | 401/403/429 × 坏头、重复关键头、冲突framing、不支持encoding、读头timeout | 可信status保留，code不改，持久blocked优先；Retry-After仅已有有效场景保留 |
| R2 | 401/403/429 error × phase未知枚举/非字符串/null/重复phase/额外secret字段 | 整条protocol_invalid/unknown，无status，无新增source记录，terminal不自动retry |
| I1 | 旧error无phase；六种合法phase；旧/新错误往返 | 新parent接受；缺失unknown；旧parent拒新字段的限制被准确记录 |
| I2 | 重复顶层error、嵌套code/phase；NaN；bool/list/object；超长phase；成功result混入phase | protocol_invalid，安全输出不出现攻击标记 |
| I3 | 截止、取消、spawn失败、nonzero退出、IPC两种超限、半截JSON、pipe error、shutdown超预算 | 原code，unknown；子进程确认回收／原锁语义不变 |
| A1 | 本次成功、一次失败、部分成功后失败；旧异常无属性；本地恶意phase | []或仅本次失败；五键与有效enum；最多10；先落盘原结果 |
| A2 | 多次独立命令/不同run、resume第2..10 attempt、已blocked或已committed无新请求resume | 不串列表、不回填旧失败；真实attempt number；无新请求则[]；无额外send |
| A3 | 固定UUID/时间/合成body下原实现与新实现对照 | plan/reservation/journal/source/capture字节一致（新增摘要字段除外）；身份/版本不变 |
| A4 | 10次预算、reservation各崩溃点、capture发布各崩溃点、事务/COMMIT ACK恢复、取消边界 | 原额度/停止/恢复/快照数不变；诊断丢失不重发；未收body不产生capture |
| C1 | CLI成功/错误退出；旧summary读取；新summary键访问；原完整strict-v1及旧格式黄金摘要 | 原退出码/status/error_code/target_view/资格不变；未知外部严格consumer不作保证 |

验收顺序：先补异常测试，后最小实现；运行受影响 public_transport/public_acquisition/adversarial/CLI 测试及 strict-v1/legacy 黄金摘要，再全仓测试、diff --check、独立实现审查。报告通过/失败/skipped/未跑，不能把 Windows native、真实来源、浏览器或性能未跑算通过。若全仓现有测试需要不可用资源，原样列出。

## 编码阻断条件

以上条件接受后没有设计级必然阻断；出现以下任一方案则 NO-GO：
1. generic create_connection OSError/timeout 强行标 connect。
2. phase 参与分类、源阻断、预算或恢复。
3. 为阶段拆开 DNS/地址遍历、增加进度协议、继承代理或修改 TLS。
4. 修改 journal-v1 四键、plan/decoder身份或捕获合同。
5. 为受限status绕过IPC完整校验，或为诊断验证跳过可信status的持久来源限制。
6. 新旧worker/parent混搭兼容被误报为已解决。
7. 任何真实请求、DNS、curl 或读取旧私有数据用于本轮验收。

## 编码前接受（2026-10-13）

本任务接受上述有条件 GO、全部冻结要求及 P1–C1 十六组验收。只修改三个既有产品模块，先加入失败测试再实现。测试只使用合成临时数据与替换连接／本地故障进程；无真实网络、DNS、代理或 TLS 配置变更。无旧数据库、旧 Store 或原件访问。开发结束仅本地提交，等待独立实现审查。设计依据同时包括 2026-10-13 公开采集运输诊断审计；其负结果只说明旧稳定错误码不足以定位阶段，不证明任何来源故障或许可变化。
