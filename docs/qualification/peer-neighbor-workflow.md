# 同步双窗有符号相关检索：限定验收

日期：2026-10-12 UTC。基准 main：`63e392cbd682eb0ce2cbfdcfc15fad69632e87ec`。本片新增批量检索入口，在一个明确自选组中一次查看目标对所有候选的前60与当前60来源区间相关、各窗完整排名、精确并列、变化方向及原始端点。产品定义见[049研究](../research/049-signed-peer-neighbor-workflow.md)、[冻结计划](../plans/2026-10-12-peer-neighbor-workflow.md)和[验收协议](../plans/2026-10-12-peer-neighbor-acceptance.md)。

## 初次合成验收通过范围

- 纯数值以独立 Fraction 均值中心化参考核对精确符号、相关平方与排序，覆盖反向关系逆序、非同一序列真并列、显示相同但位次不同、微小非零、常量目标只关闭一窗、Δ估计为0但精确增加。合法大整数例观察到最大57,076 bit中间量，低于65,536 bit保守预算；这项是正确性检查，没有性能结论。
- 目标121日期组固定、精确cutoff、额外/缺失/重复/不可定位日期、坏价/OHLC、完整来源全局身份反证、无目标窗仍保留已扫异常、20例截断后仍生效的阻断；2–50成员、每源20,000行/合计200,000行与2 MiB结果预算。
- 新建合成Store → 实际进程内ASGI API → 前端DTO/身份核对 → 静态SSR；原token、精确close、ordinal、全部121日期与三处边界按钮回调。原件损坏/缺失拒绝，恢复后重试；旧Store及真实行情未读。
- 控制器缺目标零请求、重复提交单入场、编辑/取消/卸载、准备或摘要等待中断、迟到成功/失败不覆盖较新状态。请求错误与成员理由分别解释；`raw_object_missing`、`raw_object_corrupt`、`snapshot_not_found`、`service_busy`、`connection_error`等继续使用共享恢复说明，未知码与`constructor`/`__proto__`等采用own-key安全回退。
- 最终过滤合成Python：**3,287通过、0失败、1跳过、34 deselected、1项既有警告**，133.51秒。另14个真实样本实例随整文件ignore未收集，不能称未过滤全套通过。Windows跳过为`tests/test_tdx_session.py:280`的“Windows native current-process evidence”。
- 最后仅整理两个新前端文件的多行类型、控制流、JSX及局部命名后，全Node：**482通过、0失败、0跳过**；TypeScript/Vite构建通过。Python两个产品文件SHA保持不变，沿用上述后端结果。既有Starlette/httpx、npm `http-proxy`及755.40 kB主包大于500 kB提示保留。

独立审查另有Python30项、DTO/控制器22项、SSR/回查9项；这些与作者检查有重叠，不累计为市场证据。最终字节复验及发现/修正见[实现审查](../reviews/2026-10-12-peer-neighbor-implementation.md)。

## 失败历史与重跑

原始阶段日志保留在本轮隔离验收目录，不提交私有运行产物。以下失败没有改成skip，也没有通过调窗口、口径或产品期待消除：

1. 编码前异常测试首先因模块未创建而收集失败。其后新增区间外身份token反证测试首先失败，修复新模块的全局资格判定；旧helper和Store未改。
2. 独审发现无目标窗口时丢失已扫描异常/全局原因，以及DTO允许几类内部矛盾，按冻结定义修正。未知Unicode/原型名check须保留；已知精确边界须优先于有限小数估计。独立测试包装器的空列表错误单独修正，不改产品期待。
3. 第一轮全Node为477通过/3失败：移入仓库的独立异常fixture使用了位于当前合成窗口内的日期，却声明outside；仅把合成日期恢复为窗外，再得482通过。两轮日志均保留。
4. 第一轮最终Python：**244失败、2,270通过、34 deselected、140 errors，exit 3**。进度约57%后开始失败，最早可见错误堆栈在终止处为Pytest输出flush的`OSError: [Errno 28] No space left on device`；内部错误中断了逐项failure展开，不能把所有失败笼统归因磁盘。当时临时文件系统满；该轮runner也缺少main守卫，可能参与资源耗尽。
5. 第二轮使用新workspace临时根：**3,285通过、2失败、1跳过、34 deselected**。两失败准确为`test_lock_excludes_other_process_and_preserves_inode_after_release[close/crash]`，`parent.poll(20)`超时。捕获stdout出现重新从2%开始的嵌套pytest：外部验收runner未加`if __name__ == '__main__'`，spawn子进程重新执行了整个测试入口。修复仅在验收runner，未改锁、Store或测试期待。
6. 第三轮保留相同过滤清单，修复runner守卫，使用另一个全新合成临时根，得到上述3,287/1/34终态。首次失败新建目录随后仅做保留式迁移，原/目标文件相对路径与大小清单一致；没有清理其他临时目录或打开旧库。
7. 前端可读性整理的中途格式化曾把`i++`拆开，首次类型检查报TS1109；当场修正，随后受影响全Node及构建通过。该编译错误没有改变运行定义。

## 明确的真实样本排除清单

在setup前忽略整个`tests/test_real_pipeline.py`（14实例），并按`item.originalname` deselect下列20个函数名（合计34实例；同名可出现在不同文件）。没有探测私有路径、打开样本后再决定skip：

