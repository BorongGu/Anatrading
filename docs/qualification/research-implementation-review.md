# 股票研究首轮实现：独立反方验收

日期：2026-10-11。审查范围：当前工作区中 `store.py`、`tdx_session.py`、六个新增研究模块、研究 HTTP 路由及对应测试。依据 `AGENTS.md`、2026-10-11 实施方案、研究 026/027 与编码前反方最终决定。审查过程中实现仍在并行落地；本文件不把尚未交付的界面或其他任务算成实现缺陷。

## 当前结论

**本次后端审查发现的 P1 已修复并独立复验。当前审查范围未发现尚未解决的阻断项。** 因果时点、来源日期组、重叠选择、统计分母、SQL 等价和本机请求边界的已跑检查通过。此结论仅适用于本文件列明的代码与测试，不替代最后全套重跑、真实来源、Windows 原生、浏览器或预测增量验收。

审查者只新增 `tests/test_research_adversarial.py` 与本报告，未修改产品代码，未提交或推送。

## 发现与关闭记录

### IR-1 / P1：其他证券行被当作当前证券参与研究（已关闭）

**原始复现。** 通过真实 `EvidenceStore.import_bytes` 导入合成 BaoStock 信封，信封证券为 `sh.600001`，其中第三行证券 token 为 `sz.000001`；OHLC 为合法的 999，周围价格为 10、11、12、13、14。解码器已保留该行 `source_code=fail`。原 `research_series._bar` 只检验 OHLC，忽略身份矛盾，导致该行仍为 `warming_up/reason=None`，产生突破和约 −98.8% 的“有效”后续变化。

**影响。** 同一共用标准化被单股、事件、双股、集合消费；另一证券的观测会污染当前证券的状态、标签和排序。条件性/复盘限制不能消除此类明确矛盾。

**已实施修复。** 明确 `source_code` 失败或原 token 与来源声明冲突，标 `source_identity_conflict`。保留日期槽和原价格，不参与研究，状态重置、事件窗口和配对窗口按既有坏组规则阻断。无关成交量/金额缺失仍不阻断价格研究。

**独立证据。** `test_conflicting_row_instrument_cannot_be_researched_as_envelope_security` 修复前真实失败，修复后通过；检查坏行无突破、随后新状态段及错误事件未入样。实现者另外增加实际导入的冲突回归。

### IR-2：明确复权冲突与已隔离负例的资格传递（已关闭）

审查同时发现，共用标准化最初不传递 `metadata.quarantined=True` 或 `known_negative_sample=fail`，可输出完整有效组和事件，且研究结果不带隔离原因。这里只使用合成元数据复现；私有已知负例原件未提供。

修复后：

- 行复权 token 与信封声明冲突为 `source_adjustment_conflict`
- 解码器明确复权检查失败仍失去研究资格，不能被本层重新提升
- 已隔离来源各组标 `known_negative_source`，单股资格为 `source_rejected`
- 原始源值保留，拒绝资格不等于删除证据

上述规则已在同一独立重跑中覆盖实现者新增的测试。真实负例文件兼容仍未验。

### IR-3：集合跨市场同步解释的首版边界（已关闭的范围澄清）

最初集合允许 CN_A 与 US 在相同日期标签混合排名和广度，双股已拒绝这种组合。冻结集合段对同市场的要求不如双股段明确，因此本项作为范围澄清报告，并未先判定为公式错误。

主方选择首版同市场，当前 `universe_report` 已在身份阶段拒绝市场混合并给 `research_market_mismatch`；SH/SZ/BJ 共属 CN_A，不被机械限制为同一交易所。由此避免把跨市场同日标签当成同步研究截面。跨市场扩展需另明确观察时点与解释。

## 独立对抗测试

`tests/test_research_adversarial.py` 共 9 项：

