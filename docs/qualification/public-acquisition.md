# 有界公开行情 CLI：实现与真实验收记录

日期：2026-10-11。依据[已审查计划](../plans/2026-10-11-automatic-market-data.md)、[来源研究](../research/029-automated-ashare-data.md)及[独立实现审查](../reviews/2026-10-11-automatic-market-data-review.md)。

结论：本轮合成、故障注入及全仓回归通过，独立实现审查无遗留阻断。新 CLI 的真实来源链路仍未通过：首次腾讯请求没有取得 HTTP 响应，按验收约束立即停止；新浪两项没有发送。已有离线历史原件的格式／Store 验收不能替代该运输门槛。

## 实现范围

- `acquire-public`：显式沪深代码及 `stock` 声明，腾讯日线每块31自然日/count64，新浪1m/5m最近窗口默认10条、最多240条。声明只取得 assumed 资格，不凭代码推断股票类别。
- `resume-public`：原计划请求、解释、合同和版本逐字绑定；恢复不接受替换参数。每run全部历史最多10个持久发送预留，不自动重试。
- 单Store持锁串行执行。发送前落盘reservation；按固定attempt槽位恢复孤立捕获，核验既有Store提交账本及原件；COMMIT后ACK丢失不重复下载。
- 目录句柄相对操作、no-follow、普通文件/大小/链接数限制、同目录发布与fsync。证据损坏、错块、矛盾账本、预算丢失、多个捕获候选均停止。完整legacy重建封套在网络获取及临时／最终捕获恢复路径无条件拒绝。
- HTTPS使用固定来源地址、默认证书与hostname验证、无代理／认证／cookies／重定向／自动解压的标准库子进程。父进程监督包含DNS和持续慢滴的绝对截止，限制IPC、响应头及实体；取消后确认子进程退出。OS拒绝终止时保持锁并报告无法确认，不能宣称仍满足截止。
- 已存原件及全部源行不裁剪。腾讯CLI摘要提供明确目标日期视图、排除数、源ordinal/locator和原query_id；未知覆盖与未规范数量始终可见。数量标准列保持NULL，量额原token不转float、不补单位。

## 冻结代码回归

2026-10-11 04:43 UTC开始，执行：

```sh
.venv/bin/python -m pytest -q
```

实际结果：**1937 passed，49 skipped，1 warning，68.86秒**。警告为既有FastAPI/Starlette关于httpx测试客户端的弃用提示；49项跳过未计作通过。另通过 `git diff --check` 和本轮Python编译检查。六个本轮产品模块在全仓测试前后及真实尝试前后SHA-256完全一致：

| 模块 | SHA-256 |
|---|---|
| public_acquisition.py | a09e4e2fa1bfe94501a1188e69b4d85431e1899ca69e6f97a5cf8e32d2d0b694 |
| public_transport.py | 9494b6c108e141e6c3a0fbb6999680fdb62b0114a92bc197dfa919d8ec106932 |
| public_http_worker.py | dbe4fc98e51ce4bcc93842e25eac72aa2c4d10f7d62978541e4bf1119fbe3235 |
| public_market.py | b2aa1ea59e7d02ca38b0b077ad25835be7d50a21eebb8631bcd0e8f1cfbcb1e6 |
| formats.py | e044749fcd89a533cb7c82c9adcf8223f7b15785ff501f09166b137f01b6fa6a |
| cli.py | 4db1501cb438bf51f65b05e949cebc7963db5a1270be60013253aa9a6fa266ca |

仓库外证据：`/workspace/shared/anatrading-test-logs/public-acquisition-full-final.log`，同目录 `public-acquisition-final-source-sha256.json` 及 `public-acquisition-final-source-sha256-after.json`。真实数据与日志不提交。

覆盖包含：异常输入先行；精确Decimal／NULL；旧四格式完整黄金摘要；新格式query/JSON/Parquet及价格／数量API；错误码和Retry-After边界；401/403/429伴随坏头仍保存来源限制；限制记录发布后ACK丢失；全部发送预算及篡改；单写入者／symlink；请求／身份／版本交换；真实子进程强退出的Store提交边界；Ctrl+C在捕获后与事务内的不同结果；DNS挂起、TLS挂起、慢头／持续慢体／持续IPC输出、超限、子进程terminate/kill及确认回收。网络故障注入使用本地测试进程和假数据，不向真实来源制造异常负载。

## 一次真实 CLI 尝试

事前固定上限为3次串行发送：601398.SH的腾讯日线2026-09-28至2026-09-30、新浪1m count10、新浪5m count10。任一失败或限制即停止整次验收，不重试、不恢复、不换来源完成剩余项。

2026-10-11 04:45:44 UTC，在独立私有root执行第一项：

```sh
.venv/bin/python -m anatrading.cli --root PRIVATE_ROOT acquire-public \
  --source tencent --symbol 601398.SH --asset-type stock --period 1d \
  --start 2026-09-28 --end 2026-09-30
```

结果：约0.230秒，exit2，`failed_transient / transport_network_error`。run_id为 `664108acf5a7472cae43e2451889bfc9`。发送预算已消费1次，不能因无法确认源端是否收到而退还。新浪1m和5m均未发送。

离线复查确认：1份reservation、1项journal attempt；HTTP status为NULL，收到字节0、body hash为NULL、complete=false；没有捕获文件、Store import attempt或snapshot。没有运输子进程残留。未执行任何网络重试或附加连通性请求。

仓库外记录：`/workspace/shared/anatrading-test-logs/public-cli-live-20261011/report.json`、`offline-check.json`及该目录CLI stdout/stderr；私有root为 `/workspace/shared/anatrading-private/public-cli-live-20261011`。

## 能确定的环境边界

本次执行工具明确请求 `require_escalated`，工具获准并运行。父环境存在HTTP_PROXY、HTTPS_PROXY、ALL_PROXY、NO_PROXY、SSL_CERT_FILE、REQUESTS_CA_BUNDLE、CODEX_NETWORK_PROXY_ACTIVE等变量名称；只核对名称，未输出或记录其值。POSIX运输子进程实际环境白名单为空，因此不会继承这些代理或CA覆盖。当前环境公开的网络allowlist不包含腾讯／新浪；工具允许执行不能证明直连出口可用。

这组证据只支持“没有取得可确认的HTTP响应／实体”。底层OSError已经按合同净化，无法进一步区分DNS、路由、连接拒绝或其它连接错误；短耗时与环境代理存在只是调查线索，不能据此断言具体原因，也没有源限流、封禁或源端故障证据。未降低TLS验证、继承代理或绕过访问限制。

## 尚未完成

- 新产品腾讯／新浪真实HTTPS成功捕获、入库和查询／导出链路：未通过；新浪本次未跑。
- Windows原生自动采集：未跑。当前新采集路径要求no-follow目录描述符及目录fsync，能力不足的平台在联网前明确失败；既有跨平台Store行为未改。
- 强断电、网络盘、跨OS共享互斥、浏览器、长期来源可用性及最终性能：本轮未验证。
- 市场完整覆盖、标准数量单位、历史当时可得、预测／交易增量：本轮不授予资格。legacy历史重建依旧明确缺少运输和头重复性证据。
