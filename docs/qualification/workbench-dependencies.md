# 工作台依赖与现有接口：窄范围核查

日期：2026-10-04。范围：只读本机版本／安装元数据、官方 PyPI 元数据及发行说明、当前 `Store.query/export`。未安装或升级包，未构建前端、启动服务、打开产品数据库、请求行情或修改合同／代码。

**建议复用已安装的 FastAPI 0.142.2 + Uvicorn 0.54.0，以及现有前端锁定依赖。元数据约束与模块导入已检查；HTTP、浏览器及本机生命周期兼容仍待验。** Python 3.14／Windows 分类属于发布者声明，不能计作运行实测。

## 1. 本机与冻结前端基线

本机只读命令返回 Node **v24.15.0**、npm **11.12.1**；来自 `C:\Program Files\nodejs\`。Python 为 `.venv` 中 **3.14.0，MSC v.1944，64 位 AMD64**。

前端 **8 个直接依赖（3 runtime + 5 dev）**均存在于 `web/node_modules`，安装包的版本字段与 `package.json`／`package-lock.json` 一致。此前协作消息中的“9 个”为计数口误，以此表为准。

| 包 | 声明＝lock＝已安装 | 已安装元数据中的 Node 要求 |
|---|---|---|
| lightweight-charts | 5.2.1 | 未声明 engines |
| react | 19.3.0 | >=0.10.0 |
| react-dom | 19.3.0 | 未声明 engines |
| @types/react | 19.3.0 | 未声明 engines |
| @types/react-dom | 19.3.0 | 未声明 engines |
| @vitejs/plugin-react | 6.1.1 | ^20.19.0 或 >=22.12.0 |
| typescript | 7.0.2 | >=16.20.0 |
| vite | 8.3.2 | ^20.19.0 或 >=22.12.0 |

当前 Node 满足上述显式要求。检查只覆盖直接依赖清单与导入，没有逐文件验证 `node_modules` 完整性或审核整个 npm 传递依赖树。

| 冻结文件 | 本轮读取 SHA-256 |
|---|---|
| web/package.json | `7c3bd2e32c94ff9c60a9b90e4a55f4d98b0c6034286f3f159db69034be91afcf` |
| web/package-lock.json | `27ee6e164e4fe7371190131d5fd5b099b5f4bf6f5776d86c862ef4013cac0a09` |

## 2. Python 候选版本与一级来源

| 候选 | 官方元数据／发行说明 | 本轮可确认与边界 |
|---|---|---|
| FastAPI **0.142.2** | [精确版本 PyPI JSON](https://pypi.org/pypi/fastapi/0.142.2/json)、[官方发行说明](https://fastapi.tiangolo.com/release-notes/) | 本轮 PyPI 当前版本与已安装版本相同；要求 Python >=3.10，列 Python 3.14／OS Independent，提供未撤回的 `py3-none-any` wheel。发行说明 0.118.3 明示加入 3.14 支持；0.142.2 日期为 2026-09-30。不据分类推定 HTTP 全链通过 |
| Uvicorn **0.54.0** | [精确版本 PyPI JSON](https://pypi.org/pypi/uvicorn/0.54.0/json)、[官方发行说明](https://uvicorn.dev/release-notes/) | 本轮 PyPI 当前版本与已安装版本相同；要求 Python >=3.10，列 Python 3.14／OS Independent，提供未撤回的 `py3-none-any` wheel。0.38.0 明示 3.14 支持；0.54.0 发行说明日期 2026-09-24，PyPI wheel 上传为 09-25 UTC |
| Starlette **1.7.0** | [精确版本 PyPI JSON](https://pypi.org/pypi/starlette/1.7.0/json) | 已安装；Python >=3.10，声明 3.14，基础要求 `anyio>=4,<5`；当前 Python 不触发 `<3.13` 的 typing-extensions 条件 |
| Pydantic **2.13.5**／core **2.46.5** | [Pydantic 元数据](https://pypi.org/pypi/pydantic/2.13.5/json)、[core 元数据](https://pypi.org/pypi/pydantic-core/2.46.5/json) | 已安装；Pydantic 严格要求 core==2.46.5。core 官方有未撤回的 **cp314-cp314-win_amd64** wheel，且声明 Windows／3.14；本机使用普通 CPython ABI，不混用 cp314t |

本轮只读取发布元数据，没有下载或验证 wheel 文件本体。可用于后续核对的官方 wheel SHA-256：

| 文件 | PyPI 元数据声明的 SHA-256 |
|---|---|
| fastapi-0.142.2-py3-none-any.whl | `bd5f4d81f1e93a88bcd77caf4dfe3c2dbffc3805407a0007e9a114c18b3a670b` |
| uvicorn-0.54.0-py3-none-any.whl | `505bdb0f318731d45f1f712071fc781a8981f6847a31c902c9f5e652d4f67faf` |
| pydantic_core-2.46.5-cp314-cp314-win_amd64.whl | `fa10ef4112775900e7a0661068635eb67b2ab824fbde764de6e0e21982a93db0` |

FastAPI 0.142.2 的基础要求为 `starlette>=0.46.0`、`pydantic>=2.9.0`、`typing-extensions>=4.8.0`、`typing-inspection>=0.4.2`、`annotated-doc>=0.0.2`、`opentelemetry-api>=1.44.0`。Uvicorn 在 Python 3.14 的基础要求为 `click>=7.0`、`h11>=0.8`。选择基础包，不因示例安装 `standard`、云 CLI、multipart、uvloop 或 WebSocket 扩展。

## 3. 已安装基础依赖闭包

仅从 FastAPI／Uvicorn 沿当前环境生效的基础 `Requires-Dist` 遍历，`extra=''`，未扫描全生态。**14 个包均已安装，全部基础版本条件及 Requires-Python 满足，发现冲突数 0。** 该结果只评价当前元数据约束，未校验安装文件来源完整性。

| 包 | 精确已安装版本 | 当前生效的基础依赖 |
|---|---|---|
| fastapi | 0.142.2 | 上节六项 |
| uvicorn | 0.54.0 | click>=7.0；h11>=0.8 |
| starlette | 1.7.0 | anyio>=4,<5 |
| pydantic | 2.13.5 | annotated-types>=0.6；core==2.46.5；typing-extensions>=4.14.1；typing-inspection>=0.4.2 |
| pydantic-core | 2.46.5 | typing-extensions>=4.14.1 |
| typing-extensions | 4.16.0 | 无 |
| typing-inspection | 0.4.4 | typing-extensions>=4.15 |
| annotated-doc | 0.0.5 | 无 |
| annotated-types | 0.8.0 | 无 |
| opentelemetry-api | 1.45.0 | typing-extensions>=4.5 |
| anyio | 4.15.1 | idna>=2.8；当前 Python<3.15，typing-extensions>=4.16 |
| idna | 3.20 | 无 |
| click | 8.5.0 | 无 |
| h11 | 0.16.0 | 无 |

这些 HTTP 包尚未声明为项目的运行依赖；存在于 `.venv` 不等于新安装可复现。主方定案后应声明直接版本并冻结所采用的闭包，不需要为本轮核查再次安装或升级它们。

## 4. 已跑与最小待验

已实际运行：`node --version`、`npm --version`；安装元数据和 marker 条件检查；Python `-B` 导入 `fastapi/uvicorn/pydantic_core` 成功；Node ESM 导入 React 与 Lightweight Charts 成功，返回 React 19.3.0／LWC 5.2.1，`createChartEx` 为函数，Candlestick／Histogram 导出存在。未创建 DOM 或画布。

后续仅需在合同获准实现时补：

1. 锁定依赖下的 TypeScript／Vite 构建及真实浏览器图层生命周期；模块导入不能替代它们。
2. Windows 本地单 worker 的启动、绑定、lifespan 关闭与 Store 锁释放；明确 `asyncio/h11`，不依赖自动选中的可选实现。[Uvicorn 设置](https://uvicorn.dev/settings/)
3. HTTP 精确字符串／NULL、坏原件阻断、有界上传预检、导出和请求竞态；验收沿工作台合同，不增加框架比较。
4. 确认启动与使用无非预期外联。FastAPI 0.142.0 新增 OpenTelemetry 支持，0.142.2 修正自动配置失败时启动行为；基础 `opentelemetry-api` 存在本身不能证明启用了网络导出。[官方变更记录](https://fastapi.tiangolo.com/release-notes/)

本轮没有执行服务、构建、浏览器或上述 HTTP 试验，没有改依赖清单。

## 5. 当前 Store 与工作台草案的差异

只读核对 `src/anatrading/store.py` 的 query／JSON／Parquet 路径及 `models.py`。以下交由主方处理 rebuttal 后定案；本报告未修改合同。

| 定位 | 当前事实 | 最小建议 |
|---|---|---|
| `store.py:355`、`:400–401` | query 仅接收 snapshot、cutoff、ordinal_start/end、mode；没有 fields 参数；查询身份中的 fields 固定为六个 VALUE_FIELDS | 第一版合同收窄为固定六字段，不为 UI 列隐藏增加数据库投影能力 |
| `store.py:391–406` | 已返回精确字符串 values、原 tokens、checks、质量与精确 totals；没有 up/down/equal 方向字段 | Python 应用展示层对有效 O/C 作精确 Decimal 比较，缺值为 unknown；不回写存储，不用浏览器浮点判方向 |
| `store.py:404` | `unlocated_rows` 是所选源序号范围内的无标签数；`batch_unlocated_rows` 是全批数 | 草案“全批信息”使用后者；两者明确命名，避免窗口／全批混淆 |
| `store.py:380–384` | 先全批 `fetchall`，再按 cutoff／ordinal 筛选；目前没有 20,000 行查询硬上限 | 草案预算不能描述为现成功能。后续决定前检／查询限制；不得在前端静默丢行冒充限额 |
| `store.py:408–436` | JSON／Parquet 都重新调用同一 query，继承 query_id、精确字段和原件哈希验证；Parquet 分 rows／unlocated，附查询元数据 | 复用现有路径，HTTP 仅交付其结果；不从图形序列重建导出 |

当前日线 query 可接受 D 前一自然日作为含边界 cutoff，因此日／分钟条件配对的 `source_date < D` 不需要推测前一交易日或新增永久身份合并。它仍只表达源标签筛选，不建立历史可得性。
