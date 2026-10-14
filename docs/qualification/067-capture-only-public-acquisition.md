# 067：capture-only离线验收

2026-10-13。范围与冻结条件见[研究记录](../research/067-capture-only-public-acquisition.md)。仅两个产品文件 `public_acquisition.py` 与 `cli.py` 变化；不改Store、运输、格式、依赖或前端。

## 首个候选已核验证据

- 新永久测试39通过，包含零DB、五处捕获崩溃恢复、计划／journal篡改、三种来源限制跨run、十次预算、双向互斥、根/锁/来源目录切换、混合empty及捕获后取消。
- 第一次负例运行15失败／3通过；最小实现第一次原采集／CLI／对抗及新测试108通过。独审发现恶意block类型净化缺陷后修复并加入四个回归；失败记录保留。
- 最终受影响9个测试文件626通过／0失败／0跳过，18.30秒；包含原运输阶段、采集、CLI、对抗和strict/legacy格式golden。
- 最终允许Python全仓3732通过／0失败／49跳过／2 deselected，142.96秒。49项缺私有样本及Windows原生证据仍未通过；两项既有localhost慢流测试 `test_http_slow_chunks_do_not_reset_absolute_deadline[header/body]` 按零网络边界未跑。保留既有FastAPI/Starlette的httpx弃用warning，未改依赖。
- 独立49项合成验收全部通过，包括实际子进程 `os._exit(73)` 在reservation发布与临时capture边界、合成DB哨兵访问spy、双向锁、预算和源限制。独立审查另在拒绝socket事件的环境重跑39／39永久新测试，无剩余代码阻断。
- 两组v1独立oracle均通过：默认acquire→resume，以及capture_recorded崩溃→resume导入→再次resume。每组4份plan/journal/reservation/capture JSON逐字一致，完整初次／恢复摘要相同。对照基线为 `d142513382227380618e113c92b9b31166e0936a`，不把数据库文件计入逐字主张。
- 独立qualification环境234通过及112 subtests通过，2.33秒；9个进程安装拒绝socket创建／连接／DNS／bind的审计钩子，无被阻止的网络尝试记录。与产品全仓分开报告。
- `git diff --check` 与两产品／新增测试编译通过。全仓和受影响回归使用父进程及继承环境的socket连接／DNS／bind拒绝钩子，并禁止旧私有行情路径访问；运输子进程使用既有已检查的本地注入脚本。所有Store测试数据为纯合成临时根。

### 首个候选产品字节

- `public_acquisition.py` SHA-256：`c3d405691201763207d34f4d501730b1deeb63f7af665587d3475d246159f9cc`
- `cli.py` SHA-256：`4210e96b3c80c3f30473d5f7e1cd09f1d60b8367798b232b5f6b0c35889bd05a`

上列首轮测试与本地GO针对这两个hash；PR62自动审查随后发现两个P2，后续修订见下，不把首轮GO作为新字节的通过证据。

### 保留的失败与纠正

独立前置测试旧实现23项预期失败。独立首轮候选曾有一项测试误将真正不完整的规范临时前缀要求为立即拒绝；冻结合同明确保留原字节／原预留并允许下一槽有界重试。经反方核对后修正测试，补充源blocked及预算耗尽不得重试两案；没有为迁就用例修改产品。完整错误JSON、错误hash/绑定和多候选仍拒绝。一次受影响测试命令使用了不存在的文件名，0项运行；纠正为实际9个文件后得到上列626通过。

## PR62首轮审查修订候选

自动review在 `c87bab4dfe02862b031bd47f0b645e04746cdc58` 上发现两个P2：v1 resume路由根也需跨两次读取绑定；capture-only运输期间来源目录切换后，必须在捕获或来源阻断发布前复核身份。五个先行负例全失败；修复后永久新增44通过。修复未改计划、journal、reservation字段或正常v1输出。

