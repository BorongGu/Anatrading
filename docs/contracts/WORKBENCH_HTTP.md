# 单快照工作台 HTTP 实施约定

2026-10-04。落实已批准的[工作台合同](WORKBENCH_CONTRACT.md)及[008决策](../reviews/008-workbench-review.md)。此文固定前后端接线，不增加格式、Schema、分析指标、双快照或行情请求。实施责任：data_access_research负责workbench.py／Store必要读取及基本测试，microstructure_papers负责web，validation_papers负责独立边界测试与反方，主方负责CLI／依赖／集成验收。

## 服务与通用结构

- 工厂：`create_app(root, *, port=8765, web_directory=None)`，位于`anatrading.workbench`。默认静态目录为仓库`web/dist`，可由本机调用者指定；HTTP请求不接受文件路径。单Uvicorn worker绑定`127.0.0.1`，asyncio/h11，无reload／access log；关闭在线OpenAPI/docs。正式入口为`anatrading --root <私有目录> serve --port 8765`。
- 页面与API同源，只接受`Host: 127.0.0.1:<port>`。有Origin时须严格等于`http://127.0.0.1:<port>`；两个POST额外要求该Origin及本次服务生成的`X-Anatrading-Token`。GET config仅返回这个内存会话token；不建立账户／持久凭证，不在URL放token。不配置跨源放行。
- API响应禁止缓存。失败为安全JSON `{"error":"固定代码"}`，不回显ValidationError输入或异常载荷；用户可读解释由界面按代码映射。导入已形成attempt时返回该真实终态，即使其为rejected/failed；连接断开或无可核实回执由UI标“结果待核对”。
- HTTP监听层不拥有DB连接。一个专用线程拥有Store的open、所有方法和close；调用排队串行。入队的操作不因等待方取消而取消；关闭拒新任务，排空已接受操作，再在所属线程close。最多一个接收／导入在途；忙时明确409，不能排队持有多份16MiB上传。额外请求队列应有简单固定上限，满时503，不构建作业框架。

## 固定路由

| 方法与路径 | 输入 | 输出 |
|---|---|---|
| GET `/api/config` | 无 | `{csrf_token, formats: string[], max_upload_bytes: 16777216, max_query_rows: 20000, mode: "retrospective"}` |
| GET `/api/snapshots` | 无 | `{snapshots: [{snapshot_id, batch_id, row_count, manifest, metadata}]}`。仅目录元数据读取，不全量query各快照；目录存在不等于原件当前已校验 |
| GET `/api/attempts` | 无 | `{attempts: [...]}`，使用既有安全账本字段；与导入同通道，不能承诺导入中实时轮询 |
| POST `/api/import` | raw `application/octet-stream`；URL参数`format_id`、`filename`，可选`instrument/venue/asset_type/volume_unit/amount_unit`；Origin和token头 | `{attempt: 原Store导入结果}`。文件名仅显示用途；不接收任意本地路径、额外解释键、JSON载荷或multipart。流累计≤16MiB，传输未完成不提交导入 |
| GET `/api/query/{snapshot_id}` | 可选`cutoff/ordinal_start/ordinal_end`；可选mode但只能retrospective | `{query: 原Store.query结果, display: [...], navigation: {previous_label, next_label}}`，后两字段仅展示辅助，见下节 |
| POST `/api/export/{snapshot_id}` | 同一选择参数，加`format=json|parquet`、必填`query_id`，Origin和token头；空请求体 | 文件内容；`X-Query-Id`、`X-Content-SHA256`及安全`Content-Disposition`。重新验证原件并执行同Q的既有导出；query_id不符返回409，不交付错误文件。不得返回本地绝对路径 |

JSON与Parquet导出内容保持既有内核格式，不混入display或navigation。服务不得从画布重建数据。查询、导出失败时前端清除当前图、详情、tooltip并禁用导出；更晚返回的旧请求不能恢复它们。

## Q、预算与展示

省略cutoff表示全部源标签；非空值沿用内核严格日期／分钟标签格式，不经JS Date时区转换。字段固定OHLC、volume、amount。查询前用目录row_count判断：批次>20,000条必须显式提供两端源序号，且跨度≤20,000；已有两端时也限制跨度，参数合法性沿用内核。返回后再次检查`rows+unlocated`总数≤20,000。超限拒绝，无静默截行。此界限不承诺Store内部已改为SQL分页。

`display`与`query.rows`顺序和长度一一对应，每项为：`{ordinal, direction, ohlc_drawable, precision_lost}`。direction由Python Decimal比较O/C得到`up/down/equal/unknown`；OHLC缺值、非法、包含关系或非负价格检查失败时不可画普通蜡烛。任意两个不同精确OHLC转Number后重合时`precision_lost=true`，保留位置和明确标记，不画误导正常蜡烛。数量独立可画，0与缺失分开。展示字段不回写质量或存储，也不是新交易指标。

导航只读取同一快照、同一源序号范围的有效源标签，允许返回Q之外的**标签**，不返回其价格、数量、质量或摘要。锚点为显式cutoff；未设cutoff时以该范围最大标签为锚。`previous_label`为严格小于锚点的最大标签，`next_label`为严格大于锚点的最小标签，不存在则null；相同标签整体前后移动。查询仍只返回`<=cutoff`记录，导航不改变query_id或导出身份。

前端每次快照、cutoff或源序号选择改变时立即使当前Q失效，图表、tooltip和导出等新结果；新响应仅在其请求代次仍有效时发布。Number只用于绘图坐标；精确表、鼠标／键盘详情、导出沿query原字符串。可视区域缩放不改变Q。导出按钮明确“N条定位＋M条无法定位”，空定位结果仍可有unlocated。

## 实施与证据

所有HTTP边界先有异常输入／故障用例。服务端可用已安装httpx 0.28.1作开发测试依赖；ASGI测试显式运行lifespan，不能替代真实Uvicorn与浏览器。客户端可用现有Node原生测试工具，不新增前端测试框架。

实现和浏览器验收按WB01—03、05—10当前单快照范围；WB04与配对代次留第二切片。需实际测试文件选择、同Q JSON／Parquet下载、坏原件后清屏、请求竞态、重复／坏标签、零／缺值和显示缩放；构建、API测试及源码阅读均不单独授予图形通过。
