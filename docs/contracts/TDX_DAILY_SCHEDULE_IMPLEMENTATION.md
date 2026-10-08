# U4 日线定时入口实现合同 v0.2

2026-10-08。基于[已审方案](TDX_DAILY_SCHEDULE_PLAN.md)。本合同待独立反方与根方决定，之前不修改产品代码。成功标准：有限计划无需逐次输入日期，重复触发和进程中止不会重复POST；旧运行恢复不消费新槽。真实定时取得行情仍需另外实测。

## 范围和简化

仅新增 `tdx_schedule.py`、CLI `acquire-tdx-due --plan <绝对路径>`、必要 acquisition 内部提取、对应测试与说明。复用现有客户端锁、原件与工作台唯一写者，不新增数据库、守护服务或来源格式。保持同客户端锁贯穿 reserve→新采集→归槽；删除方案中释放锁再重入及活owner授权分支。普通 acquire 仍先检查全局dispatch。一个 dispatch.json 内原子关闭原槽和active关联，不做两次独立写入。此简化需要反方确认。

首版只有一个活跃有限计划；同客户端不同plan_hash拒绝替换。7天仅资格窗口，永久自动更新、日历续期、开机启动工作台及自选分钟仍为后续必需项。

## 固定计划

JSON严格拒绝重复字段、非有限数、超过1MiB和未知顶层字段。schema=1；root/client_directory 必须绝对且规范化；port为有效整数且非17709；symbol固定600059.SH；period固定1d；exe_sha256/sdk_sha256沿用已验指纹。

`days` 包含连续1—7个民用日，每项只含 date/kind/due_at；date为ISO，kind为open/closed，due_at固定当地18:00:00+08:00。最多5个open。`start_at`为首日00:00:00+08:00，`end_at`为末日23:59:59+08:00。每槽id采用日期，本计划哈希为规范JSON的SHA256；根目录、端口及日历均参与身份。首验批准名单仅2026-10-08—14，open为8/9/12/13/14，closed为10/11；超出此证据区间 calendar_unknown。

`calendar` 是两项原文引用，每项只含path/sha256/source_url/captured_at_utc；读取文件核哈希、时间为明确UTC且不在未来。固定来源为：

