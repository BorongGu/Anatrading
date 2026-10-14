# 068 OHLC 兼容路径最大源价跌幅：限定验收

2026-10-14 UTC；基线 main `17c9064794969340fcac1210f82e940d760c8bd4`。新增独立纯模块 `ohlc_decline_bounds.py`，只接受至多253根正价 OHLC，另提供可信完整日线前缀的单窗适配器。没有 API、UI、CLI、Store 入口、依赖、缓存或真实采集变更。发布以实际提交/PR为准。

## 编码前依据

[冻结设计 v2](../research/068-ohlc-decline-bounds.md)原样复制，SHA256 `f25ebf37b9019ded8decacaea5d8757508cd287f3703654258e632bad1cfbda4`。先独立数学设计 GO，再关闭 R1 首因统计和 R2 重复日期引用两项澄清，负责人授权实现。原129,960路径/420组实验、另行8,000三柱组合审查不覆盖旧记录，不相加为市场样本。[独立评审决定](../reviews/068-ohlc-decline-bounds-review.md)分列设计与最终代码检查。

两条假想极值路径 O→L→H→C 与 O→H→L→C 得到所有供给柱兼容路径的最大比例源价跌幅紧下/上界。整数定标与约分分数不受 Decimal 上下文影响；正跌幅并列取该证明路径最早谷、该谷前最早同高峰。零结果无见证。close-only 基线另行择早，不修改050/054合同。端点从首根开盘初始化，不包含窗前峰。

上界仅限已提供柱的相容集合：供给常量100两柱可得0；若漏掉中间100→1→100，则完整真实区间跌幅为99/100。报告始终披露日历/闭合/复权/历史可得性未验，源价不等于财富或成交收益。

## 实现与结果字段

`exact_bounds(bars)` 对完整窗先验格式、数值、正价与OHLC几何，再扫描两个极值路径和收盘子序列。`DeclineBoundsError` 继承既有 NumericError/ValueError，保留 code、bar_index、field。lower/upper/close_only 含 value、witness；分子分母为精确整数字符串；identified、ambiguity_width、path_ids、scope 另列。close_only 见证只含峰谷 bar_index/price_exact；来源报告从成员补 date/ordinal。

`decline_bounds_report(query,start_date,end_date)` 检查严格日期、retrospective、cutoff恰等于end、日线及无ordinal裁切。身份只投影已核 selection 字段 mode/cutoff/ordinal_start/ordinal_end，来源资格深复制。身份字段≤256 UTF-8字节，raw hash为64小写十六进制，身份与资格投影≤16KiB；最终compact UTF-8报告≤256KiB，超预算整调用失败。上下文无来源认证能力。

全源行首冲突计数、来源级known_negative_source标记、逐日期组首因分别保留；被首因短路的同一行后续判据标明未评估。重复日期ordinal=null，通过query身份及日期回查，未附加原行引用载荷。窗外普通坏价不关闭有效窗；任意来源冲突及无法定位覆盖关闭整个报告。坏volume/amount不单独阻止价格计算。成员和无效成员均完整保留，不截断、不跳行、无端点回退。

## 红灯、合成验收与回归

先写异常/独立oracle测试，再创建模块；首次收集因模块不存在出现1项预期错误，日志保留。初版新增46项通过，后补足固定前缀/反例/ordinal/20,000行边界/身份测试至66项通过（3.77秒），没有产品数值失败。独立全先后点对oracle覆盖原129,960路径/420组、两条达到路径、见证位置、相等槽位、极端格点和循环分数、恶意context、坏结构、全局来源反证/局部坏价、深复制等。

最初受影响集337通过、2跳过（4.45秒），包含当时46项新增；扩展后最终受影响与完整允许集合结果在下方补记。缺私有样本skip保留未验。独立验收先冻结外部脚本再读取接口，16,293断言及补充34项检查通过（共16,327检查）；原路径枚举420组零不一致。它首轮因测试oracle漏转Fraction失败，修复测试后通过，候选模块未改；旧失败记录保留，未修改数学期望。独立补充测试首轮误用metadata.symbol声明字段，读取既有identity合同后改为metadata.interpretation.instrument/venue，再通过原先的冲突拒绝断言；这是夹具修正，候选源码未改。

