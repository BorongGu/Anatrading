# 024：日线自动采集实现反方

2026-10-08。对照 [v0.3 实现合同](../contracts/TDX_DAILY_ACQUISITION_IMPLEMENTATION.md)，独立只读核 `tdx_acquisition.py`、CLI、workbench 与采集测试。未改产品／测试、未调用通达信、未取真实行情、未打开现有产品数据库。阅读期间根方正在修订，以下按所见具体行为记录；需要在最终文件上闭合后才能放行真实刷新。

## 初审结论

**最终修订通过实施反方，允许合同规定的受控日线实测。** 4项P1及结构／预算P2已关闭，本反方独立重跑最终采集测试64通过。下文保留初审及修订依据；此结论不构成真实来源、发布闭环或全系统验收。

## 必须关闭项

1. **P1，旧发布恢复丢失原工作台会话。** 初版恢复用本次 config token 作 baseline；同 root 工作台重启后，只要旧快照仍在，就可能恢复成 committed。原会话没有持久化，违反合同要求。应保存 token 的 SHA-256 作原会话标识，恢复前后均核一致；不记录 token 原文。需要未知发布后工作台 token 改变且旧内容仍可查的负例。
2. **P1，损坏 identity 可假冒已换客户端会话。** 初版 journal 只验身份键是否存在；错误 pid/start/path/fingerprint 会与当前 identity 不同，被认作旧任务结束并允许新 refresh。旧身份值必须合法，安装指纹须为合同固定值；只能从合法的监听 PID／启动时间等会话证据解除旧刷新未知。journal 损坏应停，不能进入新任务。
3. **P1，畸形失败回执直接终结发布未知。** HTTP200 `{attempt:{status:"failed"}}` 在初版就把状态置 failed，没有合法 attempt id 或账本关联。畸形回执不能证明提交已失败，更不能允许后续再次刷新。只有合法失败尝试与现有 attempts 账本终态核一致后才能终结；其余保留 publication_unknown。可复用现有 attempts GET，不需要新路由。缺字段／错误类型／伪造失败ID应有负例。
4. **P1，绝对 deadline 未覆盖 HTTP header 内部读取。** 独立 localhost fixture 以40ms间隔发送10条 header，设置 `_http(... budget=0.12)`，实际耗时 **0.408秒** 才返回 AcquireError。`getresponse()` 内部多次读 header，每次 socket timeout 重新计时；body `read1` 前调整 remaining 不能约束这部分。deadline 须下沉到每次实际 socket recv（或等效方式），并覆盖 Connection:close、慢 header 与 chunked 内部行读取。仅完成后检查 elapsed 不足以满足合同。
5. **P2，结构校验和初始化失败恢复。** 根方已主动处理 config formats/query rows/journal 的严格类型及 preparing 未获得 identity 就失败的恢复；最终复核应确认畸形结构返回安全错误，不泄漏 traceback；初始化失败状态可终结，不凭空要求存在从未取得的客户端身份。
6. **P2，恢复文件预算。** 初版 current journal 与 after.day 使用无界 `read_bytes()` 后才判断1MiB。须改为最多读取限额加1字节，超限即停，不先全量分配。

## 已核正确边界

- acquire 在 CLI 的 `EvidenceStore` 上下文前分支；采集模块只复用目录锁和确定性身份函数，没有构造 Store 或连接 DuckDB。发布通过既有 import，因此工作台仍为唯一 writer。
- 客户端目录 hash 作用域的私有锁/current journal 跨 root 共用；publication_unknown 恢复校验原 root 和 port，不使用新 symbol/date 覆写旧任务，也没有第二次 import 或另一数据根 fallback。
- refresh 请求之前先持久化 refresh_unknown；导入之前先持久化 publication_unknown。网络断开／原件缺失／目标 query 不可读保留未知，允许复用既有 catalog/attempts/query 做有限核账。
- `.day` 副本经过两次稳定读取，全量复用既有严格表示解码；日期非法、重复／倒序、不可精确表示时不发布。Volume 保持 UInt32 整数；Amount 保持收到的 binary32 精确表示；身份/价格缩放 assumed、标准量额未知。
- catalog 和 attempts 与按源副本算出的 manifest/batch/snapshot 对账，并核目标单行 query 的 token 与精确值，避免把仅目录存在当可读成功。
- 当前代码没有分钟/GUI/交易接口或长期调度路径；两次真实 refresh 的授权只有在第一轮成功可读后才可用，不能绕未知状态继续第二次。

