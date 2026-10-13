# 051 无目标全成对双窗相关

2026-10-13，编码前冻结。基线 e42c609。研究目的：同一完整来源组一次核对全部成员对；不声称预测、金融优势或实测人效。

## 阅读与独立审查

本次实际阅读根 AGENTS、049/050 的现行精确核、扫描、窗口及前端验证代码；一手论文阅读来自前序《组内共同变化：有界研究与候选取舍》的阅读账本，未把前序阅读冒认为本次重读。前序已定向读 Roy–Vetterli 2007 entropy 定义、Mazzucato 等 2016 dimensionality 定义、SciPy pearsonr 和 NumPy corrcoef 官方定义。独立设计反方《全成对共同变化：独立设计审查与冻结建议》最终 SHA256 为 6b66799505c8bff89f8394321841be2eaaa16f4797a8920b0113f59e8a31621b；复核范围是四/六成员反例、现行核与来源规则、DTO/交互/预算，未重新读论文或运行实验。仓内决定见对应 plan/review。

## 冻结口径

输入排序后2–50个唯一数据版本和精确截止日，无目标、阈值、可调窗。每成员独立取截止及以前最后121个日期组，必须包含截止；先日期后价格，不补齐。各121数组逐项相等才确定共同D；不交集、不多数表决、不回退。全源扫描复用049私有 _scan/_window_member；来源、身份、原件或端点失格关闭整组相关，保留全部N成员与全部M=N(N−1)/2对及诊断。不同网格的共同日期为空、共同边界null，各自候选日期及端点仍保留。结构/算术/预算错误整请求失败。

变化 r_t=(P_t−P_{t−1})/P_{t−1}，前60与当前60变化共享中间价格。各列每窗只中心化一次，复用049有理数/整数 _price_integer/_center/_correlation/_display，65536bit逐中间守卫、50位ROUND_HALF_EVEN、estimate最多80字符、4位display、精确sign/boundary。常量包含恒价与恒定非零变化，仅关闭涉及该成员的对；其余对继续。无对角，所有i<j按版本ID顺序，无排名、差值、均值、PCA、聚类、PR/熵、图或热图。

全响应canonical UTF-8 JSON硬限2MiB（包括analysis_id）。6050端点仅存一次，最多2450cells；超限group_pair_result_limit整次失败，不扩预算、不缩N。输入上限不保证每个合法输入均可装下。analysis_id绑定方法、规则、来源引用、截止、每成员候选日期、共同日期、scope/limitations，哈希是自洽校验，非来源签名。

前端严格keys、ID/完整组合、日期/端点/诊断、常量与可算政策、K/M守恒、数字字符串与SHA验证。常量用精确价格BigInt交叉乘积独立核对，不实现第二套Pearson核。现有默认模式不变；显式新模式一次请求。两窗默认折叠，固定50对分页（全量DTO先通过），一次仅挂载一个选中对双方端点，沿既有controller及onOpen回查。

## 冻结合成验收及失败条件

先异常测试，所有Store仅新指定TMPDIR内构建。四成员：u=(1,1,−1,−1), v=(1,−1,1,−1)，每窗前四变化乘0.1、后56为0，T=D=u/B=v/C=v或−v；T的相关摘要与各成员共同起止端点相同，B–C从+1变−1。六成员3u+3v与4u+v+w有同计数不同成员结构。独立有理数/手算核与逐目标049全部对对照。恒价/恒定非零/近常量、全相同/符号翻转、2/50成员及2450cells，缺/额外/重复日期、截止缺失、全局身份反证、共同缺日未知、置换/未来合法追加、受控整数/显示/2MiB失败，DTO篡改/SHA及SSR/异步失效。

保留原始失败，最终重跑受影响Python、新合成API、完整Node、TS/Vite；不跑fullpytest，不启动服务/端口/浏览器、真实行情、旧Store、性能benchmark、依赖安装、账户/部署。本次50成员只验正确性/序列化；资源异常立即停止。Windows、真实来源、浏览器实际挂载、性能和预测效果未验。变更共享helpers、来源语义或预算先重新审查。

## 可公开复核的研究依据与候选取舍

以下阅读归属均为前序研究的定向一手阅读，本次实现者只复核其公式及相关仓内代码，未重新阅读全文：

- Roy & Vetterli, EUSIPCO 2007，pp.606–607 §2.1定义与§2.2性质，归一化奇异值的熵有效秩；未复核其余证明/实验：[会议原文](https://www.eurasip.org/Proceedings/Eusipco/Eusipco2007/Papers/a5p-h05.pdf)。对PSD相关矩阵奇异值等于特征值，对数据矩阵则不能混用。
- Mazzucato, Fontanini & La Camera (2016)，Methods Dimensionality measure与有限试次理论，借用PR定义及有限样本提醒，未迁移神经科学效果到股票：[正式论文](https://www.frontiersin.org/journals/systems-neuroscience/articles/10.3389/fnsys.2016.00011/full)。前序网页部分公式缺失，同论文PMC索引辅助核对，未复现模型。
- SciPy pearsonr Warnings/Notes：常量未定义、近常量浮点风险及Pearson公式；不采用p值或置信区间：[官方文档](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.pearsonr.html)。NumPy corrcoef定义/rowvar/Notes：标准化及浮点对称/范围局限：[官方文档](https://numpy.org/doc/stable/reference/generated/numpy.corrcoef.html)。现行实现采用049精确核，官方浮点实现不替代本项目验收。
- TradingView Pine矩阵、请求与限制定义的前序定向阅读：[Matrices](https://www.tradingview.com/pine-script-docs/language/matrices/)、[请求概念](https://www.tradingview.com/pine-script-docs/concepts/other-timeframes-and-data/)、[限制](https://www.tradingview.com/pine-script-docs/writing/limitations/#number-of-calls)。其支持多源及矩阵能力；未实测竞品同任务，不宣称其缺少全相关矩阵。

三路线：逐目标049可恢复全部成对相关，是强简单基线；本片增加一次明确批量读取与来源回查操作价值，不声称新增原始数学信息。完整有符号表直接保留成员关系，采用。PCA/谱摘要不直接返回谁与谁同向/反向，本题没有额外必要性，停止。前序043/046/049失败决定不因本片恢复。

固定N、非恒定列相关矩阵R及M=N(N−1)/2，q=Σ(i<j)ρ²/M。有tr(R²)=N+2Σρ²，因此D_PR=(tr R)²/tr(R²)=N/[1+(N−1)q]；固定N时只是平均相关平方的一一变换。熵有效秩exp(−Σp log p)与PR不同。任意符号对角D满足D²=I，R和DRD同谱；全同向与半数反向可有同一谱，不能以谱集中度解释全组同涨同跌。六成员3+3与4+1+1各6正9零，计数也不返回成员结构。四成员反例只比较T相关摘要和共同起止端点；C完整121价格序列不同，049完整端点仍足以重算全部关系。
