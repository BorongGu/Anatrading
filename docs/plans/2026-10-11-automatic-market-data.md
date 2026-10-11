# 自动取数首轮：腾讯日线与新浪分钟的有界接入

日期：2026-10-11。状态：[独立设计复核批准](../reviews/2026-10-11-automatic-market-data-review.md)（APPROVE_FOR_IMPLEMENTATION，R1–R6设计关闭）；父任务已确认性能测试冻结解除，当前按批准范围实现，验收尚未完成。依据[029来源研究](../research/029-automated-ashare-data.md)及现行AGENTS.md。真实原件留仓库外，测试使用合成同形数据。

## 1. 成果和范围

一个命令可从明确公开来源下载一只显式声明为股票的沪深证券的有限数据，保存请求及原实体字节，经过新格式解码进入现有EvidenceStore，返回snapshot_id，随后用现有query/export精确读取。任务中断后可以查询状态并恢复未提交的块。

首轮仅：腾讯未复权请求的日线；新浪未复权请求的1m/5m最近窗口。真实验收首先使用029已经观察的601577.SH。通用入口要求显式声明`--asset-type stock`，仅形成`asset_type=stock, evidence=assumed`的沪深候选请求；六位代码语法及交易所后缀不证明股票类别，不能宣称入口已经排除指数/ETF。无股票声明在联网前拒绝，明确声明其它类别不支持；已有证据与股票声明冲突时停止，不靠代码前缀补足资格。当前成员清单与选股依据仅支持当前池回顾，永久/历史身份及未实测证券兼容性仍未验证。无京市、其它品类资格、全市场发现、持续调度、后台守护、前后复权、来源替换、跨源拼接、分钟重采样或新数量列迁移。

## 2. 两个格式ID与确定性捕获封套

新增 `tencent-daily-capture-v1`、`sina-minute-capture-v1`。二者使用同一个极小封套形状；首轮只提供这两个固定格式。本节为严格v1运输封套，顶层只允许以下字段；获准的旧记录离线重建版本另见第10节：

| 字段 | 固定类型/语义 |
|---|---|
| capture_version | 字符串 `public-market-capture-v1` |
| source | 字符串 `tencent`或`sina`，须与format_id一致 |
| request | 对象，恰有method/url/parameters/headers四键；method=`GET` |
| request_sha256 | request经本节规范JSON序列化后的SHA-256，小写64位十六进制 |
| response | 对象，恰有status/url/headers三键；status为整数200，bool不接受 |
| response_headers_sha256 | response.headers规范JSON字节的SHA-256；不是线路原始头哈希 |
| body_base64 | 标准RFC4648 Base64字符串，无空白，严格解码，重新编码必须相同 |
| body_sha256 | 解码所得HTTP实体字节的SHA-256 |

规范JSON：UTF-8、sort_keys=True、ensure_ascii=False、separators=(',',':')、allow_nan=False，不附加换行。新格式离线导入也要求封套原字节与规范再序列化逐字相等，不悄悄改写原件。全部对象拒绝重复键；固定子对象同样检查精确键集合与类型；哈希须64位小写hex。JSON非有限常量、BOM、孤立surrogate、超过32层嵌套及类型替换稳定拒绝。整个封套的哈希是store的raw_sha256，正文另有body_sha256，二者不得混名。限制读取长度后才解析，未规范离线字节不能以语义相同要求复用raw身份。

request.headers固定为 `Accept: */*`、`Accept-Encoding: identity`。request.parameters全部是精确字符串；url必须由本节来源固定地址和parameters按下文规定顺序urlencode重建，逐字符相等，不能用外部任意URL。该request只记录应用设置的白名单头；运输生成的Host等未冒称被完整记录，未声称HTTP线路原始字节。response.url必须与request.url完全相同，首版禁止重定向。response.headers只保留两键：`content-type`和`content-encoding`，值为收到的单一字段原文字串，缺失encoding表示空串；重复/多值对应头拒绝。encoding只接受空串或identity，禁止隐式解压后冒充原字节。

UTC开始/完成时刻、HTTP Date、网络尝试编号、错误、run_id等属于采集日志，不能进入确定性封套。否则相同请求和实体会因抓取时刻变化产生伪新批次。原件完整性不构成发布者签名或网络真实性证明，离线导入封套也只能记录来源声明。既有外部捕获只能使用当时实际保存的request、status、最终URL和headers；缺失证据标明unavailable，不能猜测或事后补造。格式必需字段无记录的原件保留并列为格式资格未满足；不因离线封装成功追授本产品的TLS/无重定向/截止/环境隔离运输资格，新运输仍须独立故障注入及真实CLI验收。