## 放行条件

关闭上述项并复核最终文件，完成相关边界测试后，可放行合同规定的受控单股票日线实测：最多两次 refresh、工作台运行中发布、首轮 committed/query 可读再第二轮，并独立全量原件量额对账。实施评审不授予全市场、分钟、经济单位、手动导出语义或预测效果资格。

## 修订中间复核

模块 SHA-256 `d20e08ecd5001704c2d4e91ac3027760ac27e34e0979fa8b9eaa2f1f7770f71f`。

- P1-1：保存工作台 token 的 SHA，恢复前与末尾均核原会话，关闭。
- P1-2：未知 journal 身份验证合法 PID、aware 启动时刻、安装路径及固定指纹，关闭。
- P1-3：失败回执要求32位hex attempt id，并核 ledger 同 raw/status/format、服务会话，关闭。
- P1-4：Timer 在绝对 deadline shutdown 自己的 socket；本反方重复同一慢 header fixture，budget0.12秒现为 **0.135秒** 返回 AcquireError，fixture线程终止，关闭。
- P2-6：current 与 after.day 恢复有限 read，关闭。
- P2-5 仍有严格类型遗漏：attempt.status 为 list/dict 时 set membership 可 TypeError；matching committed ledger 缺 attempt_id 时最终访问可 KeyError；应先验合法 ID/status/reused 和客户端 identity.path 类型。补齐并测试后再最终放行。

## 最终闭合

本次只读复核及 localhost/synthetic 测试；无真实行情请求。最终文件 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `src/anatrading/tdx_acquisition.py` | `3a9206aa7f40e468f0590d998b74cc38c8a256dfba3c6a20c237b35acfef3e2b` |
| `src/anatrading/cli.py` | `668ef0b0b27194a8ddc56ae272438bc70e0be22d2d8b8acda70bb5f3397235fa` |
| `src/anatrading/workbench.py` | `07609c0f7668fd2cdd8399734f739546d995fba7db374110328b89186f334bae` |
| `tests/test_tdx_acquisition.py` | `1636899134dd5c2b14fa9f04cf2e19e341d3337fd3d09bf2a6c57b41519e2fd7` |

- P2-5 关闭：import status 显式验 str；committed acknowledgement/ledger 的 attempt ID 验32位hex；回执 reused 验 bool；客户端 path 显式验 str。preparing 初始化失败作为 failed 保存，终结记录允许从未取得的空 identity，后续可重新初始化。
- 独立运行 `.venv\Scripts\python.exe -m pytest tests/test_tdx_acquisition.py -q`，最终完整文件得 **64 passed（11.70s），exit 0**，仅既有 Starlette TestClient 弃用告警。测试覆盖跨 root 锁／未知刷新、未知发布前后、原工作台会话改变、损坏旧身份、伪造失败回执、初始化失败恢复、畸形 status／attempt ID／reused 和缺 ID 的 ledger，以及 header/body 慢滴响应。并未以这些合成测试证明通达信服务行为。
- 未发现剩余 P1。保留原合同最多两次真实 refresh：第一轮 committed 且目标query可读后才第二轮；未知时不追加。实测仍需受控工作台根、独立全量 UInt32／binary32 对账和旧快照不可变核验。

本评审未重跑全部 Python 回归、UI构建或真实入库审计；这些分别按合同和实际变更范围由根方执行。分钟、调度及全市场资格仍未开放。
