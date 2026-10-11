# 小样本数据资格探测

历史记录：[自动取数验证](../docs/qualification/baostock-acquisition-results.md)经真实帧诊断和反方修正，P01取得2,784条5m数据（2页）；P02在record结构预检处停止，P03批量日线未执行。该阶段记录为资格工具218项测试及112子用例通过，生产自动采集尚未放行。历史记录不代表当前检出包含全部私有原件；本次离线复验见下文。以下五组小样本工具保留为第一轮G1证据路径。

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

首批正式数据内核已按[独立合同](../docs/contracts/IMPLEMENTATION_DECISIONS.md)完成限定验收；本目录工具不写产品数据库。旧原型已存档；图形单快照实施按[008评审](../docs/reviews/008-workbench-review.md)限定放行，界面仍待交付。

第二轮离线边界测试使用项目开发依赖中的pytest（含子进程和fake socket，不发出行情请求）：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -X utf8 -m pytest `
  qualification/test_acquisition_preflight.py qualification/test_acquisition_process.py `
  qualification/test_baostock_acquisition_probe.py qualification/test_baostock_transport.py `
  qualification/test_baostock_frame_diagnostic.py -q
```

`baostock_acquisition_probe.py` 使用独立子进程、有限输出解压、逐页完整响应检查；原始响应存入独立的`baostock-acquisition`目录。它的本地通过状态与实际帧兼容结果分开，当前不将它接入生产更新。原始失败记录不覆盖，诊断也不能推进获取完成或覆盖状态。

## 2026-10-11 离线测试隔离

本轮在仓库外建立独立 Linux Python 3.14.0 资格测试环境，按 `qualification/requirements.txt` 安装六项固定依赖，另用 pytest 9.1.1；不修改产品环境或依赖锁。补齐依赖后的首次结果为214通过、4失败、0跳过，另112子用例通过。4项使用 fake SDK/socket 的 D01 worker 边界测试仍访问生产前置检查，而当前检出缺少固定历史 `20261003T183357030285Z/P01/status.json`；旧失败记录保留。

现在这4项显式使用前置检查 stub，并断言检查恰好调用一次；原有请求数、控制内容不落盘、字段白名单、清理和历史标识断言均保留。父进程超时测试也使用该显式 stub。真实 `_check_prerequisites` 另以临时合成文件测试：直接检查、worker、run 三个入口分别拒绝协议缺失、原状态缺失、两类哈希变化和 SDK 版本不符，并确保不启动 worker/子进程、不调用保存、不创建输出目录；另验证匹配合成字节与版本可通过。合成路径和内容明确标记为测试用途，不写回仓库历史目录。

完整 `qualification` 本次结果为 **234通过、0失败、0跳过，另112子用例通过**，包含新增16项真实前置检查测试。进程级网络 guard 覆盖本次9个 Python 进程，记录到0次 socket/DNS 尝试。此结果只覆盖离线测试隔离与合成边界；未认证缺失历史材料、真实登录/网络、真实行情或生产采集资格。生产前置条件及固定指纹保持不变，缺历史材料时实际诊断仍须停止。Linux 本次结果也不代替 Windows 原生回归。

复现时从仓库根目录使用独立环境和新日志目录。先准备环境（安装阶段需要官方 PyPI 网络；测试阶段禁止网络）：

```bash
QUAL_ENV="$(dirname "$PWD")/anatrading-qualification-env"
python3.14 -m venv "$QUAL_ENV"
"$QUAL_ENV/bin/python" -m pip install --index-url https://pypi.org/simple --only-binary=:all: \
  -r qualification/requirements.txt pytest==9.1.1 iniconfig==2.3.0 packaging==26.3 \
  pluggy==1.6.0 Pygments==2.21.0
```

以下 guard 只作用于当前测试及其继承环境的 Python 子进程，不修改系统网络设置。`mktemp` 在 workspace 的仓库外创建新目录，保留每次日志；不要复用旧 `--basetemp` 或覆写历史失败日志。

```bash
set -euo pipefail
QUAL_RUN="$(mktemp -d "$(dirname "$PWD")/qualification-offline.XXXXXX")"
mkdir -p "$QUAL_RUN/guard" "$QUAL_RUN/tmp"
cat > "$QUAL_RUN/guard/sitecustomize.py" <<'PY'
import json
import os
from pathlib import Path
import sys

log = Path(os.environ["QUALIFICATION_AUDIT_LOG"])
def record(event):
    with log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"pid": os.getpid(), "event": event}) + "\n")
def audit(event, args):
    if event in {"socket.__new__", "socket.connect", "socket.bind", "socket.getaddrinfo", "socket.sendto"}:
        record("blocked:" + event)
        raise RuntimeError("qualification_offline_guard: " + event)
sys.addaudithook(audit)
record("guard_installed")
PY
export TMPDIR="$QUAL_RUN/tmp" TEMP="$QUAL_RUN/tmp" TMP="$QUAL_RUN/tmp"
export PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export PYTHONPATH="$QUAL_RUN/guard:$PWD"
export QUALIFICATION_AUDIT_LOG="$QUAL_RUN/network-audit.jsonl"
"$QUAL_ENV/bin/python" -B -X utf8 -m pytest qualification -q -p no:cacheprovider \
  --basetemp "$QUAL_RUN/tmp/pytest" --junitxml "$QUAL_RUN/qualification.xml" \
  2>&1 | tee "$QUAL_RUN/qualification.log"
```

应检查审计日志含 `guard_installed` 且没有 `blocked:` 事件；若 guard 未加载、日志缺失或发生拦截，不可报告“0次网络尝试”。资格独立环境不含产品数据库/HTTP依赖；产品 `tests` 仍使用产品环境另行验证，不把两套环境或结果混合。