腾讯正文含会变化的qt附属字段：即使历史day不变，完整实体仍可能改变，必须保存新的完整原件/快照；不能承诺每次历史重读都复用快照。仅完全相同封套与解释保证store既有幂等；resume跳过已确认提交项则不重新请求。价格/量额修订与仅附属字段变化在日志中分开，首版不实现跨版本合并。

## 3. 请求参数及字节解析冻结

### 腾讯日线

固定地址：`https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get`。
parameters键及URL编码顺序：`_var`、`param`、`r`。`_var=kline_dayYYYY`，YYYY取该块起始日期年份；`r=0.8205512681390605`为既有公开接口示例常量，无随机生成。`param={source_symbol},day,{start},{end},{count},`，结尾逗号保留，空调整项只表示未复权请求。捕获格式允许每块最多366个自然日、count为1..640，可以跨公历年；callback仍绑定start.year。原始请求/响应均保留实际count，不伪造为64。普通CLI默认每块31个自然日/count=64；用户已明确授权的20+5外部批次采用约一年块/count=640，其导入不因保守CLI默认被拒。640为当前AKShare适配器使用参数及本次探测上界，未声称上游永久最大配额。

源证券只允许`sh`+六位数字或`sz`+六位数字，来自明确的`六位数字.SH/SZ`固定映射：后缀SH→sh、SZ→sz，数字原样保留；不根据数字前缀猜交易所、类别或永久身份。start/end为真实ISO日期，start<=end，闭区间天数<=366。纯格式解码只检查这些字面条件，不读取当前日期。只有创建联网计划时，检查end不晚于首次冻结UTC按Asia/Shanghai解释的日期；这属于工程运行边界，时区假设不升级为源时区证据。普通CLI计划分块后最多10项，超限在联网前拒绝。

response Content-Type媒体类型允许`text/html`或`application/json`，charset必须UTF-8（大小写不敏感）；缺失或其它编码先拒绝，不能自动猜编码。body用严格UTF-8解码；精确前缀为本请求 `_var + '='`，没有其它前导注释/空白或尾分号。中间仅接受完整JSON对象，末尾最多允许JSON规定的空白；不宽松搜索第一个等号、不eval/exec。

顶层必须恰有code/msg/data；code为整数0（拒绝bool），msg为空字符串，data恰有请求证券一键。证券对象必须有day；允许的其它键仅qt/mx_price/prec/fsStartDate/version及实测attribute，原样留正文，不进入研究。可选attribute须为恰含NoProfit/WeightedVotingRights/IsVIE/IsRegistration四键的对象，每值均为一字符字符串0或1；不据这些附属旗标生成品类、权利、上市板块或身份资格，未知键/形状仍拒绝。实测证据见029第7节。qfqday/hfqday或其它顶层身份分支拒绝。day为0..请求count行列表，每行恰11槽，索引0..5、7..10为字符串，6为对象。对象不能进入代码执行或字段单位推断。day为空只记录empty_result，不生成空快照或完成覆盖。

每行日期须严格YYYY-MM-DD且合法；晚于request.end的行属于本版未接受的范围异常，原件可作为已识别行情留存并拒绝解码，不裁剪后成功。早于request.start的行允许作为源返回的历史上下文，所有行按原顺序进入该块快照。依据029的真实反例：年度请求2024-10-11～2025-10-10/count=640实际返回2023-02-20～2025-10-10共640行，其中397行早于start、243行在请求区间。因此请求起点不能当作服务端严格截断保证；这项容许只适用于腾讯这个已观察的形状，不泛化为任意源范围规则。

明确记录`requested_range`、`actual_range`、`before_start_count`、`in_request_count`、`after_end_count`和`request_range_mismatch`。日期重复/逆序仍保留源序和失败检查，不静默去重/重排。行数达到count记`count_saturated`及`truncated_possible`，允许提交已得到的源观测；它只表示触及返回限制，不能独立证明目标范围有缺口。行数超过count拒绝；超过请求区间自然日数只有在核对更早上下文、重复标签后才有意义，不再用这一条件错误拒绝合法上下文。少于count同样不证明无缺日。

默认Store查询返回完整快照，不隐式按请求范围裁剪。需要目标区间视图时显式给出独立`view_start/view_end`，记录源快照/原件哈希、筛选规则、保留/排除数和逐行ordinal/locator；视图不能覆盖原件或产生“重新下载得到的两年”假象。首轮已有query只有cutoff和ordinal范围，而daily_bars不接受ordinal_window研究上下文；因此目标区间视图先作为带源ordinal的独立派生文件/运行摘要。既有ordinal查询仅用于证据查看，不当作研究入口。完整单快照可供现有价格研究；严格从两年起点重置算法另需明确选择语义。扩展下界查询接口、query_id或跨快照组合均不在本轮。

