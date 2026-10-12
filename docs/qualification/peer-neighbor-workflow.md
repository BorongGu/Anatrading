# 同步双窗有符号相关检索：限定验收

日期：2026-10-12 UTC。基准 main：`63e392cbd682eb0ce2cbfdcfc15fad69632e87ec`。本片新增批量检索入口，在一个明确自选组中一次查看目标对所有候选的前60与当前60来源区间相关、各窗完整排名、精确并列、变化方向及原始端点。产品定义见[049研究](../research/049-signed-peer-neighbor-workflow.md)、[冻结计划](../plans/2026-10-12-peer-neighbor-workflow.md)和[验收协议](../plans/2026-10-12-peer-neighbor-acceptance.md)。

## 实际通过范围

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

## 没有验收的部分

真实来源兼容、Windows原生、实际socket/网络HTTP、浏览器视觉/键盘/窄屏和真实React挂载、性能/并发尾延迟/峰值内存、真人效率、PIT与市场/预测/交易增量均未验。静态SSR、回调和测试数量不替代这些证据。

简单变化相关与旧log相关不等价，选择理由在任何输出前已经记录。全组完整条件不认证同伴、行业、市场中性或未来稳定；反向关系保留其原符号。两窗共享边界价格，不能称统计独立。原数据仅按已存来源回查，经济收益、复权与交易日历资格仍未知。
