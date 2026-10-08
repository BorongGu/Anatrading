# 单根源K线结构：精确计算与真实全分母验收

2026-10-08。依据[015研究](../research/015-candle-geometry.md)、[合同v0.2](../contracts/CANDLE_GEOMETRY_IMPLEMENTATION.md)、[开工决定](../contracts/CANDLE_GEOMETRY_DECISION.md)与[034合同反方](../reviews/034-candle-geometry-contract-review.md)。异常测试先写，缺模块导致 collection 失败的 red 证据由独立测试 agent 取得后开始实现。没有新增行情请求、运行 SDK、清除分钟未知或修改存储/schema/源格式。

## 已实现的用户路径

查询现有快照返回同一源 query 和逐根 geometry。工作台固定记录详情增加源高低价差、实体、上下影线、收盘位置、近似百分显示及展开的权威有理分数；十字线 compact 详情保持原样。无效 OHLC 全部派生值为 null，原记录保留。零区间比例未定义；量额异常不妨碍独立合法 OHLC 描述。源单位、复权、时点和身份限定继续展示，不产生交易信号或预测资格。

CLI（服务关闭后使用，沿用数据根锁）：

```powershell
.venv\Scripts\python.exe -m anatrading.cli --root data/local candle-geometry <snapshot_id> --ordinal-start 1 --ordinal-end 128
```

HTTP GET `/api/query/{snapshot_id}` 新增 geometry；POST `/api/geometry-export/{snapshot_id}` 用当前 query_id/geometry_id 和相同 selection 返回 `{query,geometry}`。原 JSON/Parquet 导出仍只导出源 query。结构下载同时核 SHA、两身份头、JSON 正文及双 scope 映射，通过后交付原 Blob。界面沿用请求代次门禁，当前失败清空当前图/详情，迟到结果不发布；该组件交互语义本轮仅代码复核，真实浏览器门槛仍待完成。

## 真实全分母证据

复用[U1/U2](tdx-daily-acquisition.md)已经取得的古越龙山日线原件；本轮既有唯一 owner 启动真实 localhost HTTP 服务，审计结束通过 uvicorn lifespan 正常关闭。原件 SHA `f9271218e4ae49729d4b38976552432da7bf529aa677a2c89358fa5df6887f30`；快照 `c3f950f6002fa14ea4569e2e7075722a3c4df897628e6d63e6b4e981cbffd39c`。

私有独立脚本从原 `.day` 的四个 UInt32 直接计算整数分差和 Fraction；未调用产品 geometry/numeric helper。百分显示采用距离最近的两个整数候选、偶数破平的方法，独立于产品 divmod 分支。全部源 OHLC、token、日期、locator、ordinal、派生固定字段、几何恒等式、比例和显示舍入逐根核验。

| 核验项 | 实际结果 |
|---|---|
| 全部实际记录 | 7,068 根，API/完整结构导出/CLI 各全分母通过；无删除/无法定位记录 |
| 本根 C/O 方向 | up 3,562；down 3,316；equal 190；零区间 0。只描述本根源开收关系 |
| 重复查询 | 完整 API reply 逐项相同；首128根不同Q的结果与全量前缀相同 |
| CLI | 完整输出15,495,121字节（本次保存编码），与API的 `{query,geometry}` 完全相等；独立逐根复核通过 |
| 旧源 query | 7066–7068、cutoff=2026-09-30，与U1/U2保存的 persisted-query 完全一致 |
| 旧源 JSON | 本次源导出原字节等于上述旧query的既有canonical序列化；结构导出前后源JSON逐字节相同。执行前 exports 中文件数0，不声称核验既有导出文件全分母 |
| 结构身份 | Q `f00e4b0cc212f6c4389b4012c71f6547f035954d6b77c6fd086ad3ce3e570cb2`；G `60f2ff573a5ad522ecd286dfba4a73dc9aec909903883b84ab0dbe16f26cce10`，独立 SHA 绑定方法/Q通过 |
| 结构原字节 SHA | `e99bd27da50b1fecb2630682831308da660fb0646896ed11c01716cd2c14fe3d`，headers/正文与当前Q/G完全一致 |
| 原件/客户端状态 | 原件哈希不变；原分钟current/receipt两文件字节哈希不变；未追加采集 |

私有证据仅在 git 忽略的 `artifacts/qualification/candle-geometry/20261008-g1/`：独立 audit_import.py、完整API/CLI/导出、全分母报告、逐100ms原生进程资源与 server-closed。三个守卫阶段正常exit0；HTTP全审计7.067秒、原生内存计数峰值801,611,776字节，CLI1.761秒/695,566,336字节，独立CLI复核1.027秒/728,453,120字节，均低于120秒/2GiB。守卫是观测性控制，不能把阶段时长作为HTTP500ms或浏览器性能结论。

## 自动检查与未通过项

完整 Python 回归 **474项通过**，114.23秒；仅既有 Starlette/httpx 弃用提示。新增数学/API/CLI测试58项包括极限38位价差、外部Decimal prec=1/Emax=1/Emin=-1及舍入陷阱、half_even半点及两侧、异常优先级、零价/零区间、来源版本隔离、双scope、20k预算、原件损坏、授权边界、源JSON/Parquet保持。

前端全部33项通过；构建通过。strict validator和派生导出坏正文身份/映射/版本/JSON、SHA与固定详情的SSR检查覆盖实现逻辑；Generation单元测试不证明App真实交互竞态。

**浏览器门槛未通过**：本轮 `cua.getState()` 返回 apps/browsers 均为空；尝试创建 iab tab 返回 `Browser is not available: iab`。没有通过其他技术绕用native UI；构建、SSR及HTTP不能替代实际点击、截止切换、失败清除或下载交互证据。

实现/证据独立复审见[035](../reviews/035-candle-geometry-implementation-review.md)。本功能授予有限源结构计算与API/CLI真实原件一致性，UI实际验收、分钟有效样本、全市场持续更新、单位/复权/PIT、量能可比性、样本外净收益和竞品超越均未完成。完整工具目标保持active。
