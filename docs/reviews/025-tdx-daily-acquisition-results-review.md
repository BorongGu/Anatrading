# 025：日线自动获取／工作台发布真实结果反方

2026-10-08。按 [v0.3 合同](../contracts/TDX_DAILY_ACQUISITION_IMPLEMENTATION.md)及 [024 实施反方](024-tdx-daily-acquisition-implementation-review.md)，独立只读复核实际保存文件。**未发 TQ／工作台请求、未打开数据库、未修改产品或原件。** 以下全量复核通过临时内存脚本直接读原件与保存的 HTTP 查询结果，未复用产品 decoder 或根方 `audit_import.py` 执行逻辑。

## 结论

**本次单证券 U1/U2 真实结果通过，无新增 P1/P2。** 自动获取古越龙山日线、固定 `data/local` 工作台单写者发布、同内容重导复用与精确源值保存有实证。批准范围限这两次运行、当前客户端指纹／会话及已保存内容；定时无人值守、全市场、分钟、完整交易日覆盖、经济单位、手动导出语义及交易效果尚未验收。

## 身份、请求及发布

私有证据运行目录：

- 第一：`data/local/acquisition/ad38b26212eb4e7ba6f58a57dc9e2c78`。
- 第二：`data/local/acquisition/41545e9d1a8a407483212050203d56ee`。
- 全量查询及资源：`artifacts/qualification/tdx-daily-acquisition/20261008-u1u2`。

两份 refresh 请求分别 id `2906174050`、`1096048285`，均只含 `refresh_kline`、`stock_list=[600059.SH]`、`period=1d`。对应原始响应 id 一致、字符串 ErrorId `0`；请求／响应 SHA 与各 receipt 一致。两次 HTTP status 均200。未从这些成功码单独推断数据完整或最新。

两次原身份及各3个前后 observations 全部相同：`D:\tdx_64\TdxW.exe`、PID25140、启动 `2026-10-08T03:19:49.7815869Z`。本反方另读当前 exe/SDK 文件重核指纹，仍为合同固定 SHA。反方未重新探测监听、未声称当前进程运行状态由旧 observation 证明。

root 均为解析后的 `C:\Users\<user>\Anatrading\data\local`（`<user>` 为原用户名的脱敏占位；root SHA 仍绑定原运行路径），独立计算 root SHA 与 receipt 一致；工作台 session SHA 在两次运行中一致。server helper 源码实际创建该 root 的 workbench，CLI acquire 不开 Store，发布走既有 import；本次保留的 catalog/attempts/query 和产品 root raw CAS 构成固定根发布证据。未以替代数据根导入冒充成功。

| 项目 | 第一轮 | 第二轮 |
|---|---|---|
| 采集结果 | `new_content`，先前缓存 `absent` | `unchanged_target_observed` |
| 发布 | committed、reconciled=false、reused=false | committed、reconciled=false、reused=true |
| attempt | `4243f58b251743e6b97d6ea35d42e5a7` | `fba58206e07b41c6b823045307ffa87c` |
| catalog | 1个快照 | 仍1个快照 |

首次 `absent` 来自实际采集记录及执行分支；反方未观察下载前的活文件状态。两次回执均与保存账本的 committed 尝试关联。第二轮副本、before 和当前客户端缓存均与第一副本逐字节相同；重导没有制造新内容／新快照。两轮目标单行 query 均有2026-09-30真实记录且与完整窗口一致。

## 独立全记录重核

**独立重核全部7,068条、42,408个源数值及全 token/定位信息。** 直接读取226,176字节 `.day`，读取56个128行分片（末片28行）的保存 query，核序号连续且无重叠／遗漏。Volume 从字节24–27取 UInt32；Amount 将字节20–23的 binary32 符号、指数、尾数自行转为精确 `Fraction`，再与响应十进制值的精确有理数比较；没有经 float 或产品解码器。

- 全部 OHLC raw UInt32/100、整数 Volume、位型 Amount 精确值吻合；这是源表示保存证明，价格缩放仍 assumed、量额经济单位仍 unknown。
- 全部日期合法、严格递增，source_label、label、byte locator、OHLC原token、Volume原token、Amount/reserved hex及日期token吻合；规范 `volume_shares`/`amount_cny` 全为 null。
- 每个保存窗口 manifest、batch/snapshot、query_id及源行分母一致；独立按规范JSON计算 batch／snapshot／query identity，无缺失或未定位行。
- 三目标窗口与全量序号7066–7068完全相同：9/28 Volume `122897667`、Amount `1451543168`；9/29 `113040680`／`1233597440`；9/30 `89971081`／`1093331584`。这些为收到的源数值，不授予股／人民币元单位。

