# 数值候选合同：DuckDB / Arrow / Parquet 独立往返实验

日期：2026-10-04。结论：**`DECIMAL(38,18)` 与非负 `BIGINT` 在本轮固定数据和边界实验中，有条件通过无损存储验证；条件是先做精确可表示性检查，再写入显式类型。** 直接依赖数据库 CAST 不符合该条件。此结果不定最终 G2 schema，不解除分钟二进制负例的身份/语义隔离，也不解决既有量额冲突。

## 1. 环境与安装边界

现有 `.venv`：Windows AMD64、Python **3.14.0**。从 PyPI 官方元数据核到当前稳定版及 `cp314-cp314-win_amd64` wheel，使用官方 wheel URL 与 SHA256 安装，参数为 `--no-deps --no-index --only-binary=:all:`，未请求额外依赖。

| 包 | 实装并成功导入 | 官方证据 | wheel SHA256 |
|---|---|---|---|
| DuckDB | **1.5.6** | [PyPI 元数据](https://pypi.org/pypi/duckdb/json)，Requires-Python `>=3.10.0`；wheel 发布于 2026-09-28 | `ebcbd09cd8578ab1093393e9b16289cda0e8f1791ac595bf00eb5bad75c3cf00` |
| PyArrow | **25.0.1** | [PyPI 元数据](https://pypi.org/pypi/pyarrow/json)，Requires-Python `>=3.10`；wheel 发布于 2026-08-10 | `f729cfdbd36fd99d543b67a914d2de044c84ebe45be8b34902b299b608c15c8f` |

安装前后分发包清单比较：**只新增 DuckDB、PyArrow；其他依赖版本不变**。元数据快照、wheel URL/哈希、安装日志和前后清单均在 `artifacts/qualification/numeric-roundtrip-package-metadata.json`、`numeric-roundtrip-install.log`、`numeric-roundtrip-packages-before.json`、`numeric-roundtrip-packages-after.json`。本轮未修改依赖清单、SDK、业务代码或冻结原型。

## 2. 方法与成功标准

脚本 `artifacts/qualification/numeric_roundtrip.py` 为独立实验，不导入 `src/anatrading`。它按 [数值观察](numeric-observations.md) 的输入 SHA256 重新核对 8 个公开文件和两批 5 个 BaoStock 请求，再构建显式 Decimal/BIGINT 列。

前置检查只处理表示资格：

1. 字符串精确转 Decimal；有限性、数值范围及类型独立检查。普通 Python float/bool 拒绝进入此入口；原始 binary32 经带来源定位的精确展开后传入 Decimal。
2. Decimal 通过系数/指数移除纯尾零，要求必要 scale≤18、整数部分不超过候选范围；用整数系数构造 scale=18 的值，**不调用舍入使输入合格**。候选范围为 `abs(x)<10^20` 且 `x×10^18` 为整数。
3. 数量必须为有限、精确整数，满足 `0≤V≤9223372036854775807`，再传入 Python int。数据库另有 `CHECK(volume >= 0)`。
4. NULL 与数值 0 分别保留。这里验证可空列的存储行为；哪些业务字段允许缺失，仍由 G2 独立决定。

成功标准是读取值与已接收精确值逐字段相等；小数尾零格式可变化，原 token/位模式保留在输入或隔离记录中。负数 Decimal 的极值案例只验证有符号数值类型，不赋予股票负价/负金额业务资格。

## 3. 实际结果

### 固定样本：38,763 行、232,578 个数值单元

其中正向格式材料及 SDK 字符串为 30,583 行；`sh688001.day/lc1/lc5` 的 **8,180 行仍为身份/语义不合格负例**，只参加表示往返。重复内容的文本变体按独立输入保留，不能据行数声称更多独立市场样本。

| 路径 | 结果 |
|---|---|
| 原精确值 → Python Decimal/int → 参数绑定写 DuckDB → Python 读取 | 38,763 行全部逐值相等 |
| DuckDB → Arrow → Python | 38,763 行全部相等；价格/金额为 `decimal128(38,18)`，数量为 `int64` |
| Arrow → Parquet → Arrow → Python | 38,763 行全部相等；列 schema 保持一致 |
| 同一 Parquet → DuckDB → Python | 38,763 行全部相等 |

该通路保持的是**源已表示的数值**。将 float32 精确展开成 Decimal 不恢复源量化前的信息；更宽列类型也不会修复 TDX/BaoStock 的分钟定义、量额分配或可得时间问题。

### 人工边界：34 个案例

**16 个按预期允入并完成往返，18 个在存储前按预期拒绝。** 这些人工案例与真实数据分开保存。

| 边界 | 实测结果 |
|---|---|
| `1e-18`；最大值 `99999999999999999999.999999999999999999` 及其负值 | 无损往返；最大值读回为 Python Decimal |
| `1.2300000000000000000000`；`0e-50` | 纯尾零可无损化简；原 token 保留 |
| `1e-19`、`1.0000000000000000001`；候选最大值再加非零第 19 位小数 | 存储前拒绝：`fraction_not_exact_at_scale18` |
| `±1e20` | 存储前拒绝：`decimal_magnitude_overflow` |
| 已观察 binary32 精确值 `37.020000457763671875` | 数值可无损往返；原负例的身份资格保持隔离 |
| 人工 binary32 `0x3f800001`，精确值需 23 位小数 | 拒绝超精度，未静默改成 18 位 |
| 数量 `2^53−1`、`2^53`、`2^53+1`、`2^63−1` | 全部精确；`9007199254740993` 与最大 BIGINT 读回为 Python int |
| 数量 `−1`、`2^63`、`1.1` | 分别拒绝负值、溢出、非整数；`1.0000` 可精确转换为 1 |
| Decimal NaN/sNaN/±Infinity、非法 token、普通 float 输入 | 存储前拒绝，保留原输入与原因 |
| NULL、Decimal 0、整数 0 | NULL 读回 None，0 保持数值 0，未互换 |

完整案例与拒绝原因见 `numeric-roundtrip-results.json`、`numeric-roundtrip-quarantine.json`。后续只读检查的返回类型见 `numeric-roundtrip-type-checks.json`；其中附被读取 Parquet 的哈希。

## 4. 绕过前置检查的错误路径

下列结果来自本机实测，说明显式类型声明仍不足以保证原值无损。

| 操作 | 实际行为 | 对候选合同的含义 |
|---|---|---|
| DuckDB `CAST('1.0000000000000000001' AS DECIMAL(38,18))` | 成功返回 `1.000000000000000000`，原值已改变 | 必须先拒绝非零超位，不能仅等待 SQL 报错 |
| DuckDB `CAST('1.5' AS BIGINT)` | 成功返回 **2** | 股数必须先检验精确整数，不能借 CAST 完成校验 |
| Decimal 幅度 `1e20` 或 BIGINT `2^63` 的直接 CAST | `ConversionException` | 仍保留前置范围检查与原始值；不能把异常替换为 0/NULL |
| 直接插入负股数 | `CHECK(volume >= 0)` 引发 `ConstraintException` | 数据库约束可补一层，但不能检查分数在 CAST 前的身份 |
| Arrow 将非零 scale=19 安全转换到 scale=18 | `ArrowInvalid: Rescaling Decimal value would cause data loss` | 此路径拒绝精度损失；不能外推所有来源/转换组合 |
| SQL `1::DECIMAL(38,18) / 3::DECIMAL(38,18)` | SQL 类型 **DOUBLE**；Python float `0.3333333333333333` | VWAP 等除法必须另定派生量精度和舍入规则；此次存储通过不包含精确比值运算 |

这些行为与官方 [DuckDB Numeric Types](https://duckdb.org/docs/current/sql/data_types/numeric)、[Typecasting](https://duckdb.org/docs/current/sql/data_types/typecasting) 及 [Arrow CastOptions](https://arrow.apache.org/docs/python/generated/pyarrow.compute.CastOptions.html) 的边界相符。拒绝记录属于资格隔离；当前正向材料即使数值通过，也仍须服从各自来源和业务语义验收。

## 5. 复现与停止边界

```powershell
.venv\Scripts\python.exe -X utf8 artifacts/qualification/numeric_roundtrip.py
```

| 本地文件（均在 `artifacts/qualification`） | SHA256 |
|---|---|
| `numeric_roundtrip.py` | `3c3ff59e4f400b8518e170fa53d7f7828727afb3d62bab46df914c018409a9c4` |
| `numeric-roundtrip-results.json` | `5e7eb968132ccb0829c630ff4f7e0dd6fb797043af31f54529b4929e4590c495` |
| `numeric-roundtrip-samples.parquet` | `38bec391388927f76dcc3f68bdeace61c0941a17097ecab77ffb157f5206773d` |
| `numeric-roundtrip-boundaries.parquet` | `b8d054698755ae3432716f8ab519fce2cb621ef9f7efe4556c1fdcf026f16dff` |

全部文件留在已忽略的 artifacts 目录；不把原始行情、Parquet 或依赖安装产物加入公共仓库。运行出现 `fetch_arrow_table()` 弃用提示，数值检查没有失败；该次运行使用的 API 与版本按上表固定。

本轮到此停止。**候选存储通路通过，裸 CAST 校验方案不通过；最终 schema、源接入资格、聚合/派生运算、性能和业务模块均未由本实验定案或验收。**