1. 实际导入的其他证券行冲突与断链
2. 固定随机种子 30 组 × 70 日期槽，含无效 OHLC、重复日期、随机前窗与全部允许 horizon；对照朴素逐窗实现逐项检查突破、贪心选择、purge、无效、未成熟及计数守恒
3. DECIMAL(38,18) 合法最小正数/最大值交替输入，低全局 Decimal 精度下三类研究仍可序列化为无 NaN/Infinity 的 JSON
4. 相差 1e−18 的事件价格使用精确变化，不被 float64 相同价格抹成零标签
5. 相近 Decimal 动量按精确分数排名，不产生二进制舍入假并列
6. 收益方差、价格方差门槛两侧的资格，以及完美拟合仅关闭残差标准化
7. 三个 HTTP 入口拒绝非本机 Host/Origin；成功请求后同字节数原件变更，三入口仍全部给 `raw_object_corrupt`，不绕过逐请求校验
8. 11 个各 20,000 行的集合预检在总计 220,000 行时拒绝，并证明没有调用行查询/构造响应
9. 集合允许 SH/SZ/BJ 同市场，拒绝 CN_A 混合 US/HK

## 已核对实现性质

- 单股初始化只用首根一次；Kalman 预测创新先于更新；Joseph 协方差更新；EMA 同一 log 尺度；EWMA 原始收益及 pre/post 分离；坏组同时中断模型和收益链。
- 突破严格此前窗口、不含当日 high，Decimal 判断；h 以来源日期组计步，不删坏组重新挑终点；事件选择不看未来标签；跨切点训练标签 purge；基线包含全部规则可算日期并明示重叠。
- 双股先共同日期对齐，再形成相同起止区间收益；重复/坏共同槽不被静默跳接；收益窗包含当前、价格拟合排除当前；常数、残差退化、未知覆盖各有原因。
- 集合 N+1 日期组和 N 个收益，波动 ddof=1、非正最大回撤、同截止缺失不回退；精确动量 competition ranking，成员身份稳定排序，各指标独立分母。
- HTTP 参数拒绝未知/重复/非法日期或窗口，方法身份含来源与参数；递推加载完整截止前缀；先计数再读取；同源边界与 owner 线程复用。
- SQL 条件显式保留 NULL 标签；完整批次未定位计数与所选行分离；超 BIGINT 序号有安全处理；已有独立全批 Python oracle 验证 query_id、计数、顺序、总和与原件校验。
- POSIX 锁文件保留 inode，双进程争用/退出释放以及失败关闭句柄已跑；Windows 固定宽度结构可在 Linux 检查布局，不能替代原生 Windows API 运行。

## 实际运行证据

首次审查已有研究/API/SQL/锁测试：112 通过。

修复后最后于 03:19 UTC 独立执行：

```text
.venv/bin/python -m pytest -q \
  tests/test_research_adversarial.py tests/test_research_series.py \
  tests/test_signal_research.py tests/test_event_study.py \
  tests/test_pair_research.py tests/test_universe_research.py \
  tests/test_research_api.py tests/test_store_query.py tests/test_store_platform.py
160 passed in 6.88s
```

其中无跳过。`git diff --check` 通过。不同成员仍在并行新增测试，最终全套计数由主方最后一次完整运行记录，不能将本次局部 160 项当作全仓通过。

## 未验证与发布约束

- 私有真实软件导出、已知负例真实字节和真实来源兼容：未提供/未跑
- Windows 原生 Store/进程 API/桌面软件：未跑
- 浏览器、完整用户工作流、窄屏、焦点与异步请求竞态：由界面验收单列，本次后端报告未验
- 最大 W 双股、最大总集合、峰值内存、owner 排队影响与实际网络 HTTP 性能：本审查未独立跑；纯算法或 ASGI 耗时不能替代这些结论
- 预测/样本外增量、成本后可执行收益：未验证；不得据本测试宣称有效交易信号或竞品优势

新增实现变更若影响上述行为，应重跑对应独立测试；最终发布声明分别列出已跑、失败、跳过与未跑项目。