### 新浪分钟

固定地址：`https://quotes.sina.cn/cn/api/jsonp_v2.php/=/CN_MarketDataService.getKLineData`。
parameters键及URL编码顺序：symbol、scale、ma、datalen。symbol同上；scale只能1或5，ma固定no，捕获格式的datalen为1..1970的十进制字符串；普通CLI默认10、首轮交互上限240，用户已明确授权的5股分钟外部批次可使用1970。1970来源于当前AKShare实现，不构成永久保留期或完整历史承诺；日期范围不能传给此接口。一个命令只产生一个网络块。

Content-Type须`application/javascript`、charset=GBK，encoding限制同上；两个来源的Content-Type均只接受一个明确media type与一个唯一charset参数，重复/歧义参数拒绝。严格GBK解码。本轮只接受已见固定字节前缀 `/*<script>location.href='//sina.com';</script>*/\n=(` 和末尾 `);`，中间是完整JSON数组，无其它前后字节。前缀中的script文字纯作字节识别，绝不执行；不支持任意JSONP callback、回退URL或自动改前缀。

数组0..datalen行；每项恰有day/open/high/low/close/volume/amount七键，值均为字符串。空数组记录empty_result不发布空快照，已识别的空行情封套可以保留；返回超count拒绝。恰datalen记`count_saturated/recent_window`，可正常提交，不能视作网络/存储失败。day严格YYYY-MM-DD HH:MM:SS，合法且秒为00。不推断14:58/59省略原因，不强迫全天固定根数；也不因缺前日数据伪造历史补齐。请求没有日期限制，因此只作源标签合法性检查和实际最早/末条报告。未知源时区及市场阶段不由抓取时钟晋级；未来于采集解释日的标签只在绑定该次冻结采集UTC的日志中诊断；确定性封套离线decode不读取系统当前时间，不因重导日期改变检查、manifest或snapshot。参考固定为plan的`observation_reference_utc`及`label_timezone_assumption=Asia/Shanghai`，resume不改动。该诊断仅报告，不改变decode、manifest或发布结果；离线封套没有可验证采集时钟，显示`acquisition_clock=unavailable`，不能制造“未来日期检查通过”。任何情况下均不得据此升级源时区、闭合或known_at资格。

响应没有身份回显，metadata必须分别用`requested_symbol`、`requested_period`、`requested_adjustment=none`及`response_identity=absent`；source_code/source_venue/source_adjustment不伪造为源回显。用于现有UI的展示声明通过interpretation保留assumed。period可取请求1m/5m用于标签格式，另记`period_evidence=request_declared`。

## 4. 精确字段与未规范数量

两个格式均将源价格/金额字符串送入既有decimal_value；不经DataFrame/float。腾讯token映射O=1/C=2/H=3/L=4/volume=5/amount=8，source_date=0，其余标量按source_extra_7/9/10保留；对象6只在原件中保留并附定位。新浪映射同名字，source_date/source_time由原day无损拆分，原day仍保留。tokens.volume永远是原字符串；不换算、不截断、不四舍五入。

首轮对于两个新格式，所有source_volume列均NULL，包括表面整数，避免同一源量有时为手、有时被误认为股。volume_shares/amount_cny均NULL；amount保存原数值尺度，明确腾讯原额候选万元、新浪单位unknown，不能标成标准CNY。

精确处理路径：为这两个格式构造SourceRow，或为_row增加仅由内部源解码器可选的显式策略`volume_policy=unstandardized`；旧四格式默认行为完全不变。该策略先用decimal_value对原volume token作词法/有限/范围检查，再显式检查Decimal值>=0；decimal_value本身不负责非负约束。合法时增加`source_quantity_decimal=pass`，将values.volume设None，并生成`numeric.volume=not_evaluated`、reason=`source_quantity_not_normalized`。不得调用integer_value原token，也不得先制造`integer_fraction`再删除失败。原token缺失/非法/负值仍分别产生相应源数量检查，不冒充合法未评价。

后续_quality的`zero_volume_amount`、`conditional_price_bounds`及`conditional_price_bounds_cent`对该策略均为not_evaluated，reason=`source_quantity_not_normalized`；没有必要计算假设股/元的比值。`standard_units`继续not_evaluated。原OHLC有效性与价格研究不应被volume为空全面拒绝；依赖量能/VWAP的入口必须给缺数量/单位的原因，不能显示已有验证。不要更改全局schema或BIGINT类型；源数量Decimal规范列迁移另行研究。

