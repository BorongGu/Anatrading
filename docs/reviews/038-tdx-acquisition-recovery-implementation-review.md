# 038 · 客户端未知刷新恢复实现反方

2026-10-08，独立反方 `/root/candle_contract_rebuttal`。依据[037定案](037-tdx-acquisition-recovery-contract-review.md)、[实现合同](../contracts/TDX_ACQUISITION_RECOVERY_IMPLEMENTATION.md)、[根方决定](../contracts/TDX_ACQUISITION_RECOVERY_DECISION.md)及[研究016](../research/016-client-session-recovery.md)，只读审查 tdx_recovery/session、acquisition/schedule/cli 必要接入和新测试。仅新增本记录，不更改产品、生产journal、SDK、行情或账户；纯字段负例只调用验证函数，未打开真实数据库或客户端。

## 初审问题与闭环

| ID | 级别 | 初始问题 | 当前状态 |
|---|---|---|---|
| RI-01 | P1 | 无final checkpoint时，原代码生成N后共用O/N允许列表，可接受current=O/receipt=N并在新核证后创建checkpoint，违背初次必须O/O的原字节规则。 | 已关闭：final checkpoint不存在时 receipt_raw必须等original，且old按完整unknown校验；拒绝在原生核证/封存之前。负例由反方独立重跑通过。 |
| RI-02 | P1 | gate初始read/decode/通用journal/path校验位于原try外，畸形路径可漏非typed异常。纯验证负例：合法record仅root尾加lone surrogate `\ud800`，data_root_id UTF-8 encode实际抛UnicodeEncodeError；NUL路径已获typed拒绝。 | 已关闭：公开recovery_gate全过程typed wrapper，ValueError含UnicodeError；不扩大普通journal变更。gate级surrogate负例反方独立重跑通过，拒绝在核证/写入前。 |
| RI-03 | P1 | `_publish`只在整次既有acquisition._write前后核预算；内部write→flush→fsync无阶段门禁，write返回已到期仍开始flush/fsync。合同要求到期不新增持久阶段。`_read`也没有读返回后的remaining。 | 已关闭：恢复私有unbuffered FileIO薄写、write返回值完整检查、write/flush/fsync前后预算和路径检查，读后remaining；deadline/short-write不flush/fsync/replace的两个分支及读后过期负例反方独立重跑通过。普通_save/_write未变。 |

**最终代码复审：三项P1闭合，被审代码无未关闭P0/P1；根方完整回归通过。** 这只关闭当前实现审查，不能授予真实生产恢复、正式任务持续运行或分钟成功资格。

## 已核实现关系

- 三入口均先读合法client-global控制；acquire/recover active非空拒绝，due active保持既有核账路径。无active的gate位于_collect、新run、due marker/control初始化、持久时钟和reserve之前。本次阻断/补齐/刚完成均early return；完成N/N才在下次普通入口继续。
- 原64KiB、checkpoint256KiB上限，严格UTF-8/BOM拒绝/递归重复键与非有限、非整数JSON数值拒绝；old必须无恢复tag/任意调度关联字段、完整身份、root/state/client/data_root_id/run/证据路径规范绑定。临时/final的resolve包含关系在读写replace边界校验，不扫描历史run。
- checkpoint固定键、schema整数1、canonical base64原bytes、old/new SHA；new由old仅四个字段机械生成且沿用精确缩进UTF-8，无new对象任意信任。两次prior/native与新监听稳定观察必须合格才原子创建不可覆盖final。已有效checkpoint允许O/O、N/O、O/N补齐，第三种bytes/丢receipt/tag丢checkpoint拒绝。
- N/N快速核完checkpoint机械bytes后不重查已结束进程；recover幂等，普通入口可继续。新current仅查新run的checkpoint，历史记录保留且不全盘阻断。publication_unknown/committed既有发布核账函数保留，调度owner终态未获得本恢复的关闭权限。
- native模块100ns regex先拆秒/至多7位小数/规范offset，再整数days/seconds×10^7+fraction；不走float/微秒截断。OpenProcess先正非boolDWORD，GetProcessTimes与Wait0绑定同句柄；ERROR87只能触发完整非空Toolhelp枚举，结束18且无旧PID才missing。CreateToolhelp非法句柄、First/Next/超限/旧PID存在/访问拒绝/Close失败均拒绝；所有已取得句柄finally关闭，即使预算耗尽仍释放句柄。
- 恢复将native五键组合/创建tick绑定old，prior missing/reused/ended才通过；同tick alive拒绝。监听仍须原EXE/SDK/AMD64/唯一端口身份，再要求native alive+tick精确等started，两次核心身份稳定。同步syscall无硬取消承诺，无HTTP/SDK/Store/强停或轮询。

## 验收与最终复审区

本反方独立执行：`tests/test_tdx_session.py` **66/66通过，0.25秒**，含仅对当前测试Python自身PID的真实只读creation/alive对账；其余模拟native返回覆盖100ns/offset/DWORD/87完整枚举/CloseHandle及预算。这不证明用户TdxW已结束。

在最终修订源码上独立执行恢复负例选择 `new_receipt_without_checkpoint or surrogate_root or read_crossing_deadline or write_failure`：**5/5通过，2.68秒**，135项未重复运行，1项既有Starlette/httpx弃用提示。零新HTTP/槽/原件变化及原bytes保持由临时fixture核查。此前较早选择命中3项亦通过，最终五项取最新完整闭环结果，不合并成8个不同用例。

测试代码另覆盖三入口checkpoint rename、receipt/current write/fsync/replace前后中止、O/O-N/O-O/N/N/N、active/single-sided-control、inactive control字节、completed下次due、历史checkpoint不阻断与来源机械候选。根方最终执行完整Python回归：**680项通过，95.08秒，1项既有Starlette/httpx弃用提示，执行session61031终态exit0**；包含最终140项恢复及66项native测试。之前focused331项/42.05秒是执行方先前阶段，不独立相加。反方本次没有重复完整回归，保留自身66+5 focused与根方全套结果的来源区分。reparse/path包含防护已源码核查；实际symlink/junction故障当前尚未由本反方测试，不授予全面文件系统对抗资格。

最终工作树代码SHA-256（Git换行归一可能改变字节哈希，不等同逻辑变化）：

- tdx_recovery.py：`7f920a2085db3f5a8237a472a9a79339774d6340aeb8520702371b02df3cf473`
- tdx_session.py：`0e1ab5ee55a6638f97a7514d35e67364313c997e395bc49dfcb30495cc78fa15`
- tdx_acquisition.py：`ea297038b63638e9848f42d45280f6815c25ce87c071084846845ed1c0dd12ce`
- tdx_schedule.py：`2117aae0c1f6a8e137af6222b215ea20835fe24cb071a204af029de2dba64386`
- cli.py：`27207c03f7ac7362b898b35dd4ed32191fa59081f8b9a81c5b614c68edaebcfa`

真实原会话仍alive时不得运行成功恢复写入或请求新行情；本切片后续原生资格helper必须另审动作/预算，并把自建进程、真实只读阻断、生产恢复分开登记。任何自建child/合成missing/完成checkpoint都不能证明实际TdxW任务结束。