- 上交所[年度休市安排](https://www.sse.com.cn/disclosure/dealinstruc/closed/)，私有sse-closed.html，30794B，SHA `7ea10c16202c4748f0ad5bcdfe6ee07b85b5462589504604b17c9d63865e7d8c`；上轮落盘2026-10-08T08:07:56Z，只能作为已保存页面的落盘时间，精确网络接收时刻未记录。
- 上交所[股票投资说明](https://one.sse.com.cn/onething/gptz/)，私有sse-weekdays.html，45558B，SHA `f5d95746ec6f8dc7d5c9f057b230ba56eae67dce05dbae06fe62a0bdad98f0db`；2026-10-08T08:53:16.648329Z落盘。原文明确周一至周五交易，法定假日及公告休市日休市。

两者均为Invoke-WebRequest.Content重新UTF8编码HTML，不能称线上原始字节；captured_at_utc在本版定义为页面保存时点。名单为这两份官方事实的有限推导，不证明停牌、供应商开放、当日数据闭合或沪深京统一日历。

## 控制文件和顺序

所有动作使用现有 `_state_directory(client_directory)` 及 `.operation.lock`。`dispatch.required`内容固定 `anatrading-tdx-dispatch-v1\n`，一旦建立永久保留；marker-only、dispatch-only、损坏或缺失均停止。标记与dispatch均不存在时视为尚未启用；首次启用在锁内先fsync标记，再原子写dispatch，单边崩溃保持阻断。普通 acquire 在旧current处理前调用门禁，active不为空即 schedule_dispatch_unresolved，任何root/日期都不能绕过。

dispatch对象只含schema/plan_hash/plan/last_observed_utc/slots/active。plan为完整已验计划，加载时重新验身份与slots全集。slots逐日保留完整分母：closed_no_target或pending，以及唯一dispatch_id/run_id/status/result关联。active为null或预分配关联对象，含dispatch_id/run_id/slot_id/plan_hash/root/data_root_id/port/client_directory/symbol/target_date/owner_pid/owner_started_filetime/state。UUID为32位小写hex；owner原生FILETIME只供审计，绝不授权其他进程继续新采集。state仅reserved/linked/dispatch_unknown。

slots为以date为key的对象；每项恰含status/dispatch_id/run_id/result。允许status为pending、closed_no_target、reserved、linked、dispatch_unknown、committed、failed、not_covered。pending与closed_no_target的三个关联值必须null；closed日必须closed_no_target，open日不得closed_no_target。reserved/linked/dispatch_unknown须两个UUID有效且result=null，必须恰有一个这样的槽且与active全部关联一致；active=null时不得存在这些状态。终态槽的result必须为相同run/dispatch/plan/slot/root/port/client/symbol/date的终态journal且status一致；终态槽不能被active引用。所有槽run/dispatch各不重复。除此以外均 invalid_schedule_control。

每次在锁内：先验已有控制；核UTC/主机时区与回拨；持久last_observed_utc；再检查旧current。旧publication_unknown只有限GET核原root/port/run，恢复后本触发立即返回；未关联手工run不归新槽。旧preparing/refresh_unknown直接阻断，本版due不通过会话变化尝试新派发。普通手工既有会话变化规则保持。当前真实minute refresh_unknown须零RPC保持。

只有无active和无未知current，且start_at≤now≤end_at，选择最早已due的pending槽。原子保存reserved（槽和active同一文件），再以预分配run_id创建新journal与目录。journal增加dispatch_id/plan_hash/slot_id，先保存preparing，然后dispatch原子更新linked；此时才允许进入采集。preparing identity={}只在scheduled关联严格核验后用于保守中止，不放宽通用 `_journal`。若此阶段崩溃，下次保留active，不发POST。采集内部函数只从内存接收关联，公开CLI无dispatch参数。

采集返回后逐字段核run/dispatch/plan/slot/root/port/client/symbol/date/evidence_directory；不匹配保留dispatch_unknown。terminal journal的失败/未覆盖可关闭原槽；committed关联原件、快照、attempt须已按现有核账通过。终态槽result保存原journal，不宣称后来query永远可读。同槽重触发只返回保存结果与完整计数，不发POST。

active的崩溃恢复：只允许读取完全匹配的原current及原receipt（相同对象）；preparing/refresh_unknown继续阻断；publication_unknown用原会话GET恢复；已committed原run也用GET重新核原件/原快照再归原槽，禁止调用能新建run的普通acquire。failed/not_covered可核相同收据后关闭。reserved没有journal、单边receipt/current、关联不符均保持未知。恢复本次不派发任何新槽。先原journal终态落盘，再一个dispatch原子替换同时写原槽result和active=null；写入失败下次只恢复原关联。

## 时钟、预算与系统任务

due默认UTC可注入；主机独立Get-TimeZone.Id必须China Standard Time且当前偏移+08:00。now须明确UTC；now低于持久前值即clock_rollback并停止，不覆盖原值。每次新POST前重新读取UTC、检查主机时区和偏移、回拨及原槽due_at/start_at/end_at，并持久前值；越过期限不能开始import。每次新POST前检查单调时钟剩余预算；业务总150秒，HTTP每请求取现有上限与总剩余较小者，客户端身份子进程也取8秒与剩余较小者。磁盘操作/解码边界再检查预算；到期不启动新POST。期限前后只做有界只读恢复或报告pending_overdue，不能新增请求。

Task Scheduler模板：当前交互用户InteractiveToken/Limited，IgnoreNew，StartWhenAvailable=true，无RestartOnFailure，无重复触发，StartBoundary/EndBoundary有限，ExecutionTimeLimit=PT3M；绝对Python与CLI模块动作、固定工作目录，Hidden仅隐藏任务枚举，不能证明无控制台窗口。生成XML供核验，本合同只解冻生成与离线测试；持久注册、真实刷新及强停资格未解冻。源未知解除并给出精确动作/有限计划后，再独立审核注册与注销；窗口隐藏需核原生启动路径，未核前不声称无人打扰。不会在serve/import/due中偷偷注册任务。超时只停自建Python，不能停用户客户端、工作台或宣称外部动作取消。

## 验收与停止条件

先写异常输入及故障用例，再实现：非法/缺失控制、reserve后中止、preparing单边写成、不同root/计划/日期手工绕过、旧publication恢复不占新槽、错run误归属、同槽重启去重、expired/rollback/closed日历、总deadline前后POST门禁及真实ASGI单写者路径。完整Python回归通过后独立代码反方；没有真实系统触发成功证据时输出“定时入口已实现，系统任务未启用”，不能宣称已全自动。当前真实分钟未知不得为测试清除，全部边界注入私有临时目录。