腾讯metadata保留原响应键如`sh601577`，按上述固定规则产生可与解释声明`601577.SH`对比的source_code/source_venue，并注明`response_key_mapping`；字符串相等只证明声明对应。新浪source_code/source_venue保持缺失，不能由interpretation或研究分组反填为源回显。metadata明确requested身份与response身份、范围、未复权请求、源标签、body/request/header哈希、source_units状态、identity/period证据。instrument_id始终未验证；时间边界/closed/known_at未知，source label与采集UTC分开。该版本只允许retrospective查询。

## 5. 最小CLI和运行预算

新增两个命令，不新增守护或网页面板：

- `anatrading --root ROOT acquire-public --source tencent --symbol 601577.SH --asset-type stock --period 1d --start YYYY-MM-DD --end YYYY-MM-DD`
- `anatrading --root ROOT acquire-public --source sina --symbol 601577.SH --asset-type stock --period 1m|5m [--count 10]`
- `anatrading --root ROOT resume-public RUN_ID`

前两行是同一个acquire-public命令的两种合法组合。不支持一条命令隐式展开全市场。腾讯拒绝--count；新浪拒绝--start/--end；所有未知选项或不匹配组合在联网前失败。RUN_ID为32位小写hex，不接受任意路径。首次调用创建新run；恢复不得替换任何参数。重复调用acquire-public表示一次新的显式观察，resume只推进旧run。

冻结预算：普通CLI单run全历史最多10次网络尝试（发送前预留，崩溃后不能确认是否发送仍占一次），仅串行一个连接。每次尝试从启动运输进程之前计15秒绝对截止，包含DNS、连接、TLS、头、全部实体读取；一条命令的采集阶段单调时钟预算180秒，跨resume的发送次数总额不重置。实体上限1MiB，封套上限2MiB；不会先无界读取后检查大小。相邻网络发送至少1秒间隔；恢复后首个新发送也等待1秒，保守避免丢失旧单调时钟造成连发。这是工程保守值，不声称等于源限频许可。180秒不承诺强杀数据库事务；接近截止时不再发请求，已进入store提交临界段按既有最终结果收尾，单独报告结束耗时。

运输限定一个很小的Python标准库HTTPS子进程，固定这两个host/path、GET和白名单请求头，使用默认验证证书与hostname的SSLContext；不引入采集框架或后台服务。主进程持有唯一Store及预算，通过有界IPC收取结果；运输进程不打开数据库，不继承Store对象/文件描述符。使用绝对解释器路径、隔离模式、close_fds和最小环境白名单；不复制调用者环境，不读取Cookie、netrc、账号、token、代理/代理凭据或环境TLS覆盖，不采用全局可变会话。固定HTTP客户端不自动跟随重定向或解压；TCP地址解析不改变HTTPS hostname验证。运行平台确需的系统路径/临时目录逐项列入非秘密白名单，不默认继承HOME/PATH或插件凭据。这是程序行为/环境边界，未建立OS文件系统沙箱，也不声称阻止可信运输代码读取所有本机文件。

主进程用monotonic截止监督运输进程；普通socket timeout只是辅助。DNS阻塞、慢滴或取消时终止并回收该子进程，确认它已退出后才释放锁或运行下一项；不留下继续发请求的线程。stdout/结果IPC累计上限2MiB，stderr累计上限4KiB；父进程边读边限额，超限立即终止，不用无界communicate后检查。到期即终止、必要时强杀，回收等待预算最多2秒；超过回收预算而仍无法确认退出时报告transport_shutdown_unconfirmed并停止，不能继续发送或声称已安全回收/墙钟达标，保留锁直到确认终态。正常支持环境须实测15秒截止加最多2秒清理，上述OS终止失败作为明确失败情形。异常只返回预定义安全错误码。测试必须证明该监督对DNS卡住和不断到字节的响应同样有效。

HTTP头累计上限64KiB、100个字段；状态行/中间响应同受预算。重复Content-Type、Content-Encoding、Content-Length、Transfer-Encoding，矛盾长度，CL与TE同时出现或未支持的传输编码均拒绝。最多一个chunked传输编码可解帧为HTTP实体；其分块行/trailer也计入有界运输开销，不作内容解压。EOF/声明长度/终止块须一致，未完整接收不得封装成功。所有3xx拒绝，仍占已预留的一次请求。非identity Content-Encoding拒绝，不能保存解压后的字节冒充实体。日志仅存安全状态、已读长度及带`complete/partial`标志的hash，不复制异常repr、任意HTTP头或失败正文；Retry-After只接受有界整数秒或可解析HTTP-date并标准化为安全值，不原样回显。

