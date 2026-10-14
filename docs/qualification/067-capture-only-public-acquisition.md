# 067：capture-only离线验收

2026-10-13。范围与冻结条件见[研究记录](../research/067-capture-only-public-acquisition.md)。仅两个产品文件 `public_acquisition.py` 与 `cli.py` 变化；不改Store、运输、格式、依赖或前端。

## 当前已核验证据

- 新永久测试39通过，包含零DB、五处捕获崩溃恢复、计划／journal篡改、三种来源限制跨run、十次预算、双向互斥、根/锁/来源目录切换、混合empty及捕获后取消。
- 第一次负例运行15失败／3通过；最小实现第一次原采集／CLI／对抗及新测试108通过。独审发现恶意block类型净化缺陷后修复并加入四个回归；失败记录保留。
- 最终受影响9个测试文件626通过／0失败／0跳过，18.30秒；包含原运输阶段、采集、CLI、对抗和strict/legacy格式golden。
- 最终允许Python全仓3732通过／0失败／49跳过／2 deselected，142.96秒。49项缺私有样本及Windows原生证据仍未通过；两项既有localhost慢流测试 `test_http_slow_chunks_do_not_reset_absolute_deadline[header/body]` 按零网络边界未跑。保留既有FastAPI/Starlette的httpx弃用warning，未改依赖。
- 独立49项合成验收全部通过，包括实际子进程 `os._exit(73)` 在reservation发布与临时capture边界、合成DB哨兵访问spy、双向锁、预算和源限制。独立审查另在拒绝socket事件的环境重跑39／39永久新测试，无剩余代码阻断。
- 两组v1独立oracle均通过：默认acquire→resume，以及capture_recorded崩溃→resume导入→再次resume。每组4份plan/journal/reservation/capture JSON逐字一致，完整初次／恢复摘要相同。对照基线为 `d142513382227380618e113c92b9b31166e0936a`，不把数据库文件计入逐字主张。
- 独立qualification环境234通过及112 subtests通过，2.33秒；9个进程安装拒绝socket创建／连接／DNS／bind的审计钩子，无被阻止的网络尝试记录。与产品全仓分开报告。
- `git diff --check` 与两产品／新增测试编译通过。全仓和受影响回归使用父进程及继承环境的socket连接／DNS／bind拒绝钩子，并禁止旧私有行情路径访问；运输子进程使用既有已检查的本地注入脚本。所有Store测试数据为纯合成临时根。

### 最终产品字节

- `public_acquisition.py` SHA-256：`c3d405691201763207d34f4d501730b1deeb63f7af665587d3475d246159f9cc`
- `cli.py` SHA-256：`4210e96b3c80c3f30473d5f7e1cd09f1d60b8367798b232b5f6b0c35889bd05a`

测试、独立验收和代码GO均针对这两个产品hash；最终只补文档实际结果，产品未再改。

### 保留的失败与纠正

独立前置测试旧实现23项预期失败。独立首轮候选曾有一项测试误将真正不完整的规范临时前缀要求为立即拒绝；冻结合同明确保留原字节／原预留并允许下一槽有界重试。经反方核对后修正测试，补充源blocked及预算耗尽不得重试两案；没有为迁就用例修改产品。完整错误JSON、错误hash/绑定和多候选仍拒绝。一次受影响测试命令使用了不存在的文件名，0项运行；纠正为实际9个文件后得到上列626通过。

## 操作边界

`acquire-public --capture-only` 仅保存来源捕获，要求原权威目录和来源限制历史可用，不初始化数据库。`resume-public RUN_ID` 按原计划保持capture-only。非空成功是captured；空结果empty_result；混合完成与失败为partial，退出2。captured不是已导入或已获研究资格，数量仍未标准化、覆盖仍未核实。

完整捕获发布后恢复不重发。真正不完整临时前缀保留且旧预留继续消耗预算，允许下一槽；完整损坏或身份矛盾拒绝。旧二进制拒绝v2前可能打开Store，不支持降级恢复新模式根。

真实网络仍NO-GO，原来源限制与预算历史未恢复。没有读取、hash、复制或打开旧私有数据库／Store／行情原件，没有真实市场请求、登录、网络回退或新root重置历史。全仓允许测试中的Store仅为测试自行创建的纯合成临时数据。前端未改，本轮不重跑或重复声称前端验收。Windows原生、浏览器、真实来源、长期性能与金融效果未跑；058 STOP保持。本记录冻结时尚未提交／推送／创建PR／合并；后续发布状态以对应PR终态为准。
