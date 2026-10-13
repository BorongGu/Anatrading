# 064 精确收盘离散纯核心：限定验收

2026-10-13；基线 main `84179960272ffbe0c8589efeb89513c89e85ac3f`。仅新增纯 Python 核心、合成测试与研究记录；没有 API、UI、Store入口、依赖或默认报告变化。发布状态以实际提交/PR为准。

## 编码前依据与独立复核

[冻结设计](../research/064-exact-close-dispersion-core.md)在产品编码前写入。原仓库外 v2 SHA256 为 `9cb44f89fdd70f4ec013c523b35727225f188cec88d961720a788a8e83d8a4b7`；公开副本另补执行范围和实际字段，不冒充相同文件hash。独立反方设计GO，落实最小非恒定σ、整数元组构造、显示负零与20项长度先验等意见。历史063四个冻结源例、constant100附加例、另行五例零修正及旧正价审计失败保持分列；本轮不重写历史实验协议。

严格正价适配器复用完整daily_bars核验，数学核心允许零；两者测试独立。固定当前及前19来源日期组，总体方差、均值±2σ，无调参、去噪、买卖判断、概率覆盖或TradingView完整兼容声明。整数矩精确、平方根闭包络是数值误差界；负下界有效，近零显示不覆盖精确值。

## 合成测试与失败记录

先写 `tests/test_close_dispersion.py`，首次运行因产品模块尚不存在出现1项collection error（预期红灯），之后实现。新增75项通过，独立中心化Fraction/190对差/二分平方根验证17种窗口、恶意Decimal上下文、类型/范围/尺度拒绝、舍入跨界与负零、严格正价/坏OHLC、来源冲突/隔离、位置恢复、重复/无定位/未知覆盖、全前缀和身份变化。该测试含零核心与零适配器拒绝两个独立语义。

受影响组合（新增、numeric、research_series、price_channel、candle_geometry、true_range、signal_research）279通过、0失败、2项缺私有样本跳过，0.87秒；新增75为其子集，不累计。

独立代码复核同一产品hash：104个窗口的Fraction中心化、精确平方界、独立整数half-even显示参考及prec=1/Emin=-1/Emax=1/全traps恶意上下文通过，无实现阻断。另一路独立验收：83个数值向量及恶意上下文复跑、17项正负端点探查、合成适配器/身份/坏窗恢复/全前缀通过，源文件前后hash不变。这些是各自重叠的合成检查，不能相加为市场样本或产品测试条数；外部审查脚本不随仓库产品测试发布。

## 运行环境与完整回归

本轮恢复为 Python 3.14.0 隔离 `.venv`，按现有 requirements-workbench.lock 安装项目与dev依赖，pip check通过。没有沿用此前环境运行结果；没有安装前端依赖。既有产品测试的真实文件来源均为仓库内 data/reference、data/local 或 artifacts/qualification，其目录缺失时按原测试skip，不寻找替代文件。静态检查未发现测试引用受禁外部历史库；临时合成Store位于本轮单独临时根。无原始行情读取、新采集、历史Store、浏览器或网络服务重试。

完整产品允许集合3670通过、0失败、49跳过（48项缺私有样本、1项Windows原生）、2 deselected、1项既有Starlette/httpx弃用警告，143.47秒。两项现有test_http_slow_chunks_do_not_reset_absolute_deadline（header/body）需要真实localhost socket，明确deselected；未再次尝试已知受限socket。测试中合成ASGI请求和临时Store不代表真实HTTP/浏览器或实源兼容。

额外qualification初次实跑218通过、16失败、112子用例通过，1.34秒；16失败均为baostock模块或包元数据缺失。该包不在本轮恢复的产品锁依赖，缺失已先行识别；这不是完整资格套件通过，不修改产品依赖掩盖失败。随后另建隔离资格环境，按原qualification/requirements.txt六项固定依赖与README固定pytest9.1.1闭包恢复，未修改产品.venv；pip check通过。按资格README的进程级无网络guard复跑：234通过、112子用例通过、0失败/跳过，2.15秒；9个Python进程均guard_installed，0次阻止的socket/DNS尝试。初次16失败和原日志保留，恢复成功另列，不覆盖历史。新运行日志SHA256 `94fc9b74b919990e13dcce638e6e70f017f0727f013b79007dcb00333023006c`；网络审计SHA256 `74c1629e6bb22b289210df09603b72e2e61594088f81e69b2ed507a12b3f03a8`。本轮无真实登录/抓取或历史Store。

## 另行冻结的资源成本观测

数值验收完成后，独立测试者先冻结两种20,000行合成工作负载，再各运行一次独立子进程；这不是追补数值验收门槛，不重调标准。每进程256MiB地址空间、120秒CPU/墙钟及64MiB序列化字节预算；没有扩大预算重试。JSON流式编码仅计数，不保留大输出文件。

- 全有效常量：19,981可算窗，报告1.520秒、JSON编码0.599秒、整个子进程2.189秒，峰值RSS77,720KiB，紧凑JSON13,252,068字节。
- 全无效零OHLC：0可算窗、399,810条重复窗口无效成员，报告0.389秒、JSON编码2.070秒、整个子进程2.498秒，峰值RSS146,336KiB，紧凑JSON39,557,697字节。

两例在本次预算内，仍暴露明显成本：全无效输出约37.7MiB。当前合同保持离线完整审计纯函数，不能据此直接接入API/UI；未来须单独审核分段展示、避免重复invalid_members或有界投影等候选及身份/回查语义。本次不临时重构schema，不宣称吞吐优势、稳定尾延迟、实际HTTP或浏览器性能；峰值为整个合成子进程，未证明函数增量RSS。上述脚本与原结果位于外部验收记录，有限观测与仓库内可复现正确性测试分开。

## 仍未完成

真实来源兼容、实盘闭合、历史可得性、复权与公司行动、完整交易日历、Windows原生、实际浏览器、稳定性能/增量RSS、人效、样本外预测与交易收益均未验。058等既有科学STOP不变。代码上固定20项的计算上界不能替代实测性能。

## 复现命令与最终数学文件

在README要求的Python3.14与产品锁环境执行：

```sh
.venv/bin/python -m pytest tests/test_close_dispersion.py -q
.venv/bin/python -m pytest tests/test_close_dispersion.py tests/test_numeric.py tests/test_research_series.py tests/test_price_channel.py tests/test_candle_geometry.py tests/test_true_range.py tests/test_signal_research.py -q
env -u DRAWDOWN_FIXTURE_EXPORT .venv/bin/python -m pytest tests -q -ra -k 'not test_http_slow_chunks_do_not_reset_absolute_deadline' --basetemp=<本次专用临时目录>
```

在资料存在的其他机器上，真实文件相关测试不能因此自动取得读取授权；本次是在上述私有目录不存在条件下运行。需要真实socket的两项未运行，不以允许集合代替不受限全套。

最终独立审查和上述产品测试使用同一数学代码：
- `src/anatrading/close_dispersion.py` SHA256 `c8242f76ed020a52d0abfe6666ace5f89e05e476ba469cf620a9333bb2f94ee4`
- `tests/test_close_dispersion.py` SHA256 `516653cfaf6e640cb9149f81445e18114d7921a0415c776e681810f105819ec7`

旧产品文件未修改，旧测试照原参数运行；未新增analysis_id、API路由、Store导入或前端接线。后续提交若修改数学字节，必须重新执行对应验收。
