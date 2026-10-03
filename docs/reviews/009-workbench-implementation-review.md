# 单快照工作台实现：独立最终复审

2026-10-04，反方 `validation_papers`。本轮只审当前冻结实现、运行针对性现有测试，并新增本文件；未修改产品／测试代码、安装依赖、启动新行情请求或重复全量回归。依据 [图形合同](../contracts/WORKBENCH_CONTRACT.md)、[HTTP 约定](../contracts/WORKBENCH_HTTP.md) 与 [008 开工决策](008-workbench-review.md)。

**判决：条件接受本轮限定代码实现及第 6 节状态标记修复。原两项 UI 意见在代码与组件渲染层关闭；本次核读未发现新增 P0 代码阻断。单快照切片整体验收仍未通过：性能门槛未达标，浏览器文件选择受权限阻塞，完整联动矩阵尚未补齐。已独立核实真实分钟同 Q 的浏览器 JSON／Parquet 落盘子项；新增浏览器观察的证明范围见第 6 节。** 本判决不重开 G0，不放行双快照、自动取数、新格式或研究资格升级。

## 1. 原 UI 意见逐项结案

| 原意见及可复现机制 | 当前修订与本轮证据 | 判定 |
|---|---|---|
| UI-01：`source_semantics` 实际为 `{scope, fields}`，前端曾直接读 `volume_unit/amount_unit`，使 BaoStock 文档单位始终回退 unknown；复权硬编码 assumed，使 `.day` 未知复权获得错误状态 | `web/src/types.ts:12–16` 明确嵌套结构；`RecordDetails.tsx:24–33` 从 `fields` 取单位值、status、applicability，独立显示规范单位。`App.tsx:252–260` 从 `fields.adjustment` 取复权值／状态，缺失保留 unknown。`.day` 报价除 100 仍读 price_scaling 的 assumed。React 静态渲染覆盖 Bao 文档 shares/CNY known＋样本 unverified＋规范 unknown、`.day` unknown、字段缺失 unknown | **代码／组件层关闭**。浏览器版式与就地可读性仍归 WB09 |
| UI-02：tooltip／固定详情只接 row，未显示单位资格 | `SourceChart.tsx:77`（补修前为 74）传入 `reply.query.manifest.contract`；`App.tsx:243` 固定详情传 `q.manifest.contract`；`RecordDetails.tsx:4–10` 两者共用 UnitEvidence。证据来自当前 Q，未从其他快照目录补填。静态渲染同时覆盖 compact／完整详情和精确字符串 `9007199254740993` | **代码／组件层关闭**。浏览器新增证明范围见第 6 节，不据此宣告全部联动完成 |

来源定义 known 只表达文档含义；样本适用性 unverified、规范单位 unknown 仍独立保留。原件或代码名称未被提升为永久证券身份，`.day` 未获得已证实复权口径。

## 2. 本轮冻结改动的审查

