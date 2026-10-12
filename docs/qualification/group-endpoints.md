# 048 · 共同端点单组：工程验收与有限真实来源核对

2026-10-12 UTC。基线89db7c0edf36e1cb34b035ee6d86658aa28527db，候选分支feat/common-endpoint-group-20261012。对应[研究](../research/048-common-endpoint-group.md)、[方案](../plans/2026-10-12-group-endpoints.md)、[设计审查](../reviews/2026-10-12-group-endpoints-design.md)和[实现独审](../reviews/2026-10-12-group-endpoints-code-review.md)。下述初次工程验收不读取真实行情、旧DB或私有样本，所有Store均在新临时目录使用合成捕获建立。其后的有限真实来源核对单列于文末，两个阶段的计数不累计。

## 本次可用范围

现有多股页面新增“共同端点单组”：4–50明确数据版本、共同a<b，沿030腾讯日线资格及完整未裁剪查询。保留原N/有效K、精确正零负、全部失效成员与已核出的原因；K<N时mean/median/Q1/Q3全null。每行保留源token、精确close、ordinal及完整来源引用。两个回查按钮沿旧onOpen(id,date)，打开对应版本至日期的前缀；不自动聚焦原行。020、Universe旧窗口与043数学不变，无新训练、贡献、采集或依赖。

## 实际自动检查

- 最终Python合成范围整目录回归：**3262通过、0失败、1跳过、34 deselected**，119.93s；另一个真实样本文件在收集前ignore。1 skip是Windows原生当前进程证据，不是私有样本skip。既有Starlette/httpx弃用警告1项。
- 最终全Node：**275通过、0失败、0跳过**；TypeScript及Vite构建通过。JS主包723.55kB，既有>500kB与npm http-proxy配置警告保留，不视为性能通过。
- 较早受影响Python309项、新旧Node子集等均与以上重叠，不相加。独审的270组_source、96组030、48组043旧版本差分均一致；独立API与前端检查另见实现审查，不再累计成产品测试数。
- 初次合成验收未运行：未过滤Python全套、真实数据兼容、浏览器页面/React真实挂载交互/键盘/视觉/截图、Windows原生、实际socket HTTP、性能、真人效率及金融效果。后续有限真实核对见文末；进程内ASGI和SSR不补齐浏览器等其余项目。

命令采用现有.venv与锁定依赖：`.venv/bin/python -X utf8 -m pytest tests -q --ignore=tests/test_real_pipeline.py`，并逐项追加下节21个`--deselect=<nodeid>`。前端在web目录执行`node --test tests/*.test.mjs`及`npm run build`。没有安装或更新依赖。

## 明确排除机制与清单

静读测试源码，识别直接读取仓库私有data/artifacts原件和旧Store的用例；不访问这些私有路径确认其存在性。pytest在执行前按nodeid排除，不依赖“文件大概不存在所以会skip”。

- `--ignore=tests/test_real_pipeline.py`：整文件不收集；静态参数声明为8份冻结来源控制加两组各3种输出路径，共14例。
- 以下21个函数前缀用`--deselect`排除其全部参数化实例，实际输出为34 deselected。均因会读取私有真实行情/捕获或既有data路径。

- `tests/test_daily_background.py::test_private_real_pair_against_original_daily_integers`
- `tests/test_daily_screen.py::test_native_slice_matches_full_stored_query_when_real_samples_exist`
- `tests/test_daily_volume.py::test_real_native_uint32_oracle_every_window`
- `tests/test_formats.py::test_local_real_sample_control_values`
- `tests/test_formats.py::test_known_negative_sample_remains_quarantined`
- `tests/test_formats.py::test_local_bao_samples_keep_exact_source_values`
- `tests/test_minute_aggregation.py::test_real_minute_fraction_oracle_and_http_binding`
- `tests/test_minute_daily_reconciliation.py::test_private_real_pair_against_raw_independent_oracle`
- `tests/test_path_efficiency.py::test_real_native_integer_close_oracle_every_window`
- `tests/test_price_channel.py::test_real_native_uint32_oracle_every_window`
- `tests/test_source_action_window.py::test_private_real_action_boundary_and_original_values`
- `tests/test_source_action_window.py::test_private_three_market_type_one_records`
- `tests/test_source_gaps.py::test_real_three_market_uint32_oracle`
- `tests/test_source_gaps.py::test_real_minute_http_tokens_exact_oracle`
- `tests/test_source_pivots.py::test_three_market_original_integer_oracle`
- `tests/test_source_pivots.py::test_real_minute_original_decimal_token_oracle`
- `tests/test_tdx_daily.py::test_real_three_venue_native_fields_and_original_integers`
- `tests/test_tdx_http_format.py::test_private_real_capture_matches_original_tokens_and_cache_labels`
- `tests/test_tdx_reference.py::test_real_frozen_reference_samples`
- `tests/test_true_range.py::test_real_native_uint32_tr_and_fraction_atr_bounds_every_row`
- `tests/test_volume_at_time.py::test_private_real_capture_against_independent_cache_integer_oracle`

因此本轮共有48项真实样本相关用例明确未执行（14未收集＋34 deselected），与旧阶段“缺私有样本48 skip＋Windows 1 skip”的记录分开。当前3262通过不包含这些排除项；不称完整未过滤测试全通过。

## 任务链与异常证据