首轮不自动重试。网络超时、断连、5xx为failed_transient，可显式resume，在剩余请求预算内进行一次新的尝试；403/401/429、验证码/封禁提示、身份/格式/语义异常为blocked或failed_terminal，resume不得联网。429记录安全解析后的Retry-After后停止，未实现自动等待重试。源阻断记录在本数据根的安全来源状态文件中，同源新run也须检查；未知解除时刻保持blocked。不能自动改root、IP、源地址或新run绕过限制；本地文件不宣称提供跨计算机的全局限制追踪。HTML及非行情回复只记非敏感状态、字节数和哈希，不保存正文为行情原件。所有失败保留。

## 6. 检查点、锁与提交

复用现有EvidenceStore独占数据根操作锁；首版CLI在整个有界运行期间持有同一锁，并由这个store实例提交。若工作台/其它进程已持锁，联网前失败，提示结束现有占用或改用其未来受审的owner入口；不启动第二数据库写入者。本轮不增加HTTP异步采集路由。POSIX锁文件不删除。

### 不可变计划与逐项身份

数据根新增`public_acquisition/<run_id>/`。`plan.json`先持久化后联网，创建后不覆盖，字段包括计划版本、run_id、首次冻结的observation_reference_utc/时区假设、请求策略名/总预算，以及按序的blocks。每块冻结：
- `block_id`：固定从1开始的序号及该块规范描述哈希；source、symbol、period、requested_adjustment。
- 完整规范request及request_sha256，format_id；request/response URL按第2节规定匹配。
- 完整interpretation，固定为instrument、venue、asset_type三键，stock是显式assumed声明；无隐式默认、无猜测单位。
- `decoder_identity`：该format的capture版本、单独新增的源解码合同版本、该合同规范JSON哈希以及当前完整`VERSIONS`。这些常量在联网前可计算；合同含静态源语义及映射，运行时刻、正文统计不混入。首轮仅新增两种format的合同，不为此变更旧四格式或全局VERSIONS。

`plan_sha256=SHA256(canonical_json(plan_without_plan_sha256))`；明确排除hash本身。块哈希同样排除自身ID/hash，不循环引用plan hash。所有持久JSON拒绝重复键、未知字段和类型替换，文件先做尺寸限制（plan/journal各<=1MiB、单attempt记录<=16KiB）。软件恢复时必须具有完全相同decoder_identity；不兼容即`decoder_version_mismatch`停止，不能用新版默认解释重跑旧计划。以后主动重新解释另建明确任务，不伪装resume。

### 发送预留、捕获槽位与持久性

只保留几类小文件，无新数据库：`plan.json`；作为进度索引的`journal.json`；`attempts/000001/`等连续全局尝试目录。每个attempt有不可变`reservation.json`，绑定plan_sha256、block_id、request_sha256、尝试号和安全UTC日志，固定捕获槽位`capture.json`；journal不接受外部路径。capture的hash写入journal后不得改变已有槽位。同一块显式重试创建新attempt，不覆盖旧文件。

先原子持久化reservation并在journal记录requested/累计预留次数，再发GET；任何预留均占预算，包括实际尚未发出就崩溃的情况。恢复按全部连续reservation复算尝试数；已标记的历史尝试丢失、序号缺口、字段/计数相矛盾立即停止。reservation已成功而journal仍是旧索引的唯一允许落后情形可由完整reservation重建，重建必须单列recover事件；不能靠减少计数获得额度。初次计划最多10项并不授予10次以外的重试；预算耗尽保留pending项且返回`budget_exhausted`，不发第11次。

顺序：参数/锁/身份校验→持久计划→持久预留→有界下载→市场类型/身份基本预检→原子发布该attempt的capture.json→journal记captured→同一store.import_bytes→核对账本/原件→journal记提交。预检拒绝非行情、错证券/不可识别控制响应，不能写行情raw；已识别行情的数值或范围失败可保留封套与拒绝原因。合法空行情保留封套、记empty_result，不导入空快照。

每个发布使用同目录唯一临时文件、flush/fsync、atomic rename，并在支持的平台上fsync父目录；预留目录、计划、封套和journal的目录项均需覆盖。文件操作在根内且拒绝symlink/reparse point：逐组件检查取得可信目录句柄，采用平台支持的no-follow/独占创建与替换，读前复核普通文件类型/尺寸；仅Path.resolve前检查不足以当作防竞态保证。不接受`..`、绝对路径或journal自带路径；RUN_ID格式正确不替代路径检查。首轮只承诺经故障注入验证的进程崩溃恢复与本地文件系统持久发布；目录持久化不可用/失败即不继续联网，强断电、网络盘及Windows原生未经验证单列，不能承诺任何存储都保持计数。缺失、无法重建的预算证据fail closed，不新建同ID计划。