| 范围与定位 | 核对结果和边界 |
|---|---|
| `workbench.py:338–341` direct `JSONResponse` | 交付 `_query_view` 的已有 JSON 安全结构，绕过 FastAPI 通用递归编码；OHLC／量额／汇总继续沿 Store 字符串，null 保留。未引入前端浮点真值、删字段或改 Q。针对性测试逐值核 `9007199254740993`、0、空定位＋unlocated，以及 JSON／Parquet 的同 Q 身份。保存的性能证据另显示优化前后 35,512,513 字节响应 SHA 相同；这项为核读主方证据，未在本轮重新生成大响应 |
| `numeric.py:22–32` exact Decimal fastpath | 只有 `type(value) is Decimal` 直接复用不可变对象；Decimal 子类仍经原构造路径。bool／float 等类型拒绝、非有限值拒绝、DECIMAL(38,18) 范围／精度判断、BIGINT 整数判断、128 位严格求和及调用方 context 隔离均保留。未改 Schema／数值版本。本轮 numeric 全模块 83 项通过；未将性能改动解释为允许舍入 |
| `cli.py:16–28,54–63` serve | 固定 `127.0.0.1`、单 worker、asyncio／h11、关闭 access log；端口 1–65535。先创建应用，由 lifespan 的专用线程拥有 Store，CLI 分支未再套一个主线程 Store；没有额外监听地址／reload 入口。“准备启动”文案未冒称已启动。本轮核源码，未另启动 CLI 服务或测系统信号 |
| `workbench.py:70–119` 所有权／关闭 | open、方法与 close 共用一个单线程 executor；HTTP 等待取消由 shield 隔离。停止 accepting 后，close 排在已接受工作之后。启动等待被取消时，已排队构造后的关闭仍在同线程执行，再 shutdown(wait=True)。本轮独立复跑“构造晚于取消”与“导入尚排在前一工作后时取消 HTTP 等待”两条实测路径；未发现资源归属回退 |
| `workbench.py:122–169,288–336` 本地／上传边界 | Host／Origin 与 token 严格校验，重复头拒绝；API no-store；固定安全错误代码。原始字节流累计 16 MiB，接收／导入单在途；未完成上传不入 Store，已入队导入不凭断连取消。没有通用 multipart 临时落盘路径。直接 JSONResponse 未绕过这些中间件 |
| `workbench.py:255–257` telemetry | tracing、metrics、logs、operation_spans、auto_configure 均显式 False。本轮用原生 ASGI lifespan 的现有反例检查禁止进入遥测配置／发送路径，包含坏输入；没有只用 router lifespan 代替原生包装。但真实浏览器断网与外联观察仍需集成证据 |
| `workbench.py:198–237` Q／范围／导出 | 前检目录条数与显式窗口，后检 rows＋unlocated；导出重新 query、核 expected query_id，再走现有导出并核文件 SHA。坏原件继续阻断；既有导出文件不能获得免校验入口。导航 SQL 只返回同一源序号范围的相邻标签，不返回未来价格／量额；目录存在不代表原件已核验 |
| `App.tsx:41–52,81–102,129–150` React 代次 | Q 编辑先使当前 reply／选中记录／导出失效；单调代次覆盖 A→B→A。查询发布前校验代次和选择，旧失败不覆盖新代次。导出接收响应后、Blob SHA 完成后各查一次代次；失败调用 invalidate，坏原件错误进入同一路径。下载文案仅称“已发起”。本轮静态复核此机制，未声称测过浏览器事件竞争 |
| `model.ts:17–46`、`SourceChart.tsx` | Number 限于图形坐标；后端 Decimal 方向独立。OHLC 浮点重合／非法值走占位，数量可独立绘制；0 与 null 分支分开。记录序号轴保留重复标签，表／tooltip 使用精确字符串。没有抽点、补柱或用画布重建导出。初版标记曾重叠／裁剪，现按第 6 节窄修复；其余缩放与十字线矩阵继续由浏览器证据判断 |

本轮无需额外抽象层或协议变更。`store.py` 只新增目录元数据和标签导航读取；它仍可能全批 fetch 后筛选，20,000 行 HTTP 预算不代表已有 SQL 分页或更大的数据规模资格。

## 3. 本轮实际验证与证据等级

在 Windows、CPython 3.14.0 现有 `.venv` 运行：

```text
.venv\Scripts\python.exe -B -X utf8 -m pytest -q -p no:cacheprovider tests/test_numeric.py tests/test_workbench.py::test_query_exact_values_navigation_and_both_export_scopes tests/test_workbench.py::test_decimal_direction_and_drawability_are_independent_of_float_rounding tests/test_workbench.py::test_cancelled_startup_closes_a_store_created_after_cancellation tests/test_workbench_boundaries.py::test_cancelled_http_wait_keeps_an_import_queued_behind_another_operation tests/test_workbench_boundaries.py::test_native_lifespan_and_rejected_input_do_not_enter_telemetry_paths
88 passed in 1.35s

cd web
node --test tests/evidence.test.mjs
4 passed, 0 failed, 0 skipped; 452.9195ms（最终文案指纹）
```