## 限定资源观测

独立测试者在Linux/Python3.12.14预先冻结三个负载及进程定义；产品回归另使用Python3.14。分别在独立子进程中一次运行，硬限256MiB地址空间、120秒CPU/墙钟、完整输出256KiB；未扩大预算或重复失败负载。计时涵盖报告内解析/排序/核心/最终JSON预算验证及额外完整序列化的合计，没有分阶段计时；RSS是整个合成子进程高水位，地址空间与RSS分别报告。

- 253根最大/最小合法格点交替：0.0101秒，RSS13,184KiB，完整JSON60,926字节。
- 253根无效日期组：0.00460秒，RSS11,520KiB，54,210字节，253个invalid_members全部保留。
- 20,000来源行中选择253根：0.2876秒，RSS39,996KiB，33,991字节。

三例在冻结预算内。这是本次单次限定观测，无稳定尾延迟、人效或函数增量RSS结论。核心O(m)，适配器排序O(n log n)、存储O(n)，n≤20,000；不把全链描述成O(253)。不增加每个历史窗口结果。

## 复现与边界

在既有Python3.14产品锁环境运行 `.venv/bin/python -m pytest tests/test_ohlc_decline_bounds.py -q`。独立外部数学与资源脚本及原始日志不随公开仓库产品发布；上列独立结论不能仅靠hash重跑。仓库测试可复现其独立小域oracle，资源观测另列。

本轮无旧DB、历史真实捕获、行情请求或私有样本搜寻。完整回归仅使用新临时合成文件；两项已知真实localhost socket测试明确未跑。实源兼容、API/UI、实际浏览器、Windows原生、持续性能、预测与交易价值均未验。既有实采NO-GO与058科学STOP保持。

最终代码 SHA256 `f39188c2be75f3c641290b9a414e84043d7186542e7727e72a9006b4511cf9b2`；数学实现自首次通过后未改。

## 最终回归补记

最终新增66项通过；受影响组合357通过、0失败、2项缺私有样本跳过，4.34秒。新增为组合子集，不累计。产品 `.venv` Python3.14原锁环境 `pip check` 通过，未安装或修改依赖。

独立qualification环境按其README进程级网络guard运行234项与112子用例通过，0失败/跳过，2.26秒。9个Python进程均有guard_installed，0次socket/DNS拦截记录；没有真实登录或行情请求。最终测试文件SHA256 `849779eb1eb85e3ff86b62655cc1996c241642597235fa6d331e9a82913722b0`。

完整允许集合初轮3805通过、49跳过、2 deselected、1项既有Starlette/httpx弃用警告，147.37秒。该轮开始时收集46项新增测试；产品字节未改变，随后补充20项测试，最终测试文件的完整允许集合另行重跑，不把首次结果冒充最后66项闭包。

最终256KiB保护由独审静态核对：所有字段和见证补充后按compact UTF-8实检，超限整调用拒绝，不删减证据。三种资源负载均在限内；超限分支没有动态触发，保持静态确认而非动态通过。

最终测试文件完整允许集合重跑：**3825通过、0失败、49跳过（48缺私有样本、1 Windows原生）、2 deselected、1项既有Starlette/httpx弃用警告，146.45秒**。命令为 `env -u DRAWDOWN_FIXTURE_EXPORT .venv/bin/python -m pytest tests -q -ra -k 'not test_http_slow_chunks_do_not_reset_absolute_deadline' --basetemp=<本轮全新合成临时目录>`。本结果与最终模块/测试hash一致；两项真实localhost socket测试未跑。首轮3805与最终3825为重复回归，不累加。编译检查及 `git diff --check` 通过。