- Python独立Fraction手算覆盖A/B反例、奇偶中位数/Type7、正/零/负/净零、近零精确符号、N=4/50、K=0/1/N−1/N、各成员缺端点、事件预算/诊断、来源拒绝同时叠加结构畸形。
- 新合成capture→真实decoder→新Store的完整公开query/投影等价；HTTP请求结果与纯函数相等；a/b前缀按ordinal对账原close/token，明确前缀与完整query_id不同。
- API所有完整源先计数再加载、非法参数在读取前拒绝、原件损坏/缺失整请求错误、修复后显式重试、2MiB超限整请求拒绝。
- 前端验证跨请求成员/日期、比例与完整组summary恒等式，先合法DECIMAL端点再推导行分数；不声称客户端独立认证原件。源码未知异常名（Unicode和原型名）仍保留。独审另验50成员1864位均值分母与第21条关键异常，不属于性能实验。
- 新模式实际prepare/load/controller路径覆盖旧脏lookback/filter旁路、唯一请求、失败/重试、重复提交、取消后新结果和迟到成功/错误、哈希等待中编辑/dispose、旧模式草稿保留。原成员暂不可用沿既有失效原语处理。
- 显示组名不进入请求身份，改名不触发第二次请求；SSR再次渲染新组名，报告与成员不变。真实React事件挂载仍未验。
- SSR检查4–50与来源提示、没有旧lookback/A-B角色输入、N/K/全部失效行、原价/精确符号/限制文案。纯结果组件调用两个按钮的callback，逐个验证snapshot与a/b；没有浏览器操作声明。

## 本轮失败、修正与再验

独审先发现问题，作者以回归复现失败后修正，未更改旧测试期望来迎合数学变化；原失败日志由本次验证产物保留。

1. 报告直接返回共享scope/limitations，调用者修改可污染下次报告：新Python回归1失败/40通过，改为每请求独立复制后41通过。
2. JS只允许中国符号，误拒绝需要保留的HK/US失效来源：新JS回归1失败/48通过，失效行仅保留既有规范显示身份；有效算术仍限SH/SZ，修正后49通过。
3. DTO内部可检测矛盾（a/b相同ordinal、已披露区间阻断未入member reasons、异常计数与实例矛盾）曾被接受：新增反例先失败，补最小一致性检查后通过。
4. 异常计数字典的原型名碰撞和canonicalJson对Unicode的额外限制曾误拒绝合法失效行：新增反例先失败；改为null-prototype计数与own-key逐值核对，不改变通用canonicalJson或来源资格。最终全Node275通过。

最终限定源码经独立回读无剩余实质阻断。发布/远端验证由后续集成单独执行；本报告不声称已推送、合并或部署。

2026-10-12补修共同端点请求错误的共享恢复指引，并以own-key查询修复既有共享错误字典的原型键问题，成员行原因保持不变；两处均先有失败回归，最终全Node 290项、TypeScript及Vite构建通过，保留npm配置与主包体积提示，未重跑后端、真实来源、浏览器、Windows原生、性能或金融效果验收。

## 后续有限真实来源核对（2026-10-12）

在合并后源码 `e3ec37545dd0780b857c41d6dc6ef17ffaaef843` 上，固定8份既有腾讯日线完整捕获、两个显式4成员组和3种预注册日期窗口，完成6个唯一案例的离线兼容与精确算术核对，独立终审通过。没有修改产品或重跑上述3262/275项合成回归；原行情、原始捕获、查询、DTO、SSR及私有验证产物不随文档发布。

- **输入与独立参考**：8份捕获各导入一次至同一个全新隔离Store，共5120行、51200个原字符串token；逐行保留来源定位。参考实现先从原body的腾讯封装与11字段行独立解析，以Decimal/Fraction生成并冻结期望；独审另用十进制整数/指数与通用Type7分位数重算，均未调用产品helper生成期望。
- **实际通过链**：完整query与研究projection、纯函数及进程内ASGI API逐字段一致；6份实际API DTO通过前端模型和analysis_id核验，再经静态SSR核对成员、原端点、精确统计与限制。48项同版本日期前缀核对原token/ordinal，48个纯组件callback绑定正确；前缀与完整query_id不同。前缀逐行和callback结论依据已审运行断言，独审另复核保存的前缀记录及SSR逐行语义，本轮未进行浏览器操作。
- **精确案例范围**：4例N=4/K=4、2例N=4/K=0。缺终点控制保留全部成员，四项统计与符号比例均为null，不前移日期、不缩N。短区间仍来自完整来源，未验证真实来源本身仅两行；固定真实样本也未覆盖K=1–3、零/近零、拒绝来源或损坏恢复。重复运行不计新增案例或独立样本。
- **失败与修正保留**：计划初版遗漏腾讯前缀及11字段要求，在价格解析和执行前纠正；执行中先后出现API查询包装读取KeyError、SSR缺失原因文案硬编码错误。两次均只修验收脚本对应读取或断言，保留首轮失败，成员、日期、原件、数值期望与产品均未改变。最终限定链通过，没有已证实的产品数值缺陷或剩余实质阻断；不能称首遍全过。
- **完整性边界**：39份冻结输入及登记材料的字节哈希、验收期间的仓库与选定源码指纹不变；没有访问旧Store或旧DB。新Store正常写入和关闭不以DB字节不变为门槛。
- **来源资格不升级**：2份strict格式保留原CLI采集失败限定，6份legacy保留重建标记、运输证据未建立及来源哈希仅语法验证的原限定。8份来源均达到640行上限，保留请求范围不符、覆盖未验证、可能截断和采集时钟不可得；完整捕获只指保存的body。单位、复权、公司行动覆盖、闭合、历史可得性/PIT、完整交易日历与历史行业成员仍未知或未核实。

本次结论仅限上述8份来源和6个固定案例，不扩大至更多数据、完整历史、全市场、行业指数、组合或经济收益、预测和交易价值。网络采集、实际socket HTTP、浏览器/React真实挂载/键盘/视觉/截图、Windows原生、性能、真人效率及金融效果仍未验；未过滤完整测试套件未重跑。公开记录只披露方法、范围、失败历史与结果边界。