88 项为 **83 项 numeric＋5 项 HTTP／生命周期测试**。4 项 Node 测试实际用 React `renderToStaticMarkup` 渲染 SnapshotEvidence／RecordDetails，证明组件文本与契约传递；没有 DOM 事件、Canvas 或浏览器下载。先前独立 14 项 boundary 的结果不在本轮重复计数，父方后续全回归也不冒充本轮独立实跑。

主方随后报告全产品回归 **290 passed、0 skipped、39.39 秒**；本审没有重复这轮全回归，保留为主方实跑结果。

收尾时 App.tsx 发生单一下载回执文案改动：由“已下载同一查询的…；文件 SHA”改为“已发起…下载；内容 SHA”。本审在内存还原该句后，SHA 精确回到首次核读 `403f0ade…`，确认没有夹带其他修改；最终文件为 `f40c42ff…`，上列 4 项组件测试已对该最终文件复跑。主方另报告 22 项 Node 测试及 build 重过；本审仅核当前 dist/index.html 指纹，不将主方结果计作独立实跑。

只读检查 Python lock 的 **25 项**：精确版本全部匹配安装元数据，当前平台／Python／无 extras 条件下的生效基础依赖缺漏与版本冲突 **0**。前端 Node **v24.15.0**，**8 个直接依赖**的 package.json 声明＝package-lock 解析＝已安装版本。未重新安装，未验证所有发行文件完整性；`requirements-workbench.lock` 为版本 constraints，按其 `-c ... -e ".[dev]"` 用法约束安装，不宣称它是带发行文件哈希的供应链锁。

## 4. 保留的未通过项

以下属于当前切片验收门槛，不因“未发现新增 P0 代码问题”关闭：

| ID／优先级 | 当前证据与状态 | 最小关闭条件 |
|---|---|---|
| WBI-01／P1：WB10 查询性能 | **未通过。** 同目录 `query-performance-after.json` 的 20,000 行、7 次进程内 ASGI nearest-rank p95＝**1.6605021997820586 秒**，仍高于 **500 ms**；这项保留原 ASGI 口径。后补真实 HTTP 的有效结果：日线 4,995 行 **0.46408719988539815 秒**、1m 15,840 行 **1.3727681001182646 秒**、人工 20,000 行 **1.832988000009209 秒**，均各 7 次串行，见下文证据范围。日线该样本达到查询阈值，分钟与预算上限样本未达到；首次可交互 ≤2 秒仍未证明 | 完成必要定位／窄修复后，以固定语义、全部记录、同 Q／同数值验证及可复查重复次数重新测量；分别记录 API、真实服务传输、浏览器渲染。不得降低验收阈值、删异常／抽点或静默截行获得通过 |
| WBI-02／P1：浏览器文件选择与导入 | **受阻／未完成。** 主方本轮明确报告原生选文件权限阻塞；本审未重试权限操作。HTTP 工具导入与预置目录不能关闭原生选择文件、导入回执与账本核对的浏览器验收 | 在获准的真实浏览器路径完成文件选择、现行格式／声明、导入终态、快照选择；保存浏览器版本、构建指纹、输入哈希、步骤及界面证据 |
| WBI-03／P1：浏览器导出与联动矩阵 | **部分补证，整体未完成。** 已独立核实真实分钟同 Q 两种文件落盘。第 6 节补充主方实图的零／缺量标记、两条取消＋延迟查询路径及坏 raw 导出清屏观察，限定各自证据层级。旧导出返回时切换后的下载抑制、未触发取消的旧查询完成回调、完整 scope／窗口／缩放／离线矩阵等未核实条件继续保留；WB03／05–09 不能整体记 pass | 按合同补齐剩余浏览器子项及结果清单。取消后的网络响应释放不能单独证明旧成功／失败实际执行到 React 完成回调；Generation 的模型测试与该集成场景分别记账。不得用普通下载成功推定过期下载已被实测抑制 |

原生文件选择受阻是本轮工具／权限边界，不能据此断言产品导入必然有 Bug；它确实使该验收项目缺少证据。公开第三方历史样本通过也不证明当前通达信／同花顺软件版本兼容、全部 G1 完成或策略有可交易收益。