原件、两轮 after、第二 before、当前 cache 和 `data/local/raw` CAS SHA 均为 `f9271218e4ae49729d4b38976552432da7bf529aa677a2c89358fa5df6887f30`。

独立计算 batch 为 `704b33498426390b168b2a3a29e4bc77db8098886190ae65b7ef5bd7f77b5844`；snapshot 为 `c3f950f6002fa14ea4569e2e7075722a3c4df897628e6d63e6b4e981cbffd39c`。两轮保存目录的快照身份与原 manifest 一致；无覆盖第一原件的证据。

**核的是保存的真实 API 查询结果，未独立重新读取 DuckDB。** 这比只读根方 full-audit 汇总更强；当前数据库持久性／新进程查询仍由另行实际检查负责。本次未复算全部质量诊断计数，未验证手动导出语义或交易所行情真值。

补充复核 `audit-after-reuse/`：第二次导入后的56个窗口及三日文件与首轮**全部逐字节一致**，故此前独立核过的全部42,408值在重导后保持。前后 full-audit 的 committed 尝试由1增到2，原第一尝试记录保持，快照相同；本反方独立核该文件集合，未仅引用 finalize 汇总。

## 资源及准备失败

直接读三个完整资源序列及新增重导后 audit 序列，核 PID、真实 Python314 executable、精确整数 FILETIME、样本时间递增、终态 complete/exit0；含准备失败的全部5份资源与 final-audit 摘要逐项吻合。以下为全部原生内存计数的最大值（不是HTTP性能结果）：

| 阶段 | 秒 | 样本数 | 最大内存计数 B |
|---|---:|---:|---:|
| first-real | 7.9224447 | 72 | 577716224 |
| second-real | 6.8051029 | 62 | 577617920 |
| audit-full | 8.6048574 | 79 | 26886144 |
| audit-after-reuse | 8.8283814 | 81 | 26583040 |

四成功阶段均低于120秒／2GiB。guard 观测当前实际 Python 进程，100ms采样并含系统峰值；属于观测守卫，未约束通达信内部下载资源，也不构成硬隔离或500msHTTP闸门证明。

初始 helper root 少一级的准备运行 receipt 为 `failed/workbench_identity_mismatch`、identity空、observations空，目录只有 receipt，没有刷新请求文件；资源 exit2。结合实际 CLI 顺序，此次在 config 身份核对处停止，未发送 TQ。旧 helper 正常关闭 marker 已核，修正后工作台使用真实产品 root；最终正常关闭 marker `server-closed-2` 已核。反方没有把关闭 marker 当数据库完整性检查。

本次模块 SHA `3a9206aa7f40e468f0590d998b74cc38c8a256dfba3c6a20c237b35acfef3e2b` 与024一致；保留首轮脚本 `audit_import-first-executed.py` SHA `5cc1f878f3f60ce8cd48becb2132298e464e512abeb074e141d97dd3e4251cab`；后来增加输出目录的 `audit_import.py` SHA `8f8bd6daeece954d47ede53865a26a177ceed625249c8aea1e788deb5fdd6c97`；guard SHA `5350dc54c1cd097676324897870f49e2dde6790be1dca55f86281adf058e04ad`。只批准本合同闭环，不扩大请求预算或来源资格。

## 新进程持久性补证

根方在正常关闭工作台后，以新进程既有 CLI 在实际 `data/local` 查询同 snapshot，保存 `persisted-query.json` 和第6阶段 `cli-persisted-query-resources.json`。**新进程查询由根方执行；本反方只独立核保存字节及资源，没有重新打开数据库。** 所保存3行全对象与此前独立核过的三日窗口完全相同，批次分母7,068、原件hash、快照身份、cutoff2026-09-30／序号7066–7068吻合；`persisted_audit.py` 的对应断言已阅读，本反方另以独立临时脚本核过。当前实际根无 `.wal`，这是文件状态观察，不代替完整数据库完整性检查。

第6阶段PID23264、8个样本、精确FILETIME整数，complete/exit0；耗时0.7529039秒，全部原生计数最大631,205,888B，低于120秒／2GiB。此峰值高于前5阶段577,716,224B，应另列，不能继续将旧峰值当全部6阶段总峰值。补证支持关闭后重新读取这3行的持久性；不外推为新进程全库重审或HTTP性能验收。
