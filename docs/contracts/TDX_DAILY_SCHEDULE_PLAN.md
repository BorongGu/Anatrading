# 日线有限定时更新方案 v0.2

2026-10-08。U4 草案，按 [027 反方](../reviews/027-tdx-daily-schedule-plan-review.md) 修订，等待复审、具体实现合同与根方决策。只设计；没有产品编码、注册任务、启动守护程序或请求行情。沿用 [U1/U2 合同](TDX_DAILY_ACQUISITION_IMPLEMENTATION.md)、[真实验收](../qualification/tdx-daily-acquisition.md)、[008](../research/008-acquisition-and-revisions.md) 与 [011](../research/011-unattended-source-capture.md)。全市场、自选分钟及研究目标继续保留。

## 建议：系统触发，有限 CLI 执行

首版建议 Windows Task Scheduler 的一个有结束日期的任务，调用新 CLI `acquire-tdx-due --plan <私有计划>`。CLI 每次执行一个已固定的目标槽，直接复用 `tdx_acquisition.acquire()`，通过运行中工作台发布；禁止自行打开 EvidenceStore 或另起工作台。新入口名仅供评审，目前不存在。

| 选择 | 优点与实际限制 | 结论 |
|---|---|---|
| Python CLI 守护定时 | 无系统注册；需常驻进程，并自行处理重启、睡眠、钟表变化、退出和漏触发 | 留作可选交互启动模式，不同时实现两套调度 |
| Windows Task Scheduler + 有限 CLI | 系统负责时钟、触发及进程启动；每次业务有界，复用现有 CLI 路径；仍需业务去重和未知恢复 | 首版推荐，先审单任务模板，再受控注册与验收 |
| 工作台内部定时器 | 可以共享服务生命周期；需要增加后台任务、取消和服务关闭语义 | 当前采集通过 HTTP 与写者分离，首版不改这个已验边界 |

用户一次性配置并启用后，长期无需逐日输入日期或点击下载，是最终产品要求。以下7天仅为首次调度资格观察窗口；不能让用户每周手工重建计划充当长期自动更新。电脑关机／未登录、客户端或工作台关闭时，本版不能取数；工作台开机自启、日历维护、自动续期和积压恢复在后述里程碑继续实现。

## 官方来源与设计推论

本轮阅读微软 [任务创建](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/schtasks-create)、[多实例策略](https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-multipleinstances)、[延迟启动](https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-startwhenavailable)、[失败重启](https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-restartcount)、[执行时间限制](https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-executiontimelimit)。事实：可配置仅当前用户登录时运行、IgnoreNew、错过时间后的启动、重启次数和执行上限。推论：关闭自动重启，IgnoreNew 避免系统并发；业务持久日志仍必须存在。系统重启或漏触发不证明任何行情已更新。

`StartWhenAvailable` 可以延迟触发，官方说明通常有默认延迟；它没有本项目“逐日补齐”的语义。执行超限可以停止任务；它也不证明客户端后台刷新或工作台提交已停止。注册后的实际 XML、运行用户、触发时间、动作路径和退出结果须独立核验，不能拿模板存在当运行证据。