上述性能与主方 HTTP 导出报告均位于私有 `artifacts/qualification/workbench/20261003T194344681685Z/`。本轮核读 `http-performance-optimized.json` 与 `http-performance-optimized-20k-rerun.json`：计时为本机 127.0.0.1:8765 的 GET 至完整 response.read，SHA／JSON 解码在计时之外，没有计入浏览器解析、React 或画布；nearest-rank 在 n＝7 时等于最大值。原 20k 组曾受一次日线 UI 查询干扰，**整组废弃性能结论**，采用明确隔离后的重跑；原日线／1m 组按操作者记录保留。未启用 access log，不能反推精确重叠时段。有效 20k 重跑全部保持 35,512,513 字节与同一响应 SHA。

另核读 `http-export-audit.json`：主方真实 HTTP 记录了真实分钟截止（4,508＋0）、人工边界（7＋1）及空定位（0＋1）的双格式结果，共 6 个导出文件的大小／SHA。这补充 API 路径证据。

**浏览器落盘续补：** 主方操作页面的 JSON／Parquet 下载后，CUA 两次下载事件等待超时，但页面报告已发起；本审随后独立只读核验 `C:\Users\顾卜荣\Downloads\anatrading-a923b8bf2e9718db6108922e70fb155b16796b7b6ae10eacd251c05e51805cb1.{json,parquet}`：

| 文件 | 独立核验 |
|---|---|
| JSON | **7,775,904 bytes**；SHA `a7cbd459427b382c3f9f434fd83985a26c12bcac00208ecc14cac7e77e21f547`；query_id 与文件名一致；cutoff=`2020-12-15T14:08`，retrospective，4,508 定位＋0 无法定位 |
| Parquet | **369,026 bytes**；SHA `21f31da69537451627ed54f5a111e0ef8b4915afc3c70c0d85f53a0dd7762190`；schema 的 `anatrading_query` 身份与同一 Q 一致；4,508 行 |

两个实际文件与独立 HTTP audit 的预期 SHA 逐字相同，故该 Q 的普通浏览器落盘子项获得证据。**下载事件回执未收到、文件已经存在且正确是两项分别记录的事实。** 这不能替代旧代次下载抑制、其他 scope 的浏览器导出，亦不能解除原生文件选择权限阻塞。

## 5. 本轮核读 SHA-256

以下指纹限定判决所覆盖的源码与合同。后续修订需说明变更及受影响证据，不能沿用本次指纹声称已复审。

