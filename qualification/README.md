# 小样本数据资格探测

当前状态：[自动取数探测](../docs/qualification/baostock-acquisition-results.md) 的139项本地测试和50个子用例通过，但首个真实跨页请求在帧结构校验处停止，后续空首屏和批量日线案例未执行。[D01结构诊断](../docs/qualification/FRAME_DIAGNOSTIC_PROTOCOL.md) 的57项测试通过，单次实测发现声明正文后另有12字节；尚未取得跨页行情，自动采集尚未放行。以下五组小样本工具保留为第一轮G1证据路径。

依据 [G1 协议](../docs/qualification/G1_PROTOCOL.md)，只读访问 BaoStock 官方匿名公共服务，固定五组小查询，每组独立进程、8 秒 socket 超时、35 秒总时限。成功取得数据仅记作 `captured_sample_not_qualified`，随后需独立对账；这是 G1 工具，未构成生产采集器。

已验证运行环境为 Windows、64 位 Python 3.14.0，依赖按实际环境固定。项目根目录 PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r qualification/requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s qualification -p "test_baostock_probe.py" -v
.\.venv\Scripts\python.exe -X utf8 qualification/baostock_probe.py
```

已有 `.venv` 时跳过创建。可用重复的 `--case` 选择固定案例，例如 `--case daily-bank-overlap --case daily-bank-recent` 只补取两条同日的银行日线；不支持自由扩大日期或证券范围。

探测为显式运行，不随测试执行。所有数据及状态写入被 Git 忽略的 `artifacts/qualification/baostock/<UTC运行时间>/`；不覆盖旧运行，不使用 Key，不自动重试。退出码表示探测程序是否结束，**各查询的成败以 `status.json` 为准**。匿名登录失败或进程超时会停止该轮后续查询。

- `request.json`：固定行情请求的参数。
- `market-sdk-decoded.txt`：仅行情查询返回的 SDK 解压/解码文本；保留字节和哈希，但未捕获网络压缩包。
- `sdk-cells.json`：SDK 字段与单元格；只在全部为原始字符串时满足捕获结构检查。
- `status.json`：本机观察时间、版本、SDK 代码哈希、状态和行数。认证/控制响应不保存。

捕获检查覆盖错误码、空结果、字段顺序、非字符串/残缺行和分页上限。它不验证全市场覆盖、交易日历、区间完整性、行情真值、可持续更新、授权再分发或历史可得性。SDK 元数据与逐行字段的差异必须交给独立审计处理，不自动修正。

首批正式数据内核已按[独立合同](../docs/contracts/IMPLEMENTATION_DECISIONS.md)完成限定验收；本目录工具不写产品数据库。旧原型已存档，`web`仍冻结。

第二轮离线边界测试使用项目开发依赖中的pytest（含子进程和fake socket，不发出行情请求）：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -X utf8 -m pytest `
  qualification/test_acquisition_preflight.py qualification/test_acquisition_process.py `
  qualification/test_baostock_acquisition_probe.py qualification/test_baostock_transport.py `
  qualification/test_baostock_frame_diagnostic.py -q
```

`baostock_acquisition_probe.py` 使用独立子进程、有限输出解压、逐页完整响应检查；原始响应存入独立的`baostock-acquisition`目录。它的本地通过状态与实际帧兼容结果分开，当前不将它接入生产更新。原始失败记录不覆盖，诊断也不能推进获取完成或覆盖状态。