```text
test_private_real_pair_against_original_daily_integers
test_native_slice_matches_full_stored_query_when_real_samples_exist
test_real_native_uint32_oracle_every_window
test_local_real_sample_control_values
test_known_negative_sample_remains_quarantined
test_local_bao_samples_keep_exact_source_values
test_real_minute_fraction_oracle_and_http_binding
test_private_real_pair_against_raw_independent_oracle
test_real_native_integer_close_oracle_every_window
test_private_real_action_boundary_and_original_values
test_private_three_market_type_one_records
test_real_three_market_uint32_oracle
test_real_minute_http_tokens_exact_oracle
test_three_market_original_integer_oracle
test_real_minute_original_decimal_token_oracle
test_real_three_venue_native_fields_and_original_integers
test_private_real_capture_matches_original_tokens_and_cache_labels
test_real_frozen_reference_samples
test_real_native_uint32_tr_and_fraction_atr_bounds_every_row
test_private_real_capture_against_independent_cache_integer_oracle
```

执行入口为带main守卫的`pytest.main(['tests', '--ignore=tests/test_real_pipeline.py', '--basetemp=<本轮全新合成目录>', '-q', '-ra'], plugins=[SyntheticOnly()])`；`SyntheticOnly`在collection阶段移除上述原函数名并调用`pytest_deselected`。Node执行`node --test tests/*.test.mjs`，构建执行`npm run build`。运行临时根和完整排除实例账本仅留本地。

## 后续有限真实来源核对（2026-10-12）

被测main为`81a826c6fb86e08ffe76ebb584cb16b03acb597b`，与实现冻结提交的tree相同。固定8份既有腾讯完整日线捕获、2个显式4成员组及1个预定截止日；每组3个候选、两窗各60个变化、共同121个端点。沿用既有登记样本，没有依据相关值更换成员、目标、截止或窗口；这批样本此前已有来源兼容检查，不具备新独立留出或市场盲测资格。

- 8份捕获各导入一次至唯一新Store，核对5,120行、51,200个原字符串token及源序号；不重新采集、不截源、不读旧数据库。原OHLC/source amount精确值保留，数量及金额经济单位未获认证。
- 产品执行前冻结的独立Fraction均值中心化参考，与产品整数中心化路线逐项一致；独审另从原token重算，核对12格相关的符号、精确平方、显示、排序/并列判定和6个跨窗方向。两份纯报告及两次进程内ASGI API通过；每组先完成4份完整来源计数，再完整加载，保留全部成员和候选，两窗各K=3。
- 两份实际API响应通过现有DTO和分析身份校验、静态SSR核对，共968个使用端点。24次同版本边界日期前缀API与24个专用按钮callback参数闭合；13,920条前缀记录是重复回查，不计为新增样本。前缀query_id与完整query_id分开，未宣称浏览器点击或前端独立重算原件。
- 执行与独审确认41份冻结输入证据及16份选定源码指纹不变。独审直接核对原件算术、保存的报告/API/SSR及身份；完整query/projection/prefix和内核中间量未单独落盘，相关复核依据保存运行断言与账本，未重新打开Store或重跑产品。新Store的预期写入/关闭不要求数据库字节不变。

来源资格继续分层：2份标准捕获的外部managed-egress证据和`strict_cli_qualification=unchanged_failed_run_1`保留，未追授原strict CLI成功资格；6份legacy的重建模式、未记录header基数、未建立运输证据和仅语法哈希资格不变。legacy资格及通用范围metadata经完整source query和前缀API核对；strict CLI/managed-egress来自冻结外部证据，未宣称写入query。双窗DTO保留scope/limitations和来源引用，并不直接携带全部采集运输字段。请求范围不符、计数饱和、覆盖未核实、可能截断及采集时钟不可用均保留；保存捕获完整不认证完整历史行情或交易日历。

参考修正与失败历史：原参考v1误把每源399条请求起点前记录映射为行级`source_date_range`失败及anomalies，现有腾讯合同实际将该事实保留在metadata。经执行前批准，仅修正该合同映射，v2在任何产品import、Store创建或结果之前重新冻结并独审；v1、原日志和全部3,192条范围事实保留，选择、原token、精确算术和评价标准未改。此项不计为真实异常传播通过。旧登记“六例”文案已在执行前澄清为本次两例；独审脚本另有映射key及SSR空白假设两次错误，修正后完成核对。产品Python、Node均各执行一次并首轮通过，无已发现产品缺陷；参考raw-only共两次。未重跑完整回归，历史3,287/482等计数不累加。

## 没有验收的部分

更多真实来源及拒绝、缺日/多日/重复日、常量、精确零/±1/真并列或显示未分辨等真实边界未验，原合成覆盖单列。Windows原生、实际socket/网络HTTP、浏览器视觉/键盘/窄屏和真实React挂载、性能/并发尾延迟/峰值内存、真人效率、PIT与市场/预测/交易增量均未验。静态SSR、回调和测试数量不替代这些证据。

简单变化相关与旧log相关不等价，选择理由在任何输出前已经记录。全组完整条件不认证同伴、行业、市场中性或未来稳定；反向关系保留其原符号。两窗共享边界价格，不能称统计独立。原数据仅按已存来源回查，经济收益、复权与交易日历资格仍未知。