| 文件 | SHA-256 |
|---|---|
| `docs/contracts/WORKBENCH_HTTP.md` | `9018622e831203552c8b21c7b83981f086d3d2706c4e1366bc0f8d753f691613` |
| `docs/contracts/WORKBENCH_CONTRACT.md` | `dae59f562bc572ddff9c799540a99dd0ae79bad236dfddc8553899756468381e` |
| `src/anatrading/workbench.py` | `d5fcc8accb16022ae7eeda9abe8148b53bc58265fe3c3dcfac1db9b177ace636` |
| `src/anatrading/numeric.py` | `a7c66d7c609e771aa8ab43a124aec418bea6261aa7ae6feb50a169627d10b58a` |
| `src/anatrading/cli.py` | `5b3f4b06090661d8ac33aa966a14d445dba1ae12505cf96f52df797914aa896e` |
| `src/anatrading/store.py` | `918e17af71960a2ed2db9ec224b9c2a8c9d89c649797bdbe6e9bda9db9010b5f` |
| `requirements-workbench.lock` | `d1ca1c2fdc2a64cf10b65c772a4a36926de873a1f74369fc3bce9e566a37bbbf` |
| `pyproject.toml` | `3cd8c0eeeb5f6f20b803ebe309ce8955b4abff6ca735349c3ff6dbbeba2a0670` |
| `web/package.json` | `7c3bd2e32c94ff9c60a9b90e4a55f4d98b0c6034286f3f159db69034be91afcf` |
| `web/package-lock.json` | `27ee6e164e4fe7371190131d5fd5b099b5f4bf6f5776d86c862ef4013cac0a09` |
| `web/src/App.tsx` | `f40c42ffdb3bc06bf136ffff608eb75fb62a39e718a36f14315eec93a80d6050` |
| `web/src/RecordDetails.tsx` | `8f9acac0086bdd1ee0bdf4c2ab6c81bf9a97d05c66dfd94c395256a3382a00de` |
| `web/src/SourceChart.tsx` | `31806107ed3b8a3245ce1ca810f46e720f6525bbf632a4af947b2b2aca48ecd0` |
| `web/src/types.ts` | `bf57d8f9da5b929736cb40dee295c8ab94d43a98bc21e718fb6dad2bb5c888ae` |
| `web/src/model.ts` | `f3058fa2333fa020be2ed035a954e6ee80e4ce78fe0b683420926421eafb52f3` |
| `web/src/api.ts` | `9713eccda4fb42e7f9d90d7f68ad44b32c80a19d991c343fdcac4b8ef80d8cf1` |
| `web/src/sequence-axis.ts` | `cfe971d2683a1f9756dfe97da8181c0d65cbe1ada8cfcbf384bbe85f2c29654c` |
| `web/src/main.tsx` | `882c03db92f952867fe164e3632eb7471871933fb34231fd7c3e1a04346b40c7` |
| `web/dist/index.html` | `363937799c923fb78c045a0c5467037a4018083364587e6116581aed7488dd70` |
| `web/tests/evidence.test.mjs` | `e6e3b6bb7fdb6eacece9432b5caa0af503af542b47b49ddf9d982422395ab1f1` |
| `web/tests/model.test.mjs` | `ba1f7af4369b92c633cbe92451bd47959de488f41f1a1f71d9621e76dc11496b` |
| `web/tests/chart-markers.test.mjs` | `f95aa3bab4cfe601b5b5c4ffd6c4a41bcad08ce7d52b5f69f1bd68e2308493ca` |
| `tests/test_numeric.py` | `42de77064f78b0ff57d210dfc6446e3dde435cc47f83515c958e939345aa81c9` |
| `tests/test_workbench.py` | `ef862a4cb936c6ead941edaefd9ebc31ac75d59fd56377b77fc6e9bb8044740b` |
| `tests/test_workbench_boundaries.py` | `314d6986ea18702e53dd6947dfe0bd15ddcbc08e82a0e3b718393fde0215f06b` |
| 私有 `query-performance-after.json`（路径见 WBI-01） | `9a7285c2b16862028183ad7f8995a3760d4dbfbc394443aafedbb69179bc4ef2` |
| 私有 `http-performance-optimized.json` | `427d55d3c651133d9abee0076bae69fe5c3dc173e57e62516cfbfba06f38eef7` |
| 私有 `http-performance-optimized-20k-rerun.json` | `3b0ed4312acafc3e7d2e2d240857bce3ee3727d2374bce7cf0c2ebb11b532eb4` |
| 私有 `http-export-audit.json` | `a07cc5ae45a8b267fcb9c8fcce19d4bbaa7ce0540fa9265fc5141e26266ca385` |

性能记录的响应 SHA-256：`0fef926561603d0603435fff528e33e66373c43686a239df83af9778ff422de6`。该 JSON 载荷与原始行情留在私有 artifacts，本评审仅记录校验值及验收事实。

## 6. 状态标记窄修复与集成证据续审

2026-10-04 续审。保留前轮事实：修复前本文件 SHA 为 `4f7c18f0c62676a2032390e1b1a44a8865f11dc306907f9ee7afb516830639f6`，SourceChart 为 `068014a3…`，dist/index.html 为 `a10a78aa…`。本节覆盖主方在真实图形中发现的零标记与缺量方块重叠、文字贴底裁剪；旧版“纯模型测试通过”未识别这项显示缺陷，不能补写成旧版图形已通过。

**接受本次标记修复，无新增阻断。** `SourceChart.tsx:9–17,47–54` 合并为每条源记录最多一个状态标记，取 `aboveBar` 并放在独立隐藏状态轴：纯零显示 `0`，零且有问题显示 `0 !`，缺量显示 `∅ !`，其余问题显示 `!`；干净非零记录不生成标记。独立插件的零／问题标记不再叠在同一记录上。图例明确“状态行……位置不表示数量”，没有把用于状态定位的常数当成源数量。