### 恢复和提交确认

恢复首先验证计划、所有reservation、journal和每个已预留槽位；不能只读取journal已引用的文件。若capture.json已落盘而journal尚未引用，直接从对应固定槽位发现并验证，不重新下载。完整临时封套可在该唯一attempt槽位校验后安全发布；不完整临时文件保留为失败证据、不冒充捕获；多个候选/残留互相冲突即`ambiguous_capture`停止。此处不实现通用扫描/垃圾回收。

每份封套除自身hash外，必须逐字匹配其block冻结的request及hash、source/format、URL、symbol、period/adjustment；解释和decoder_identity只能来自计划。另一合法证券、相邻块或旧版本封套即使hash正确也不能接管。自报来源和局部hash仍不构成网络真实性或抗恶意本地篡改证明。

已提交项从store核验attempt、raw完整性、完整interpretation、contract/source_contract_id、VERSIONS、batch_id及snapshot_id。按现有store算法重算manifest/batch/snapshot身份并比对，不以“存在同raw的某快照”代替；核实后跳过网络。captured但未确认提交，按完全相同封套和解释查询或重入现有幂等import；COMMIT成功但ACK丢失可多一条import attempt，不能新增不同batch/snapshot。store返回`import_outcome_unavailable`时保持待核验，不改成可重下的网络失败。损坏原件、冲突账本、身份不匹配停止dependent块。

只有完整恢复扫描确认没有已捕获封套的requested/interrupted或failed_transient尝试，才可在剩余预算内创建新reservation并发GET。Ctrl+C在发送前/提交临界段前尽快记cancelled；运输进程先停止回收，已进入store提交临界段遵循其既有最终结果。cancelled/blocked/failed_terminal无联网resume；异常退出遗留requested标interrupted并保留旧attempt，不改变观察参考UTC。

## 7. 完成、覆盖与修订的分离

单块状态只用pending/requested/captured/committed/empty_result/failed_transient/failed_terminal/blocked/cancelled/interrupted。empty_result为该块终态，可继续处理下块；每次命令在全部项处理完成或首个停止原因出现时返回，不让余下pending造成“仍在运行”假象。汇总规则：

| 条件 | run结果与恢复 |
|---|---|
| 全块committed | `status=committed`只表示源观测已存储；`coverage=unverified` |
| 至少一块committed，另有未完成/空项 | `status=partial`，同时输出stop_reason、未完成块和resume_allowed |
| 无提交且全为空 | `status=empty_result`，不新建快照、不联网resume |
| 无提交且网络超时/断连/5xx | `failed_transient`，余项pending；预算尚余且无源限制才可显式resume |
| 401/403/429、验证码/封禁 | `blocked`，停止整run，同源限制保留；resume只回报 |
| 格式/身份异常、证据损坏、版本/计划冲突、预算耗尽 | `failed_terminal`及具体error_code，停止；budget_exhausted不把pending当成功 |
| 取消、进程中断、无法核验提交 | `cancelled`或`interrupted`；取消终态；中断先离线恢复核对，未知提交不得触发网络 |

partial保留其stop_reason对应的恢复规则。source_error、row_limit、timeout、empty_result、budget_exhausted、corrupt_capture及commit_outcome_unavailable分开报告；count_saturated是已观察行情的诊断，不是提交错误。实际最早日晚于独立目标起点时标`target_start_not_observed`，不能称目标两年成功；边界已出现仍不证明中间无缺日。空结果、源截尾可能和缺日无法判断分别呈现，不推进覆盖水位。

输出最少包含run_id、plan_sha256、source、requested_symbol、period、请求次数/剩余预算、每块请求/实际/目标视图日期范围及各自行数、status/error_code、snapshot_id/attempt_id、reused、quantity_normalization状态及coverage。已提交成果在后块失败时可查询，但整run显示partial；失败不回滚既有不可变快照。

首版不自动组成跨块快照，也不把最大日期当成更新水位。原计划的已提交块resume跳过；需要重叠区检查/新版观察时创建显式新计划，同一原件幂等，变更产生新原件/快照。日志比较只报告共同源标签的exact token变化、新增/消失标签及附属响应变化，不覆盖、去重或自动跨源合并；没有历史日历时消失标签不解释为退市/停牌。