- 所有resume在Store构造前比较路由根dev/inode；v1持锁后再次打开根核验。v2在成功响应返回及运输错误分支入口复核根、原锁、public/sources目录。
- 原预留仍消耗预算，目录切换时以安全错误停止，不发布捕获或向旧来源目录写入限制；这不能替代历史来源状态连续性核验。
- 最终受影响631通过，18.17秒；独立54／54通过，含两个旧v1逐字及完整摘要oracle再次通过。独立新增五个race在旧候选全部失败、在新候选全部通过；代码静态独审与另行44项拒绝socket事件复跑通过。
- 最终允许全仓3737通过／49跳过／2 deselected／1既有warning，142.66秒；同一零网络及旧私有路径拒绝条件，未跑项含义与前候选相同。qualification最终重跑234通过及112 subtests通过，2.32秒；9个guard进程，无被阻止网络尝试。编译与diff-check再次通过。
- 最终acquisition SHA-256：`4047abf456bbf57e5220c9ef9880281764c6a789fbfa15e1bb1b56b050fc52d3`；CLI保持上列 `4210e96b…` 完整hash。

## PR62完整目录链复核

第二轮自动review在 `4882a8aa882d74739e63a9e2bdba00b5084a2cb1` 指出两个剩余窗口：锁前public/sources未绑定锁后句柄，以及活动run/attempts/slot未参与运输前后身份检查。11项先行负例全部失败后，统一补完整已观察目录链；保留上述前候选3737／631／44等历史，不转用为本候选证据。

- resume首次只读路由冻结root/public/run身份，v1与v2均在后续打开和持锁重读时比较。v2的sources从锁前首次存在检查冻结；attempts及slot从持锁后的首次打开冻结，不声称核实首次观察前的历史。
- 校验器每次从当前命名根重新逐层打开public→run→attempts→slot，再与持有句柄dev/inode比较；sources为public旁支，原operation.lock也重新核对。拒绝使用已脱离命名树的父句柄作为新可信基准。
- 复核点包括恢复前后、每个旧slot采用临时捕获及完成处理后、每块来源状态读取前、各发布checkpoint返回后、运输前及成功／错误返回后、活动slot关闭前和最终summary前。
- 66个永久新增测试通过；覆盖v1/v2路由public/run同plan替换、锁前权威目录替换、运输前后完整活动链、最后capture_recorded／source-block发布checkpoint及旧slot恢复末尾切换。受影响653通过，17.78秒；独立90／90通过（既有54加完整链36），双v1逐字oracle再次通过。正式36项在前候选4047上23失败／13通过。另5个首次观察前同内容目录替换探针保留为不支持的资格假设，不计通过；缺失／篡改reservation仍受原结构、计数、请求及计划hash约束。最终允许Python全仓3759通过／49跳过／2 deselected／1既有warning，142.20秒；既有未跑边界不变。qualification重跑234通过及112 subtests通过，2.22秒，9个guard进程无被阻止网络尝试。编译与diff-check通过。
- 本候选acquisition SHA-256：`ec7599a1751c480c81dac2fc5d4ca6c31ce3120c06d2e9c508f5a16355aeef02`；CLI未变。

上述为合作式本地锁及指定阶段的离散身份检测，不是任意恶意并发修改下的原子安全保证。相同inode内容被恶意重写、首次观察前删除历史再重建或目录换回，不能仅凭inode证明历史连续；因此旧真实来源状态不可用仍是实网NO-GO，目录存在或这些测试通过都不能解除它。

## 操作边界

`acquire-public --capture-only` 仅保存来源捕获，要求原权威目录和来源限制历史可用，不初始化数据库。`resume-public RUN_ID` 按原计划保持capture-only。非空成功是captured；空结果empty_result；混合完成与失败为partial，退出2。captured不是已导入或已获研究资格，数量仍未标准化、覆盖仍未核实。

完整捕获发布后恢复不重发。真正不完整临时前缀保留且旧预留继续消耗预算，允许下一槽；完整损坏或身份矛盾拒绝。旧二进制拒绝v2前可能打开Store，不支持降级恢复新模式根。

真实网络仍NO-GO，原来源限制与预算历史未恢复。没有读取、hash、复制或打开旧私有数据库／Store／行情原件，没有真实市场请求、登录、网络回退或新root重置历史。全仓允许测试中的Store仅为测试自行创建的纯合成临时数据。前端未改，本轮不重跑或重复声称前端验收。Windows原生、浏览器、真实来源、长期性能与金融效果未跑；058 STOP保持。首个候选记录冻结时尚未提交／推送／创建PR／合并；当前PR62修订的发布状态以对应PR终态为准。