`model.ts` 的 SHA 与前轮相同，源数量 0 仍为 histogram 的数值 0，缺失／非法量仍为 whitespace；没有抬高零柱或填补缺量。OHLC 精度占位、记录轴、清理函数及从当前 Q 读取精确 tooltip 的接线保留。

本代理仅运行受影响的现有测试：

```text
cd web
node --test --test-name-pattern="zero|null|generation|quantity|status labels" tests/chart-markers.test.mjs tests/model.test.mjs
5 passed, 0 failed; 425.5947ms
```

这 5 项分别覆盖单记录单 marker／零缺量文案、纯零与非零问题、坏 OHLC 下独立数量、0 与 null、Generation 拒绝旧成功／旧失败与 A→B→A。未创建真实画布。主方报告 **24 项 Node＋build 通过**，并通过 CUA 重拍确认 `0 !`／`∅ !` 可见、tooltip 精确值保持；这里归为主方浏览器观察，本代理未再次操作浏览器或独立查看该截图。

收尾核到 `evidence.test.mjs` 的夹具另外显式加入 `ws: false`；内存移除这一个选项后 SHA 精确回到前轮 `e4165c06…`，测试断言未改。本轮更新其最终指纹，未为此重复前轮 4 项渲染测试。

### 真实响应延迟的可证范围

本代理只读核 `artifacts/qualification/workbench/20261003T194344681685Z/race_server.py`：私有包装器先调用真实应用并捕获原 ASGI 消息，限两份各 8 条人工输入；延迟后依原顺序发送这些消息，未伪造查询成功／错误 JSON，也未把门控加入产品。其 `race/events.jsonl` 有两组三事件：

| 场景 | 独立核到的服务日志 | 主方浏览器观察 |
|---|---|---|
| A1 成功延迟 → B → 同 A 原件缺失失败 → 释放 A1 | 20:28:42 UTC 捕获 A1 HTTP 200，21,227 bytes、Q=`21b4182d…`；20:29:14 记录 disconnect；20:29:23 released，`disconnected=true` | 当前 A 错误保持，无图、固定详情或导出；旧成功未恢复页面 |
| 旧 A 失败延迟 → 恢复原件 → B 成功并固定记录 → 释放旧失败 | 20:30:10 捕获 HTTP 409、`raw_object_missing`、30 bytes；20:30:23 disconnect；20:30:27 released，`disconnected=true` | B 的 Q、固定详情和导出保持；旧失败未清除 B |

**两组都已发生 `http.disconnect`。** 它们验证了浏览器取消＋服务器延迟／释放路径，未证明释放后的旧响应进入浏览器 `fetch` 成功／失败完成回调。单调代次的判别另由上述 Node 用例与源码复核支持；两层证据不能互相替代，也未实测“旧导出响应晚到仍不下载”的完整路径。

主方另报告坏 raw 下点击导出后，错误显示且图、tooltip、固定详情、导出入口清除。本代理未独立复操该页面；随后只读校验 race 的 A／B 两原件与 inputs.json 的预期 SHA 一致，主验收 store 的 6 个 raw 对象均与各自内容地址一致，损坏材料没有遗留为成功原件。文件恢复不代表自动恢复图形，继续需要一次成功查询。

| 私有证据（同一验收目录） | 本轮 SHA-256 |
|---|---|
| `race_server.py` | `7eb3a9c061b7a39f2a588286beaa910bf6defdcb46fafec3b9d2943c2ba900c9` |
| `race/events.jsonl` | `be9739db6a9b38b0696b06e6bc1d45c9df9251acd64a93f326b9aeef0c42ebdc` |
| `race/inputs.json` | `353fc151dcf4af29b62fb964b1b970992f16642726c1273a6e02e5391d804adf` |

WBI-01 性能、WBI-02 原生选文件权限及 WBI-03 其余浏览器条件继续开放；本次补审未降低阈值，也未将局部显示修复升级为整个切片通过。