## 8. 编码前异常用例与验收

先写异常测试，再实现。合成同形字段/行，禁止拷入029真实价格、数据文件或CSV；研究哈希仅用于人工追溯。

1. 封套重复键、未知字段、hash不符、非规范Base64、URL/parameters不符、source/format不符、bool状态码、跳域/重定向、非identity编码、超限与截断正文。
2. JSONP任意前后脚本、分号/注释漂移、错误callback/year、无前缀、重复JSON键、NaN/Infinity、编码错误、HTTP200非行情或业务错误；永不执行JS。
3. 错证券、qfq/hfq分支、晚于end行、合法更早上下文、非法label、逆序/重复、0行/超count/恰count；跨年、闰年、366/367天、count=0/640/641、新浪1970/1971。合成三日count=2截尾和年度640条更早上下文，证明末日/条数上限均不产生coverage=complete，合法更早行不丢失，显式视图计数/定位可复算。
4. 合成小数手、整数外观手、非数/负数/超精度量、金额Decimal边界。合法小数volume原token精确保留、values.volume=NULL、numeric.volume=not_evaluated且无integer_fraction；旧四格式检查和查询不变。
5. reservation发布前后、journal更新前后、封套发布但journal未引用、captured之后、raw发布后、事务内、COMMIT后ACK前独立强制中断；resume不跳未提交项、不重复发布、不重发孤立完整capture。预算全历史重算、不明发送计入额度；plan缺失/篡改、计数与reservation矛盾、重复键/类型替换、原件损坏、磁盘满、symlink/reparse逃逸与第二写入者安全失败。
6. 两次完全相同封套复用既有快照；只改qty/price/qt各自产生可追溯变化；新版本不改变旧snapshot/query/export；缺quantity不会被转成0或可用量能。
7. Linux实际CLI→源请求→raw→store→query/export链：腾讯至少一个31天内日期块，新浪1m/5m各一次小count；另离线导入当前真实年度640与新浪1970捕获，核对字节/行数边界及显式视图，不为适配旧小默认重抓。检查原字符串、请求/实体hash、标准单位空值、可复查snapshot。真实接口失败如实记失败，离线模拟不能替代。
8. 同一封套模拟D日/D+1日解码和重入库，检查/metadata/manifest/batch/snapshot/query逐项相同；resume跨午夜仍用首次冻结UTC。替换为另一合法证券/相邻块封套、改解释、升级合同或全局版本一律停止，不将别块当完成；旧四格式身份不变。
9. 假运输注入DNS阻塞、慢滴、无限/超大实体、超头预算、恶意302、含凭据环境代理、gzip/重复头/长度冲突和恶意错误头；15秒绝对截止和180秒采集截止有效，无额外请求、后台残留、继承秘密或日志泄漏。包括取消与临界段跨预算的明确结果。
10. 000001.SH/510300.SH语法成立不等于股票：缺显式stock声明拒绝，有声明只保留assumed，不能输出已排除非股票；错源键、声明冲突、新浪无回显分别测试。真实当前池名单/选择依据与永久历史身份分开。
11. 最终受影响Python/API/导出测试及既有数据根锁恢复测试重跑；前端若无改动仍验证现有读取不会崩溃，额外UI改动须另定浏览器验收。Windows原生运行未做即列未验证。

独立审查必须覆盖原始HTTP实体与封套区别、采集时间/幂等、JSONP注入、身份回显缺失、小数手、截尾、源预算、锁/检查点恢复及数据许可。逐项答复并修订后再编码。实际通过/失败/跳过/未跑分别记录，不称已完成大规模全市场自动采集。

## 9. 扩大首批样本后的合同修订与R1–R6答复

2026-10-11用户明确请求两个板块各10股近两年日线、同板块5股分钟。该授权扩大仓库外有界采样数量，未自动扩大普通CLI、产品网络预算或上游许可。捕获格式统一接受腾讯<=366自然日/count<=640、起始年callback及新浪count<=1970；`small-window-31d-64`是普通CLI策略，`bounded-sample-366d-640`只描述本次受限外部样本请求。离线导入不要求重写真实count或重新抓取。

早先外部方案是20股各两段年度请求加5股两频率，计划40+10次、总授权上限60；其中首个旧策略请求和诊断共已消耗2次。029新反例确认服务返回早于start的上下文后，外部批次改为20股各一次`start=2025-10-11,end=2026-10-09,count=640,_var=kline_day2025`（364自然日），另5股各1m/5m共10次，该20+5子批次计划30次；用户后续追加的科创板10股沿用独立外部计划，整体有效捕获40份，含先前两次观察累计42次，实测记录见029第6节。独立研究视图目标仍为2024-10-11～2026-10-09；原请求起点与研究视图起点分开记录。既往2次继续占全批次60次总预算，原件保留；只在最早返回晚于研究目标起点时考虑有界补取，不把恰count误判为必须重抓。此处记录计划与授权边界，实际完成以029证据/批次索引为准，不把计划数当成功数。

