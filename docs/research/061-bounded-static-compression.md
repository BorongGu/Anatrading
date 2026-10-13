# 061：有界静态构建表示

2026-10-13：先冻结下述合同，经独立设计 GO 后实施；最终代码复核及独立 ASGI/构建验收通过。Linux 最终全量 Python 3568 通过、49 跳过、1 项既有警告；Node 898 通过，TypeScript/Vite 构建通过。提交/发布状态另记。依据已独立复核的仓库外 v3 字节快照实验；以下保留编码前合同及后续修正记录。

## 范围与决策

仅现有 Vite build 生成的 assets/ 下哈希命名 JS/CSS；构建生成确定性 gzip（同 Node/zlib 版本内）和根目录 .static-encodings.json。清单 schema_version=1，assets 为条目数组；每项 identity_path、gzip_path、identity_sha256、gzip_sha256、identity_bytes、gzip_bytes、media_type、cap。cap 固定 2097152，任一目标原件或压缩件超限即构建失败。构建逐一解压校验，并按路径排序清单；不改变源数据、React、API、HTML、导出或请求框架。

清单缺失：兼容旧 dist，普通 StaticFiles identity 行为，不宣称压缩成功。清单存在但不可读、过大、JSON/schema/路径/后缀/hash/长度错误：创建应用时明确 ValueError，拒绝部分加载。清单最大 1MiB，最多 1024 资产。未列入清单的普通文件继续原 StaticFiles。所有 .gz、.static-encodings.json、.encoded 路径固定 404，包括旧 dist。清单与压缩件只作为服务器内部构建输入。

目标 identity_path 为 assets/ 下 Vite 哈希命名 .js/.css，gzip_path 严格为 .encoded/ 加 identity_path 再加 .gz；拒绝绝对路径、空段、点段、反斜线、重复项和未知字段。媒体类型只与扩展名一一对应。固定可信构建目录，不支持热部署；运行时拒绝目标任一父级/文件符号链接以及目录外路径，保留 StaticFiles containment。没有文件系统权限扩大。

## HTTP 和读取

只 GET/HEAD；其他方法 405。合并重复 Accept-Encoding 字段，上限 4096 字节；空/缺失为 identity。q 严格 0..1、最多三位小数；相同重复可接受，冲突或格式错 400，超限 431。gzip 与 identity 中选最高可用质量；隐式 identity=1（*;q=0 除外），并列选 gzip，与获准 v3 一致；均不接受返回 406。

使用现有线程池模式执行所有每请求目标文件读取/哈希；每个文件最多读取 cap+1，一次捕获不可变 bytes。原件不可读/超限为受控 503，缺失 404。仅原件和 sidecar 捕获 bytes 的 SHA 和长度都匹配可信清单时可发 gzip；失效时 identity 可接受则发送原件快照并重新计算 tag，否则 406。禁止 hash 后 FileResponse 重新打开。清单绑定来自构建时解压校验，不在请求内任意解压。

