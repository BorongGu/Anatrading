# U3：时段变化后的真实分钟观察 v0.2

2026-10-08。本机UTC07:52:54（上海15:52:54），已晚于用户界面提示的当天数据15:45时点。此为新的尝试时点，不证明历史分钟主站已开放。首次诊断的三次POST预算已用尽；本合同重新评审，禁止重跑旧脚本或改HTTP时间格式试探。

## 对象和固定预算

已验 `D:\tdx_64`；`600059.SH`、`1m`，目标已结束历史 `20260930150000`。同用户实际GUI选择股票，承接已验该股票日线。产品 `.lc1/.lc5` 白名单、单位、回放、指标和schema不改。本轮仅私有资格脚本，不导入产品库，不执行SDK/账户/订单/订阅/付费数据源。

先确认 `vipdoc/sh/minline/sh600059.lc1` 是否存在，记录大小、mtime_ns、inode和hash；若有且稳定，则只发一次 get_market_data。若不存在，允许一次 `refresh_kline`（id301，stock_list只该股、period1m）后，只有完整关联成功响应和同会话时才发一次 `get_market_data`（id302，period1m、end_time20260930150000、count3、none、fill_data=false、不筛字段）。最多2POST、每个无retry/no proxy/no redirects；刷新绝对deadline45秒，get10秒；响应≤1MiB。复用已验产品 `_http` 的绝对时限与严格JSON/id闸门。

## 全客户端互斥与未知状态

复用 `_state_directory` 和 `_DirectoryLock`，与日线同客户端全局锁。先用现有 `_journal` 核当前记录；非终结记录阻断本轮，不覆盖或清除。新运行固定 `root=<已解析repo/data/local>`、`data_root_id`按既有函数、`symbol=600059.SH`、`target_date=2026-09-30`（ISO日）、`port=8765`（产品目标端口）、`run_id=uuid.uuid4().hex`（32位小写hex）、`evidence_directory=root/acquisition/run_id`。用 `_save` 原子更新current及receipt；额外记录 `purpose=minute_source_observation`、`period=1m`、`rpc_port=17709`、`rpc_end_time=20260930150000`、identity及UTC。产品端口即使工作台未运行也不能改为RPC端口，不授予日线格式资格。

每次RPC前持久化状态 refresh_unknown，再保存请求；前后均核已验exe/SDK、localhost拥有者/PID/启动时点，同会话才继续。timeout、非200、strict JSON失败、业务失败、未知Time或无有效数据均停止，无后续刷新/再试。空结果与缓存缺失分开记；不能从成功码和mtime声称客户端下载已完成。无有效记录／缓存对应证据时保留共享refresh_unknown，日线CLI也会阻断同一会话新请求。解锁只能另按已审客户端会话变化／独立任务终结证据处理，不凭等待时间清除。

get另有严格validator：外层id正确、result对象/ErrorId字符串0，result.Value对象中600059.SH对象且证券ErrorId字符串0；空结果只接受证券层恰有ErrorId/Value且Value=[]。非空须Date/Time/OHLC/Volume/Amount字符串数组、等长1—3、有限数字、合法候选日期时间、无重复且严格递增，全部不超过截止；KlineTotal不足以放行。不能用仅刷新闸门代替证券层校验。

两分支都只有实际非空≤3条、标签有效且缓存相应标签恰各一个、稳定副本可核时，才允许将本诊断终结记为共享failed/error_code=diagnostic_completed_without_publication（带明确来源观察成功状态），不伪造产品committed或快照。HTTP/cache浮点差异单列，标签匹配不授予经济单位或原值一致资格。每次_save后须以既有_journal回读并断言run_id/identity/root/symbol/ISO日/8765/状态相同；兼容回读失败立即止。旧current内容先保存至本轮证据previous-current.json；不能把已有日线原件覆盖成分钟。初检文件存在但不稳定/超限属于失败，不能改作absent以放行refresh。

## 原件与精度观察

源缓存复制≤16MiB；复制前后元信息一致，复制两次间隔250ms且SHA相同才作为稳定副本，明确记录不存在。文件过大只流hash且停止后续解码。不得不稳定重复轮询。响应Date/Time/OHLCV/Amount原字符串保留，KlineTotal不能替代数组数量；Date8位、Time6位非000000仅为当前候选观察闸门，格式变化停止、不补时间／猜边界或换19位输入。

只作候选 `<HH5f2I` 布局观察：不预设量额单位和正确价格缩放。[作者公开布局说明](https://github.com/z52c/z52cStockC)与[另一作者实现说明](https://github.com/donge/tdx_ext)使用2004+高5位／低11位月日、分钟ushort HH*60+MM。本轮把它们作为待核候选；须与真实返回标签独立对应才报告匹配。作者写的元／股没有授予当前安装同样单位。记录目标对应三条的所有原四字节及独立尾数/指数/Fraction精确值、有效scale/幅度，HTTP差异分别保存，不混源修正。全文件只流式检查标签候选和数量，不创建几十万Decimal行对象；scale精度审计限定匹配的最多3条×5float字段。超出DECIMAL(38,18)时作为后续格式表示阻断，不舍入或改schema。

## 评审和验收

先反方审本合同，再写私有脚本与离线负例（JSON重复/错id/业务错、Time歧义/越界、缓存变动、已有未知共享任务、错误路径/超限），通过后才发最多2POST。实际脚本自监测当前Python原生进程，120秒/2GiB，停止本进程不终止客户端；结果不明留下持久共享标志。截图、旧请求、纯合成输入不能替代本次实际分钟记录。

本轮通过仅支持分钟来源观察；正式格式还须真实导出语义、表示范围与时间定义合同。U4调度设计可独立推进，不因本轮未知扩大请求。