单个640条响应若确实含两年目标，可在一个现有Store快照内保留全部源上下文并显式取目标视图；这只解决该响应所含的行。多块仍各自形成独立snapshot，没有现成跨块两年Store研究上下文。首版不能宣称20只完整两年研究已可运行；不加临时拼接bundle或跨快照合并，后续需要时另定复合上下文合同、审查并复用当前原件。

| 初审项 | 本次处理与待验门槛 |
|---|---|
| R1 范围与大批次 | 第3/9节分离格式上界、普通CLI默认和外部授权；纳入真实更早上下文，只拒绝本版未接受的晚于end，原件/Store不裁剪；第8节含合成边界及现有真实捕获导入 |
| R2 确定性 | 第3节纯decode不取时钟；plan冻结UTC仅供journal诊断和初次联网日期边界；离线缺钟不假通过；跨午夜身份测试 |
| R3 请求/解释/版本绑定 | 第6节每块冻结request、完整interpretation和decoder_identity，现有manifest身份重算；版本不兼容停止，别块合法封套不可替代 |
| R4 崩溃/预算/路径 | 第6节不可变reservation预留、固定attempt捕获槽、可重建旧journal、全历史预算、no-follow路径、目录持久化和COMMIT/ACK重入；状态表与故障注入具体化 |
| R5 网络可执行边界 | 第5节无秘密继承的短命标准库HTTPS运输进程，父进程绝对截止/回收，有界头/实体/IPC、TLS、无重定向/代理/解压，安全日志；180秒只限定采集阶段 |
| R6 类别/身份 | 第1/4节显式stock声明保持assumed，正则不授予品类；腾讯响应键固定映射，新浪不伪造回显；第8节指数/ETF反例 |

以上作者答复已获独立设计复核批准，决定及保留门槛见评审第6节。设计复核时未编码、未跑新产品测试；后续实现及实际测试须另行记录，不能凭设计批准授予真实运输、Windows或覆盖验收资格。父任务已明确确认性能冻结解除并授权按此合同编码。


## 10. 获准的旧记录离线重建版本

2026-10-11 04:37 UTC，作者与独立审查者明确协议后，父任务授权以下最小补充。原外部脚本仅记录headers.get选中值，无法还原原始HTTP头数量；不补造头对，也不将其封装成严格v1运输证据。

使用同两个format_id和独立`capture_version=public-market-legacy-reconstruction-v1`。除第2节全部原字段外，唯一额外顶层字段为provenance，恰有五键：capture_mode=`legacy_reconstruction`、header_cardinality=`unrecorded`、transport_evidence=`not_established`、original_manifest_sha256及capture_script_sha256。后两者须小写64位hex，不含重建时刻、路径或任意说明字段。请求、正文、实际已选中的两个头值及各自hash仍按原规则逐字验证。

独立`build_legacy_capture`只接受真实记录的selected_headers字典，不调用需要实际头对的build_capture。离线转换器负责读原manifest、脚本和实体文件、真复算哈希并逐项核对记录对应关系；纯decode只能校验provenance哈希语法，明确`provenance_hash_verification=syntax_only`，脚本哈希不被说成历史执行证明。原文件和旧失败审计保留，新封套写独立目录。

legacy的contract明确capture_version、raw_kind=`legacy_http_capture_reconstruction`、三个固定限制及provenance_hash_verification；metadata同步显示这些限制和provenance。raw及contract身份与严格v1不同；同一原件及同一manifest可幂等，不同原manifest有意生成不同证据身份。默认public_contract/decoder_identity和严格v1既有metadata保持不变，不改全局版本或旧四格式。

网络采集_binding只接受`public-market-capture-v1`，无条件拒绝legacy，包括新捕获发布、完整临时文件接管和resume已存槽位；不能用一个请求相同的离线重建替换在途网络证据。legacy只允许离线解释及既有Store导入，不新增网络请求、自动重抓、源单位或运输资格。

必验：provenance漏键/多键/类型/哈希/标志伪升级、版本与字段错配、selected值缺失、strict-v1完整解码黄金摘要不变、legacy重复与不同manifest身份、网络槽位拒legacy。STAR附属attribute另有正反形状测试，源数据完整保留且不生成附属字段的市场解释。