每个表示独立 strong SHA256 ETag，先协商再处理 If-None-Match（含重复字段、weak/list/*）；304 保留 ETag/Vary/Content-Encoding。HEAD 空 body，长度/类型/tag/编码与对应 GET 一致。目标忽略 Range/If-Range，完整 200，Accept-Ranges:none；去掉 Last-Modified、忽略 IMS，禁用 pathsend。普通公开非目标文件保持原 StaticFiles 语义；内部预留名称及指向它们的别名始终拒绝，旧 dist 也适用。

## 证据与代价

v3 实验修复 v2 读取与发送间内容变化造成的 tag/body 错配；stock GZipMiddleware 原 36 行中 14 失败继续 NO-BUILD，CrossResearch lazy 13.93% 字节实验保留但原生失败/重试未验收而 NO-BUILD。此前 Python 编码器 922414→269819 字节只为观察值；产品 Node 编码器须重新实测，不混用 gzip 输出。

代价：每请求读取/哈希、有限内存快照、Range 变全量、放弃 pathsend/日期验证器；不承诺页面或端到端提速。没有公开部署、依赖新增、权限变更、行情/Store/模型数据读取。

## 验收

实际 create_app 路由 ASGI 验证目标表示、协商、条件请求、HEAD、Range、安全头；API/HTML/导出不受影响。覆盖坏/缺清单、缺失/损坏/过期/同长修改压缩件、原件改变/超限/不可读、路径和符号链接、响应构造后覆写/删除及两次读取之间变化。所有成功表示核对真实 body/length/SHA/gzip 解压；HEAD 逐头比对。构建克隆重现、确定性清单/字节及超限拒绝。运行现有后端、前端资格和最终 build。Linux 实测；Windows 原生、真实浏览器及端到端性能未跑，不能冒充通过。无需重试已知 socket EPERM。

独立设计复核：GO（2026-10-13）。编码前补充：清单拒绝 symlink/非普通文件/重复 JSON 键和 bool 伪整数；资产与 sidecar 读取前拒绝非普通文件（包括 FIFO，避免阻塞）。保留路径按原始及规范化段检查，防止隐藏文件别名进入旧静态分支。目标 JS/CSS 加 X-Content-Type-Options:nosniff；API 头不变。现有本机边界只给 API 加 no-store，不宣称存在原本没有的静态安全头。可信固定目录假设保留，不声称对恶意并发替换提供一般文件系统竞争防护。

## 集成复核与阶段证据

产品使用现有 Node 构建脚本：同版本重复构建生成相同 gzip 和清单；不新增依赖。当前 Node 24.19.0 / zlib 1.3.2.1-motley-3246f1b 的两项资产合计 identity 922414、gzip 272133 字节，减少 650281 字节（约 70.50%）。HTML 473 字节不变。这是编码器特定的真实文件大小，不是浏览器性能结果。

独立产品审查发现公开符号链接别名可访问隐藏文件的缺口；已通过 StaticFiles lookup_path 的解析目标检查修复，同时保留指向正常公开文件的原有符号链接行为。构建脚本也拒绝资产目录、内部输出目录/文件及清单的符号链接与非普通文件。预留路径按大小写无关段匹配，防止大小写不敏感平台的别名暴露；这项防护不代表已运行 Windows 原生验收。

最终局部测试：81 个 Python 合同用例通过；4 个 Node 打包用例通过。全 Node 898 项通过，TypeScript 与 Vite build 通过。既有 npm 配置与大于 500 kB 的 JS bundle 警告保留。完整 Python 和独立最终矩阵结果见下文；局部计数不与独立矩阵累计冒充覆盖率。

独立最终 ASGI/构建验收：94 条协议/清单/失效记录、18 条变更注入/读取上限/线程/FIFO 记录、9 条别名/实际 dist 集成记录及 6 条打包记录全部通过；30 条非目标与安全边界观察对比原实现，字节、响应头、消息类型完全一致，含合成成功导出路径。记录数不能视作覆盖一切的独立单元测试数量。首次独立矩阵的两条原件符号链接期望写成 404，实际受控 503；冻结设计未承诺该情况 404，修正测试期望后完整重跑，原记录保留。

完整 Python 首次运行（casefold 最终三条用例加入前）：3565 通过、49 跳过、1 项既有警告。最终源码第一次全量重跑因 /tmp 4.9 GiB tmpfs 被连续完整回归的临时夹具占满，出现 ENOSPC 及 pytest 输出内部错误；日志末计数 2754 通过、14 失败、37 错误、45 跳过，未得到完整最终产品结果。已保留失败记录，仅清理这两轮自己生成的可弃测试夹具，并以明确新临时目录重跑。不得隐藏该基础设施失败或将未完成运行计为通过。

最终恢复运行（同一稳定产品源码，明确临时目录）：Python 3568 通过、49 跳过、0 失败、1 项既有 Starlette/httpx 警告，141.17 秒。49 跳过保持既有缺私有样本/Windows平台限制，未改 skip。最终运行时 SHA256 `b9ce899a079cb35a7d77f94092aca1775d0def3b41f317ca9473c704cf82e03a`，构建器 `a25ccd1bf583c105f1246fb8b3f2b9522dccbe897bf21a44910ea14802e363e7`。独立最终代码复核接受上述版本；原 ENOSPC 记录不被覆盖。Windows 原生、真实浏览器、socket 服务、端到端性能、实源及预测效果未跑。