本轮读取 [上交所 2026 年休市安排](https://www.sse.com.cn/disclosure/dealinstruc/closed/)，确认国庆后 10 月 8 日恢复开市，10 月 10 日仍为周末休市。该页面仅提供上交所年度安排，不能作为沪深京统一日历、证券停牌或通达信发布完成证据。原厂 [refresh_kline](https://help.tdx.com.cn/quant/docs/markdown/ctx.stock.md/mindoc-1h10fh9m6recg.html) 本轮重取超时，继续受 U1/U2 已验本机源码与指纹约束，不新增开放时刻或费用承诺。

已通过普通说明页 GET 保存日历原文于私有 `artifacts/qualification/docs/tdx-daily-schedule-20261008/sse-closed.html`，30,794字节，SHA-256 `7ea10c16202c4748f0ad5bcdfe6ee07b85b5462589504604b17c9d63865e7d8c`。该文件是 `Invoke-WebRequest.Content` 重新编码为 UTF-8 的HTML文本，不能称HTTP线上原始字节。实现合同须同时固定获取时刻、适用交易所、日期名单及周末规则的官方证据；页面不存在的日期规则不能靠推测补齐。未形成完整日历证据前不得注册真实计划。

## 最小计划和目标日期

首个计划仅 `600059.SH/1d`，最多连续 7 个民用日，明确开始与结束日期，最多 5 个待采集交易日。只使用已评审、保存原文／哈希的上交所有限日期名单；当日期在日历证据范围外或规则冲突时停止，记录 `calendar_unknown`，不发刷新。SZ 股票、跨年日历、在线自动更新日历和全市场另审。

计划固定客户端目录、exe/SDK 合同版本、工作台 root/port、单证券、Asia/Shanghai 的计划时刻、每个槽的 `target_date/due_at`、日历证据、请求预算及结束边界。`due_at/end_at` 必须含明确 `+08:00`；计划内容哈希为身份。开始前列出期限内所有民用日和交易目标槽的完整分母，不依据空缓存、星期、现价或最大日期临时选择“上一交易日”。已确认休市日保留 `closed_no_target`，不计作取得行情。

建议首验尝试时刻为当地 18:00，属于工程选择，尚无通达信开放／数据闭合保证；实际取数必须沿用日期存在及原件校验。先在批准的有限当日测试窗口验触发与去重，再观察真实连续日期。自动计算的是计划内的目标槽；目标日观察、历史覆盖、经济单位和最终闭合继续分开。

## 有界触发与持久恢复

1. 定案使用客户端全局 `_state_directory(client_directory)/dispatch.json`，与既有 `current.json` 共用同客户端锁。**普通手工 acquire、due 和任何未来采集入口，在处理旧current或创建新请求前必须先核该dispatch。** `reserved/dispatch_unknown` 对无匹配内部派发身份的调用全部阻断；换计划、root、日期、手工命令均不能绕过。损坏、丢失预期保留、字段不全或绑定不符 fail closed。首次启用先持久化一个客户端级dispatch必需标记；此后dispatch缺失不能当从未调度，该标记不因换计划或终态删除。标记写成而dispatch未写成同样阻断；不能把丢失状态当作干净重置。dispatch只存控制关联，不另建行情账本。
2. due先在同客户端锁内读取dispatch/current。若已有未终结运行，先处理原运行：publication_unknown只做原root/port/run的有限GET核账，不reserve新槽、不消耗新槽预算、不发refresh/import；这次触发完成恢复后立即返回。旧手工run也只恢复自身，不归到新槽。refresh_unknown保持阻断；已关联的原槽可沿用已审会话变化规则处理，但未关联dispatch未知不能按会话变化直接清除。
3. 只有无未终结运行且无未终结dispatch时，due才选择最早待执行槽。写`reserved`前生成不可重用dispatch_id和预期run_id，绑定客户端身份目录、plan_hash、slot_id、原root/port/symbol/target_date、派发进程PID与原生启动身份。原子临时文件写入／flush／fsync／replace完成后释放锁，再在同一尚活进程调用acquire内部dispatch_id；CLI不暴露任意dispatch_id参数。
4. acquire在入口拿同客户端锁后核reserved的全部绑定和派发进程身份。只有原owner的此一次匹配调用可进入，并用预期run_id创建带dispatch_id/plan_hash/slot_id的acquisition journal。journal必须在任何网络POST之前持久化；随后dispatch记`linked`并指向同run。每一文件替换仍分别原子，多文件不存在事务承诺：reserve写后journal写前崩溃，或任一文件单边写成，都按保守未知处理，禁止clear／重发。活进程合法调用与进程死亡后的恢复严格区分；读到相同id不授予新进程继续派发权。
5. acquire返回后，只有run_id、dispatch_id、plan_hash、slot_id、root、port、symbol和target_date全部吻合，才把结果归于该槽并关闭dispatch。返回旧run／旧日期、关联缺失或写入中止时记dispatch_unknown，不能记新槽committed。关联current已经committed但槽尚未关闭时，只读原run核账再闭原槽；禁止调用允许终态新采集的普通acquire去“恢复”。终态dispatch记录保留；原槽状态先写，再终结dispatch，单边完成时下次仍仅核原关联。
6. 每次触发只做“旧运行恢复”或“一次新采集”之一。新采集最多一个refresh POST和一个import POST；恢复零POST且沿用现有有限GET预算。没有系统失败自动重启、重复间隔或当日循环退避。每槽已派发次数最多一次。已有committed槽只显示原结果引用；持久记录不能替代实际原件／快照资格。原件／请求／响应继续在现有acquisition证据中。
7. 客户端／工作台离线等已证明发生在POST前的失败记dependency_unavailable，关联run确有此终态才终结dispatch；该槽不计成功且同槽不自动重试。新槽执行仍要求全局无未知。现有publication_unknown在工作台重启后因会话改变而保持未知，本版不擅自放宽；root/symbol/date不得改成新槽参数。
8. 最早overdue每次最多一槽；未派发旧槽保持pending_overdue，新日到来不删除它。已尝试未覆盖日期保留not_covered。期限结束后公布完整分母的committed、closed_no_target、not_covered、dependency_unavailable、dispatch_unknown和pending_overdue，unknown运行单列关联状态；统计不能遗漏尚未派发槽或以高水位替代覆盖。后来的raw包含旧日期，不自动闭旧槽；离线覆盖核账与有界追赶另审。
9. 使用可注入的UTC钟表，独立读取并验证主机时区/当前偏移，同时以明确+08:00计算上海日期。每次处理前在客户端控制状态持久化前次观测UTC：now低于前次值即clock_rollback并停，禁止只读取当前日期来声称检测回拨。该严格首验规则可能对校时微调停机，容忍规则待后续合同。派发前再次核due_at/end_at；开始前或结束后零新POST。结束后的只读恢复可进行，不能生成新行情槽。

## 工作台、系统任务和停止

拟议任务使用当前交互用户、绝对 Python/入口/配置路径与明确工作目录，隐藏后台窗口；不保存账号密码、不采用 SYSTEM 或修改用户终端权限。XML 设置建议：IgnoreNew、零失败重启、有限结束边界、StartWhenAvailable=true、单次 ExecutionTimeLimit=PT3M；实际动作调用单个有限 CLI，不使用串联 shell 临时脚本。系统时间触发只是一层防并发，不能替代本机采集锁。

采集的现有每请求deadline、文件上限和指纹不变。按现有正常路径4次身份探测×8秒、5次GET×15秒、refresh45秒、import15秒已达167秒，还未含稳定读取、哈希、解码及磁盘写入；PT3M无法据此保证完整流程结束。实现合同必须给总业务deadline／阶段剩余预算，超时不再开始新POST，并验证外层180秒实际停止时可读dispatch/current保留未知。进入外部作用前已持久化reserved/refresh_unknown/publication_unknown，不能依赖被杀进程事后补写“失败”。系统控制只停止此调度Python进程，用户通达信、工作台及写者不被终止；后台任务或提交可能继续。暂停／禁用只阻止后续触发，在途import继续待核。

工作台服务缺席时不抢 root 锁、不降级直接 CLI import、不换根。服务仍持有唯一 Store 写者，调度调用已有 HTTP。第一版保持用户一次启动工作台的约束；如要求 Windows 登录后自行启动工具，另审单入口 supervisor 的工作台所有权／root锁／端口冲突／正常关闭，避免注册互相竞态的第二个定时任务。

## 开工门禁、验收与待决

先独立反方审本草案；再写固定配置格式、文件清单、注册／卸载操作、唯一派发关联与测试的实现合同。当前草案不授权注册持久任务或日线真实刷新。后续登记前须给出可审核 XML 与有限计划；不能借旧 U1/U2 最多两次实测批准新的后台请求。

必须先测：reserve已写而journal未写时杀进程，再从普通手工CLI／新计划／另一root进入，全为零POST；关联日志单边完成／损坏／返回旧run；旧日期publication_unknown+新槽due，恢复只归旧run／旧槽且新槽仍pending。另测同槽重入／并发、离线依赖、刷新未知跨日、服务重启、完整backlog、休市／证据外日期、时区／前次UTC回拨、167秒预算耗尽、PT3M停止后的可读未知日志、禁用后无新派发。使用注入钟表及有限临时任务测试系统边界。真实触发至少一槽验证raw、可读snapshot和请求数；连续交易日另授资格。

具体改动接点：新due模块负责只读计划／钟表／槽结果；cli.py新增due分支且先于EvidenceStore生命周期；tdx_acquisition.py的acquire入口全局dispatch门禁、reserved绑定和预分配run_id落journal，以及单独只读恢复函数复用现有_verify_publication，避免调用终态普通acquire；控制记录原子写帮助函数及负例测试。注册动作／任务XML作为独立明确入口，不在import或serve启动时隐式安装。详细字段、文件名与预算待实现合同再审，目前无文件解冻。

定案方向为Task Scheduler单入口+client-global dispatch门禁；保持首版工作台一次手动启动约束。后续里程碑依次为：有限触发资格、连续交易日及积压账、已审日历范围自动维护／无手工续期的长期计划、统一工作台生命周期、自选扩容和分钟调度。续期只扩大已验证日历内的新槽，保留旧未知／失败／欠缺，不能靠新plan_hash清空旧任务。18:00及实际首验时段仍由实现合同固定；不重复询问账号或交易授权。
